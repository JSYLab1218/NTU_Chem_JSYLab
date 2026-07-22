#!/usr/bin/env python3
r"""
Weebly / static-site image path repair tool

功能
1. 遞迴掃描網站資料夾內所有圖片。
2. 掃描 HTML、CSS、JS 中的圖片路徑，包括：
   - <img src="...">
   - background-image: url(...)
   - slideshow 內的 "url":"..."
   - JavaScript 中跳脫過的 1\/2\/... 路徑
3. 用完整路徑、路徑尾端、檔名與正規化檔名尋找正確圖片。
4. 可從原始 Weebly 網站下載本機缺少的圖片。
5. 產生 repaired_site 資料夾與 CSV 修復報告，不直接破壞原始網站。

Python 3.9+，只使用標準函式庫。
"""

from __future__ import annotations

import argparse
import csv
import html
import os
import re
import shutil
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urljoin, urlsplit
from urllib.request import Request, urlopen


IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg",
    ".bmp", ".tif", ".tiff", ".avif", ".ico",
}
TEXT_EXTENSIONS = {".html", ".htm", ".css", ".js"}

# 能抓到：
# uploads/.../a.jpg
# /uploads/.../a.jpg?123
# 1/2/2/8/.../a.jpg
# 1\/2\/2\/8\/...\/a.jpg
# https://example.com/a.jpg
IMAGE_REFERENCE_RE = re.compile(
    r"""(?ix)
    (?P<ref>
        (?:
            (?:https?:)?//[^\s"'<>()[\]{};]+
            |
            (?:\\?/)?(?:[A-Za-z0-9_%+().~@-]+(?:/|\\/))+[A-Za-z0-9_%+().~@-]+
            |
            [A-Za-z0-9_%+().~@-]+
        )
        \.(?:jpe?g|png|gif|webp|svg|bmp|tiff?|avif|ico)
        (?:\?[^\s"'<>()[\]{};]*)?
    )
    """
)

WEIBLY_ACCOUNT_PATH_RE = re.compile(r"^\d+/\d+/\d+/\d+/\d+/")


@dataclass
class RepairRecord:
    text_file: str
    original: str
    status: str
    replacement: str = ""
    matched_file: str = ""
    download_url: str = ""
    note: str = ""


def log(message: str) -> None:
    print(message, flush=True)


def is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS


def normalize_slashes(value: str) -> str:
    return value.replace("\\/", "/").replace("\\", "/")


def split_reference(reference: str) -> tuple[str, str]:
    """回傳不含 query/fragment 的路徑與原 query。"""
    cleaned = html.unescape(reference.strip())
    cleaned = cleaned.strip("\"'")
    cleaned = normalize_slashes(cleaned)

    if cleaned.startswith("//"):
        cleaned = "https:" + cleaned

    parts = urlsplit(cleaned)
    if parts.scheme in {"http", "https"}:
        path = parts.path
        query = ("?" + parts.query) if parts.query else ""
    else:
        path = cleaned.split("#", 1)[0]
        if "?" in path:
            path, query_value = path.split("?", 1)
            query = "?" + query_value
        else:
            query = ""

    return unquote(path), query


def canonical_web_path(reference: str) -> str:
    """
    將 Weebly 圖片路徑轉成網站根目錄相對路徑。

    例如：
      /uploads/1/2/.../a.jpg -> uploads/1/2/.../a.jpg
      1/2/2/8/122804110/a.jpg -> uploads/1/2/2/8/122804110/a.jpg
    """
    path, _ = split_reference(reference)
    path = path.lstrip("/")
    path = re.sub(r"^\./+", "", path)

    if WEIBLY_ACCOUNT_PATH_RE.match(path):
        path = "uploads/" + path

    # 移除 ..，避免寫到輸出資料夾外
    safe_parts = [part for part in PurePosixPath(path).parts if part not in {"", ".", ".."}]
    return "/".join(safe_parts)


def normalized_stem(filename: str) -> str:
    """
    建立較寬鬆的檔名鍵值，用來處理 Weebly 常見的 _orig、-orig 差異。
    只在精確比對失敗時使用。
    """
    name = unquote(Path(filename).name).lower()
    stem = Path(name).stem

    previous = None
    while previous != stem:
        previous = stem
        stem = re.sub(r"(?i)(?:[_-](?:orig|original))+$", "", stem)
        stem = re.sub(r"(?i)(?:[_-]\d+x\d+)$", "", stem)

    return re.sub(r"[^a-z0-9]+", "", stem)


