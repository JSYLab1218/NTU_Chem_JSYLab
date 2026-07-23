#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""批次把 Weebly wSlideshow 轉成可在 GitHub Pages 顯示的原生相簿。"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

STYLE_ID = "native-weebly-gallery-style"
SCRIPT_ID = "native-weebly-gallery-script"

GALLERY_CSS = r'''
<style id="native-weebly-gallery-style">
.native-weebly-gallery {
  width: 100%;
  max-width: 1100px;
  margin: 18px auto 35px;
  outline: none;
}
.native-weebly-stage {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  min-height: 280px;
  overflow: hidden;
  background: #f3f3f3;
}
.native-weebly-main {
  display: block;
  width: auto;
  height: auto;
  max-width: 100%;
  max-height: 76vh;
  margin: 0 auto;
  object-fit: contain;
}
.native-weebly-control {
  position: absolute;
  top: 50%;
  z-index: 4;
  width: 44px;
  height: 56px;
  padding: 0;
  border: 0;
  border-radius: 3px;
  background: rgba(0, 0, 0, 0.58);
  color: #fff;
  font-size: 29px;
  line-height: 1;
  cursor: pointer;
  transform: translateY(-50%);
}
.native-weebly-control:hover,
.native-weebly-control:focus-visible {
  background: rgba(0, 0, 0, 0.82);
}
.native-weebly-prev { left: 9px; }
.native-weebly-next { right: 9px; }
.native-weebly-status {
  padding: 8px 0 5px;
  color: #555;
  text-align: center;
  font-size: 14px;
}
.native-weebly-thumbnails {
  display: flex;
  gap: 7px;
  width: 100%;
  padding: 5px 2px 11px;
  overflow-x: auto;
  overflow-y: hidden;
  scroll-behavior: smooth;
}
.native-weebly-thumb {
  flex: 0 0 auto;
  width: 84px;
  height: 63px;
  margin: 0;
  padding: 2px;
  border: 2px solid transparent;
  background: transparent;
  cursor: pointer;
}
.native-weebly-thumb.is-active { border-color: #2b4761; }
.native-weebly-thumb img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
@media screen and (max-width: 700px) {
  .native-weebly-stage { min-height: 200px; }
  .native-weebly-control { width: 38px; height: 50px; font-size: 25px; }
  .native-weebly-thumb { width: 70px; height: 53px; }
}
</style>
'''

GALLERY_SCRIPT = r'''
<script id="native-weebly-gallery-script">
(function () {
  "use strict";

  function initialiseGallery(gallery) {
    var dataNode = gallery.querySelector(".native-weebly-data");
    var mainImage = gallery.querySelector(".native-weebly-main");
    var status = gallery.querySelector(".native-weebly-status");
    var thumbnails = gallery.querySelector(".native-weebly-thumbnails");
    var previous = gallery.querySelector(".native-weebly-prev");
    var next = gallery.querySelector(".native-weebly-next");
    var images;
    var current = 0;

    if (!dataNode || !mainImage || !status || !thumbnails || !previous || !next) return;

    try {
      images = JSON.parse(dataNode.textContent);
    } catch (error) {
      console.error("Cannot read gallery data", error);
      return;
    }

    if (!Array.isArray(images) || images.length === 0) return;

    function show(index) {
      current = (index + images.length) % images.length;
      mainImage.src = images[current].url;
      mainImage.alt = images[current].caption || ("Lab photograph " + (current + 1));
      status.textContent = (current + 1) + " / " + images.length;

      thumbnails.querySelectorAll(".native-weebly-thumb").forEach(function (button, i) {
        var active = i === current;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-current", active ? "true" : "false");
        if (active) {
          button.scrollIntoView({behavior: "smooth", block: "nearest", inline: "nearest"});
        }
      });
    }

    images.forEach(function (image, index) {
      var button = document.createElement("button");
      var thumbnail = document.createElement("img");
      button.type = "button";
      button.className = "native-weebly-thumb";
      button.setAttribute("aria-label", "Show photo " + (index + 1));
      thumbnail.src = image.url;
      thumbnail.alt = "";
      thumbnail.loading = "lazy";
      button.appendChild(thumbnail);
      button.addEventListener("click", function () { show(index); });
      thumbnails.appendChild(button);
    });

    previous.addEventListener("click", function () { show(current - 1); });
    next.addEventListener("click", function () { show(current + 1); });
    gallery.addEventListener("keydown", function (event) {
      if (event.key === "ArrowLeft") show(current - 1);
      if (event.key === "ArrowRight") show(current + 1);
    });
    show(0);
  }

  function start() {
    document.querySelectorAll(".native-weebly-gallery").forEach(initialiseGallery);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
</script>
'''

DIV_PATTERN = re.compile(
    r'''<div\b[^>]*\bid\s*=\s*(["'])(?P<id>[^"']+)-slideshow\1[^>]*>\s*</div>''',
    re.IGNORECASE,
)

URL_PATTERN = re.compile(
    r'''(?:["']?url["']?)\s*:\s*(["'])(.*?)\1''',
    re.IGNORECASE | re.DOTALL,
)


def fix_url(raw: str) -> str:
    value = html.unescape(raw.strip()).replace(r"\/", "/").replace("\\/", "/")
    lower = value.lower()
    if lower.startswith(("http://", "https://", "//", "data:", "#")):
        return value

    value = re.sub(r"^(?:\./)+", "", value).lstrip("/")
    if re.match(r"^\d+(?:/\d+){4}/", value) or value.startswith("1/2/2/8/"):
        value = "uploads/" + value

    split = urlsplit(value)
    return urlunsplit(("", "", split.path, "", ""))