def path_parts_lower(path: Path) -> tuple[str, ...]:
    return tuple(part.lower() for part in path.as_posix().split("/") if part)


def common_suffix_length(a: Iterable[str], b: Iterable[str]) -> int:
    a_list = list(a)
    b_list = list(b)
    score = 0
    for x, y in zip(reversed(a_list), reversed(b_list)):
        if x != y:
            break
        score += 1
    return score


class ImageIndex:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.images: list[Path] = []
        self.by_basename: dict[str, list[Path]] = defaultdict(list)
        self.by_normalized_stem: dict[str, list[Path]] = defaultdict(list)
        self.refresh()

    def refresh(self) -> None:
        self.images.clear()
        self.by_basename.clear()
        self.by_normalized_stem.clear()

        for path in self.root.rglob("*"):
            if is_image(path):
                resolved = path.resolve()
                self.images.append(resolved)
                self.by_basename[path.name.lower()].append(resolved)
                self.by_normalized_stem[normalized_stem(path.name)].append(resolved)

    def relative_to_root(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def find(self, reference: str, text_file: Path) -> tuple[Path | None, str]:
        raw_path, _ = split_reference(reference)
        canonical = canonical_web_path(reference)
        original_path = raw_path.lstrip("/")

        candidate_relatives: list[str] = []
        for value in (original_path, canonical):
            value = normalize_slashes(value).lstrip("/")
            if value and value not in candidate_relatives:
                candidate_relatives.append(value)

        # 1. 相對於目前 HTML/CSS/JS
        for relative in candidate_relatives:
            candidate = (text_file.parent / Path(relative)).resolve()
            if is_image(candidate) and self.root in candidate.parents:
                return candidate, "existing-relative-path"

        # 2. 相對於網站根目錄
        for relative in candidate_relatives:
            candidate = (self.root / Path(relative)).resolve()
            if is_image(candidate) and self.root in candidate.parents:
                return candidate, "existing-root-path"

        # 3. 完整路徑尾端比對
        wanted_parts = tuple(
            part.lower()
            for part in PurePosixPath(canonical or original_path).parts
            if part not in {"", ".", ".."}
        )
        suffix_matches: list[tuple[int, Path]] = []
        if wanted_parts:
            for image_path in self.images:
                rel_parts = path_parts_lower(image_path.relative_to(self.root))
                score = common_suffix_length(rel_parts, wanted_parts)
                if score >= 2:
                    suffix_matches.append((score, image_path))

        if suffix_matches:
            best_score = max(score for score, _ in suffix_matches)
            best = sorted({p for score, p in suffix_matches if score == best_score})
            if len(best) == 1:
                return best[0], f"unique-path-suffix-{best_score}"

        # 4. 完整檔名比對
        basename = Path(original_path).name.lower()
        exact = self.by_basename.get(basename, [])
        if len(exact) == 1:
            return exact[0], "unique-basename"
        if len(exact) > 1:
            ranked = self._rank_candidates(exact, wanted_parts)
            if ranked is not None:
                return ranked, "ranked-duplicate-basename"
            return None, f"ambiguous-basename:{len(exact)}"

        # 5. 寬鬆檔名比對
        key = normalized_stem(basename)
        loose = self.by_normalized_stem.get(key, []) if key else []
        same_ext = [
            path for path in loose
            if path.suffix.lower() == Path(original_path).suffix.lower()
        ]
        pool = same_ext or loose

        if len(pool) == 1:
            return pool[0], "unique-normalized-name"
        if len(pool) > 1:
            ranked = self._rank_candidates(pool, wanted_parts)
            if ranked is not None:
                return ranked, "ranked-normalized-name"
            return None, f"ambiguous-normalized-name:{len(pool)}"

        return None, "not-found"

    def _rank_candidates(
        self, candidates: list[Path], wanted_parts: tuple[str, ...]
    ) -> Path | None:
        scored: list[tuple[int, int, Path]] = []
        for path in candidates:
            rel_parts = path_parts_lower(path.relative_to(self.root))
            suffix_score = common_suffix_length(rel_parts, wanted_parts)
            depth_difference = abs(len(rel_parts) - len(wanted_parts))
            scored.append((suffix_score, -depth_difference, path))

        scored.sort(reverse=True)
        if not scored:
            return None
        if len(scored) == 1 or scored[0][:2] > scored[1][:2]:
            return scored[0][2]
        return None


def encode_local_reference(path: Path, text_file: Path, escaped: bool) -> str:
    relative = os.path.relpath(path, start=text_file.parent)
    relative = Path(relative).as_posix()
    encoded = quote(relative, safe="/._-~()")
    return encoded.replace("/", "\\/") if escaped else encoded


def source_url_for(reference: str, source_base: str) -> tuple[str, str]:
    raw_path, query = split_reference(reference)
    original = html.unescape(reference.strip()).replace("\\/", "/")

    if original.startswith(("http://", "https://", "//")):
        if original.startswith("//"):
            original = "https:" + original
        parts = urlsplit(original)
        url = original
        destination = canonical_web_path(parts.path)
        return url, destination

    destination = canonical_web_path(reference)
    web_path = "/" + destination
    url = urljoin(source_base.rstrip("/") + "/", web_path.lstrip("/"))
    if query:
        url += query
    return url, destination


def download_image(
    reference: str,
    source_base: str,
    root: Path,
    timeout: int,
    retries: int,
) -> tuple[Path | None, str, str]:
    url, destination_rel = source_url_for(reference, source_base)
    if not destination_rel:
        return None, url, "empty-destination"

    destination = (root / destination_rel).resolve()
    if root.resolve() not in destination.parents:
        return None, url, "unsafe-destination"

    destination.parent.mkdir(parents=True, exist_ok=True)

    last_error = ""
    for attempt in range(1, retries + 1):
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 Chrome/124 Safari/537.36"
                    ),
                    "Referer": source_base.rstrip("/") + "/",
                },
            )
            with urlopen(request, timeout=timeout) as response:
                content_type = response.headers.get("Content-Type", "").lower()
                data = response.read()

            if not data:
                raise ValueError("伺服器回傳空檔案")

            # 有些失敗頁也會回傳 200；避免把 HTML 當圖片存下來
            if "text/html" in content_type and destination.suffix.lower() != ".svg":
                raise ValueError(f"伺服器回傳 HTML，而不是圖片 ({content_type})")

            destination.write_bytes(data)
            return destination, url, f"downloaded:{len(data)}bytes"

        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(0.8 * attempt)

    if destination.exists() and destination.stat().st_size == 0:
        destination.unlink()
    return None, url, last_error


def should_ignore_reference(reference: str) -> bool:
    value = html.unescape(reference.strip()).lower()
    return value.startswith(("data:", "blob:", "javascript:", "#"))


def collect_references(text: str) -> list[str]:
    seen: set[str] = set()
    references: list[str] = []
    for match in IMAGE_REFERENCE_RE.finditer(text):
        reference = match.group("ref")
        if should_ignore_reference(reference):
            continue
        if reference not in seen:
            seen.add(reference)
            references.append(reference)
    return references


def rewrite_text_file(
    text_file: Path,
    image_index: ImageIndex,
    source_base: str | None,
    download_missing: bool,
    timeout: int,
    retries: int,
) -> tuple[list[RepairRecord], bool]:
    original_text = text_file.read_text(encoding="utf-8", errors="replace")
    references = collect_references(original_text)
    records: list[RepairRecord] = []
    replacements: dict[str, str] = {}

    # 先處理與下載缺圖
    downloaded_any = False
    for reference in references:
        matched, method = image_index.find(reference, text_file)
        download_url = ""
        download_note = ""

        if matched is None and download_missing and source_base:
            matched, download_url, download_note = download_image(
                reference=reference,
                source_base=source_base,
                root=image_index.root,
                timeout=timeout,
                retries=retries,
            )
            if matched is not None:
                downloaded_any = True
                method = "downloaded"

        if downloaded_any:
            # 新下載的檔案要加入索引，後面的頁面才能找到
            image_index.refresh()
            downloaded_any = False

        if matched is None:
            records.append(
                RepairRecord(
                    text_file=text_file.relative_to(image_index.root).as_posix(),
                    original=reference,
                    status="unresolved",
                    download_url=download_url,
                    note=download_note or method,
                )
            )
            continue

        escaped = "\\/" in reference
        replacement = encode_local_reference(matched, text_file, escaped=escaped)
        replacements[reference] = replacement
        records.append(
            RepairRecord(
                text_file=text_file.relative_to(image_index.root).as_posix(),
                original=reference,
                status="repaired" if replacement != reference else "already-valid",
                replacement=replacement,
                matched_file=image_index.relative_to_root(matched),
                download_url=download_url,
                note=download_note or method,
            )
        )

    # 用 regex callback 避免字串替換造成一個路徑誤改另一個路徑
    def replace_match(match: re.Match[str]) -> str:
        original = match.group("ref")
        return replacements.get(original, original)

    new_text = IMAGE_REFERENCE_RE.sub(replace_match, original_text)
    changed = new_text != original_text
    if changed:
        text_file.write_text(new_text, encoding="utf-8")

    return records, changed