def extract_images(script_body: str) -> list[dict[str, str]]:
    images_match = re.search(r"\bimages\s*:\s*\[", script_body, re.IGNORECASE)
    if not images_match:
        return []

    array_start = script_body.find("[", images_match.start())
    depth = 0
    quote = None
    escaped = False
    array_end = -1

    for i in range(array_start, len(script_body)):
        ch = script_body[i]
        if quote is not None:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                array_end = i
                break

    if array_end == -1:
        return []

    array_text = script_body[array_start + 1:array_end]
    return [{"url": fix_url(match.group(2))} for match in URL_PATTERN.finditer(array_text)]


def gallery_html(element_id: str, images: list[dict[str, str]]) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_-]+", "-", element_id).strip("-") or "gallery"
    first = html.escape(images[0]["url"], quote=True)
    data = json.dumps(images, ensure_ascii=False).replace("</", r"<\/")
    return f'''<div class="native-weebly-gallery" id="native-gallery-{safe_id}" tabindex="0">
  <div class="native-weebly-stage">
    <button class="native-weebly-control native-weebly-prev" type="button" aria-label="Previous photo">&#10094;</button>
    <img class="native-weebly-main" src="{first}" alt="Lab photograph" loading="lazy" />
    <button class="native-weebly-control native-weebly-next" type="button" aria-label="Next photo">&#10095;</button>
  </div>
  <div class="native-weebly-status" aria-live="polite">1 / {len(images)}</div>
  <div class="native-weebly-thumbnails" aria-label="Photo thumbnails"></div>
  <script type="application/json" class="native-weebly-data">{data}</script>
</div>'''


def find_blocks(source: str):
    blocks = []
    for div_match in DIV_PATTERN.finditer(source):
        after = div_match.end()
        script_match = re.match(
            r"\s*<script\b[^>]*>(?P<body>.*?)</script\s*>",
            source[after:],
            re.IGNORECASE | re.DOTALL,
        )
        if not script_match:
            continue
        body = script_match.group("body")
        if "wSlideshow" not in body or ".render" not in body:
            continue
        images = extract_images(body)
        if not images:
            continue
        blocks.append((div_match.start(), after + script_match.end(), div_match.group("id"), images))
    return blocks


def insert_before(source: str, tag: str, addition: str) -> str:
    match = re.search(rf"</{tag}\s*>", source, re.IGNORECASE)
    if not match:
        raise ValueError(f"找不到 </{tag}>")
    return source[:match.start()] + addition + "\n" + source[match.start():]


def remove_assets(source: str) -> str:
    source = re.sub(
        rf'\s*<style\b[^>]*id=["\']{STYLE_ID}["\'][^>]*>.*?</style\s*>\s*',
        "\n", source, flags=re.IGNORECASE | re.DOTALL,
    )
    source = re.sub(
        rf'\s*<script\b[^>]*id=["\']{SCRIPT_ID}["\'][^>]*>.*?</script\s*>\s*',
        "\n", source, flags=re.IGNORECASE | re.DOTALL,
    )
    return source


def process(path: Path) -> tuple[int, int]:
    source = path.read_text(encoding="utf-8-sig", errors="replace")
    blocks = find_blocks(source)
    if not blocks:
        return 0, 0

    for start, end, element_id, images in reversed(blocks):
        source = source[:start] + gallery_html(element_id, images) + source[end:]

    source = remove_assets(source)
    source = insert_before(source, "head", GALLERY_CSS)
    source = insert_before(source, "body", GALLERY_SCRIPT)
    path.write_text(source, encoding="utf-8")
    return len(blocks), sum(len(item[3]) for item in blocks)


def main() -> int:
    parser = argparse.ArgumentParser(description="批次修復所有 Weebly slideshow")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    if not root.is_dir():
        print(f"找不到資料夾：{root}")
        return 2

    patterns = ("**/*.html", "**/*.htm") if args.recursive else ("*.html", "*.htm")
    files = []
    for pattern in patterns:
        files.extend(root.glob(pattern))
    files = sorted({p.resolve() for p in files if p.is_file() and not any(part.startswith("_slideshow_backup_") for part in p.parts)})

    if not files:
        print(f"找不到 HTML：{root}")
        return 1

    backup = None
    if not args.no_backup:
        backup = root.parent / (root.name + "_slideshow_backup_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
        backup.mkdir(parents=True)
        for path in files:
            relative = path.relative_to(root)
            target = backup / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        print(f"已備份：{backup}")

    changed = galleries = images = failed = 0
    print(f"找到 {len(files)} 個 HTML。\n")

    for index, path in enumerate(files, 1):
        relative = path.relative_to(root)
        try:
            count, image_count = process(path)
            if count:
                changed += 1
                galleries += count
                images += image_count
                print(f"[{index}/{len(files)}] 已修復：{relative}（{count} 個相簿，{image_count} 張照片）")
            else:
                print(f"[{index}/{len(files)}] 略過：{relative}（沒有尚未轉換的 Weebly 相簿）")
        except Exception as error:
            failed += 1
            print(f"[{index}/{len(files)}] 失敗：{relative}（{type(error).__name__}: {error}）")

    print("\n========== 完成 ==========")
    print(f"修改頁面：{changed}")
    print(f"轉換相簿：{galleries}")
    print(f"圖片總數：{images}")
    print(f"失敗頁面：{failed}")
    if backup:
        print(f"備份位置：{backup}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