def copy_site(source_root: Path, output_root: Path) -> None:
    source_root = source_root.resolve()
    output_root = output_root.resolve()

    if source_root == output_root:
        raise ValueError("輸出資料夾不可與來源資料夾相同")

    if output_root.exists():
        shutil.rmtree(output_root)

    ignored_names = {
        output_root.name,
        ".git",
        "__pycache__",
        ".DS_Store",
    }

    def ignore(directory: str, names: list[str]) -> set[str]:
        ignored = {name for name in names if name in ignored_names}
        # 避免把先前產生的 repaired_site 再複製進去
        ignored.update(name for name in names if name.startswith("repaired_site"))
        return ignored

    shutil.copytree(source_root, output_root, ignore=ignore)


def write_report(records: list[RepairRecord], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "text_file",
                "original",
                "status",
                "replacement",
                "matched_file",
                "download_url",
                "note",
            ],
        )
        writer.writeheader()
        for record in records:
            writer.writerow(record.__dict__)


def find_text_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in TEXT_EXTENSIONS
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="掃描並修復 Weebly / 靜態網站的圖片路徑。"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="原始網站根目錄，預設為目前資料夾。",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="輸出資料夾。預設為 <root>/repaired_site。",
    )
    parser.add_argument(
        "--source-url",
        default=None,
        help="原始網站網址，例如 https://jsylab1218.weebly.com",
    )
    parser.add_argument(
        "--download-missing",
        action="store_true",
        help="從 --source-url 下載本機缺少的圖片。",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=25,
        help="單次下載逾時秒數，預設 25。",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="下載失敗重試次數，預設 3。",
    )
    parser.add_argument(
        "--no-copy",
        action="store_true",
        help="直接修復 --root（會先建立 _backup_before_image_repair 備份）。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_root = args.root.expanduser().resolve()

    if not source_root.is_dir():
        log(f"錯誤：找不到網站資料夾：{source_root}")
        return 2

    if args.download_missing and not args.source_url:
        log("錯誤：使用 --download-missing 時必須提供 --source-url。")
        return 2

    if args.no_copy:
        working_root = source_root
        backup_root = source_root.parent / f"{source_root.name}_backup_before_image_repair"
        if backup_root.exists():
            shutil.rmtree(backup_root)
        log(f"建立備份：{backup_root}")
        copy_site(source_root, backup_root)
    else:
        working_root = (
            args.output.expanduser().resolve()
            if args.output
            else source_root / "repaired_site"
        )
        log(f"複製網站到：{working_root}")
        copy_site(source_root, working_root)

    image_index = ImageIndex(working_root)
    text_files = find_text_files(working_root)

    log(f"找到圖片：{len(image_index.images)} 個")
    log(f"找到 HTML/CSS/JS：{len(text_files)} 個")

    all_records: list[RepairRecord] = []
    changed_files = 0

    for index, text_file in enumerate(text_files, start=1):
        relative = text_file.relative_to(working_root).as_posix()
        log(f"[{index}/{len(text_files)}] 掃描 {relative}")
        records, changed = rewrite_text_file(
            text_file=text_file,
            image_index=image_index,
            source_base=args.source_url,
            download_missing=args.download_missing,
            timeout=args.timeout,
            retries=args.retries,
        )
        all_records.extend(records)
        changed_files += int(changed)

    report_path = working_root / "image_path_report.csv"
    write_report(all_records, report_path)

    repaired = sum(record.status == "repaired" for record in all_records)
    already_valid = sum(record.status == "already-valid" for record in all_records)
    unresolved = sum(record.status == "unresolved" for record in all_records)
    downloaded = sum(record.note.startswith("downloaded:") for record in all_records)

    log("")
    log("========== 完成 ==========")
    log(f"掃描圖片引用：{len(all_records)}")
    log(f"修正引用：{repaired}")
    log(f"原本已可用：{already_valid}")
    log(f"下載圖片：{downloaded}")
    log(f"仍無法配對：{unresolved}")
    log(f"有變更的文字檔：{changed_files}")
    log(f"輸出網站：{working_root}")
    log(f"詳細報告：{report_path}")

    if unresolved:
        log("")
        log("注意：請打開 image_path_report.csv，篩選 status=unresolved。")
        log("程式刻意不自動猜測重複檔名，避免把教授照片接到錯的人身上。")

    return 0 if unresolved == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
