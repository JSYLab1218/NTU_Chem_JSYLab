#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批次修復 Weebly 網站所有 HTML 的上方導覽列。

使用方式：
    python3 fix_all_html_headers.py
    python3 fix_all_html_headers.py --root /path/to/site
    python3 fix_all_html_headers.py --recursive

預設行為：
1. 掃描程式所在資料夾同一層的所有 .html / .htm。
2. 建立完整備份資料夾。
3. 從每個頁面原本的 Weebly 選單自動讀取網站名稱與導覽項目。
4. 移除失效的 Birdseye header。
5. 插入完全獨立、不依賴 Weebly custom.js 的桌面／手機導覽列。
6. 不修改頁面正文、圖片、相簿或其他內容。

只使用 Python 標準函式庫，不需要 pip install。
"""

from __future__ import annotations

import argparse
import html as html_module
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit


STYLE_ID = "standalone-header-style"
HEADER_ID = "static-site-header"
SCRIPT_ID = "static-header-script"


@dataclass
class MenuItem:
    title: str = ""
    href: str = "#"
    children: list["MenuItem"] = field(default_factory=list)


class WeeblyMenuParser(HTMLParser):
    """讀取 <ul class=\"wsite-menu-default\"> 中的階層式選單。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.started = False
        self.target_ul_depth = 0
        self.current_list: list[MenuItem] = []
        self.list_stack: list[list[MenuItem]] = []
        self.root_items: list[MenuItem] = []
        self.li_stack: list[MenuItem] = []
        self.in_anchor = False
        self.anchor_text: list[str] = []
        self.anchor_owner: MenuItem | None = None

    @staticmethod
    def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
        value = dict(attrs).get("class") or ""
        return set(value.split())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attributes = dict(attrs)

        if tag == "ul":
            classes = self._classes(attrs)

            if not self.started and "wsite-menu-default" in classes:
                self.started = True
                self.target_ul_depth = 1
                self.root_items = []
                self.current_list = self.root_items
                return

            if self.started:
                self.target_ul_depth += 1
                self.list_stack.append(self.current_list)
                if self.li_stack:
                    self.current_list = self.li_stack[-1].children
                return

        if not self.started:
            return

        if tag == "li":
            item = MenuItem()
            self.current_list.append(item)
            self.li_stack.append(item)
            return

        if tag == "a" and self.li_stack:
            owner = self.li_stack[-1]
            if not owner.title:
                href = attributes.get("href")
                if href:
                    owner.href = href.strip()
                self.in_anchor = True
                self.anchor_text = []
                self.anchor_owner = owner

    def handle_data(self, data: str) -> None:
        if self.in_anchor:
            self.anchor_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()

        if not self.started:
            return

        if tag == "a" and self.in_anchor:
            title = " ".join("".join(self.anchor_text).split())
            if self.anchor_owner is not None and title:
                self.anchor_owner.title = title
            self.in_anchor = False
            self.anchor_text = []
            self.anchor_owner = None
            return

        if tag == "li" and self.li_stack:
            self.li_stack.pop()
            return

        if tag == "ul":
            self.target_ul_depth -= 1
            if self.target_ul_depth <= 0:
                self.started = False
                self.target_ul_depth = 0
                return
            if self.list_stack:
                self.current_list = self.list_stack.pop()


DEFAULT_MENU = [
    MenuItem("Home", "index.html"),
    MenuItem("Professor", "professor.html"),
    MenuItem(
        "Research",
        "research.html",
        [
            MenuItem("GFPc Analogs", "gfpc-analogs.html"),
            MenuItem(
                "Multi-Responsive Luminescent Material",
                "multi-responsive-luminescent-material.html",
            ),
            MenuItem("Molecular Machine", "molecular-machine.html"),
            MenuItem("Supercapacitor", "supercapacitor.html"),
        ],
    ),
    MenuItem("Members", "members.html"),
    MenuItem(
        "Publications",
        "publications.html",
        [
            MenuItem("1990-1999", "1990-1999.html"),
            MenuItem("2000-2004", "2000-2004.html"),
            MenuItem("2005-2009", "2005-2009.html"),
            MenuItem("2010-2014", "2010-2014.html"),
            MenuItem("2015-2019", "2015-2019.html"),
            MenuItem("2020-2024", "2020-2024.html"),
            MenuItem("Chinese articles", "chinese-articles.html"),
            MenuItem("Patent", "patent.html"),
        ],
    ),
    MenuItem("Photograph", "photograph.html"),
]


HEADER_CSS = r'''
<style id="standalone-header-style">
#static-site-header,
#static-site-header * { box-sizing: border-box; }

#static-site-header {
  position: absolute !important;
  top: 0 !important;
  right: 0 !important;
  left: 0 !important;
  z-index: 2147483000 !important;
  display: block !important;
  width: 100% !important;
  min-height: 86px !important;
  margin: 0 !important;
  padding: 0 !important;
  opacity: 1 !important;
  visibility: visible !important;
  overflow: visible !important;
  pointer-events: auto !important;
  background: linear-gradient(to bottom, rgba(0,0,0,.48) 0%, rgba(0,0,0,.17) 66%, rgba(0,0,0,0) 100%) !important;
  font-family: "Montserrat", Arial, sans-serif !important;
}

#static-site-header .static-header-inner {
  display: flex !important;
  align-items: center !important;
  justify-content: space-between !important;
  width: 100% !important;
  max-width: 1280px !important;
  min-height: 86px !important;
  margin: 0 auto !important;
  padding: 12px 34px !important;
  overflow: visible !important;
}

#static-site-header a { text-decoration: none !important; }

#static-site-header .static-site-brand {
  display: block !important;
  flex: 0 0 auto !important;
  margin: 0 34px 0 0 !important;
  padding: 8px 0 !important;
  color: #fff !important;
  opacity: 1 !important;
  visibility: visible !important;
  font-size: 24px !important;
  font-weight: 700 !important;
  line-height: 1.15 !important;
  letter-spacing: .035em !important;
  text-transform: uppercase !important;
  white-space: nowrap !important;
  text-shadow: 0 1px 4px rgba(0,0,0,.62) !important;
}

#static-site-header .static-main-nav {
  display: flex !important;
  align-items: center !important;
  justify-content: flex-end !important;
  flex: 1 1 auto !important;
  gap: 4px !important;
  margin: 0 !important;
  padding: 0 !important;
  opacity: 1 !important;
  visibility: visible !important;
  overflow: visible !important;
}

#static-site-header .static-nav-item,
#static-site-header .static-dropdown > a {
  display: block !important;
  margin: 0 !important;
  padding: 13px !important;
  color: #fff !important;
  opacity: 1 !important;
  visibility: visible !important;
  font-size: 14px !important;
  font-weight: 600 !important;
  line-height: 1.2 !important;
  letter-spacing: .035em !important;
  white-space: nowrap !important;
  text-shadow: 0 1px 3px rgba(0,0,0,.68) !important;
}

#static-site-header .static-nav-item:hover,
#static-site-header .static-nav-item:focus,
#static-site-header .static-dropdown > a:hover,
#static-site-header .static-dropdown > a:focus,
#static-site-header .is-current {
  color: #fff !important;
  background: rgba(255,255,255,.18) !important;
  outline: none !important;
}

#static-site-header .static-dropdown {
  position: relative !important;
  display: block !important;
  overflow: visible !important;
}

#static-site-header .static-dropdown-menu {
  position: absolute !important;
  top: calc(100% + 1px) !important;
  left: 0 !important;
  z-index: 2147483001 !important;
  display: none !important;
  width: max-content !important;
  min-width: 235px !important;
  margin: 0 !important;
  padding: 8px 0 !important;
  border-radius: 2px !important;
  background: rgba(25,34,43,.98) !important;
  box-shadow: 0 10px 28px rgba(0,0,0,.32) !important;
  opacity: 1 !important;
  visibility: visible !important;
}

#static-site-header .static-dropdown:hover .static-dropdown-menu,
#static-site-header .static-dropdown:focus-within .static-dropdown-menu {
  display: block !important;
}

#static-site-header .static-dropdown-menu a {
  display: block !important;
  padding: 10px 17px !important;
  color: #fff !important;
  font-size: 13px !important;
  font-weight: 500 !important;
  line-height: 1.35 !important;
  white-space: nowrap !important;
}

#static-site-header .static-dropdown-menu a:hover,
#static-site-header .static-dropdown-menu a:focus,
#static-site-header .static-dropdown-menu a.is-current {
  background: rgba(255,255,255,.15) !important;
  outline: none !important;
}

#static-site-header .static-menu-toggle {
  display: none !important;
  width: 46px !important;
  height: 42px !important;
  margin: 0 !important;
  padding: 7px !important;
  border: 1px solid rgba(255,255,255,.7) !important;
  border-radius: 3px !important;
  background: rgba(0,0,0,.22) !important;
  color: #fff !important;
  cursor: pointer !important;
}

#static-site-header .static-menu-toggle span,
#static-site-header .static-menu-toggle span::before,
#static-site-header .static-menu-toggle span::after {
  position: relative !important;
  display: block !important;
  width: 25px !important;
  height: 2px !important;
  margin: 0 auto !important;
  background: #fff !important;
  content: "" !important;
}

#static-site-header .static-menu-toggle span::before { position: absolute !important; top: -8px !important; }
#static-site-header .static-menu-toggle span::after { position: absolute !important; top: 8px !important; }
#navMobile { display: none !important; }

@media screen and (max-width: 980px) {
  #static-site-header .static-header-inner { padding-right: 20px !important; padding-left: 20px !important; }
  #static-site-header .static-site-brand { font-size: 20px !important; }
  #static-site-header .static-main-nav { gap: 0 !important; }
  #static-site-header .static-nav-item,
  #static-site-header .static-dropdown > a { padding-right: 8px !important; padding-left: 8px !important; font-size: 12px !important; }
}

@media screen and (max-width: 760px) {
  #static-site-header { min-height: 70px !important; background: rgba(25,34,43,.96) !important; }
  #static-site-header .static-header-inner { position: relative !important; min-height: 70px !important; padding: 10px 17px !important; }
  #static-site-header .static-site-brand { max-width: calc(100% - 65px) !important; margin-right: 10px !important; overflow: hidden !important; font-size: 18px !important; text-overflow: ellipsis !important; }
  #static-site-header .static-menu-toggle { display: block !important; flex: 0 0 auto !important; }
  #static-site-header .static-main-nav {
    position: absolute !important;
    top: 100% !important;
    right: 0 !important;
    left: 0 !important;
    z-index: 2147483002 !important;
    display: none !important;
    align-items: stretch !important;
    flex-direction: column !important;
    width: 100% !important;
    max-height: calc(100vh - 70px) !important;
    padding: 8px 13px 16px !important;
    overflow-x: hidden !important;
    overflow-y: auto !important;
    background: rgba(25,34,43,.99) !important;
    box-shadow: 0 12px 25px rgba(0,0,0,.32) !important;
  }
  #static-site-header .static-main-nav.is-open { display: flex !important; }
  #static-site-header .static-nav-item,
  #static-site-header .static-dropdown > a { width: 100% !important; padding: 12px 10px !important; font-size: 14px !important; }
  #static-site-header .static-dropdown-menu { position: static !important; display: block !important; width: 100% !important; min-width: 0 !important; padding: 0 0 5px 13px !important; background: transparent !important; box-shadow: none !important; }
  #static-site-header .static-dropdown-menu a { padding: 9px 12px !important; font-size: 13px !important; }
}
</style>
'''


HEADER_SCRIPT = r'''
<script id="static-header-script">
(function () {
  "use strict";
  var header = document.getElementById("static-site-header");
  if (!header) return;
  var button = header.querySelector(".static-menu-toggle");
  var navigation = header.querySelector(".static-main-nav");
  if (!button || !navigation) return;

  function closeMenu() {
    navigation.classList.remove("is-open");
    button.setAttribute("aria-expanded", "false");
  }

  button.addEventListener("click", function () {
    var open = navigation.classList.toggle("is-open");
    button.setAttribute("aria-expanded", open ? "true" : "false");
  });

  navigation.querySelectorAll("a").forEach(function (link) {
    link.addEventListener("click", function () {
      if (window.innerWidth <= 760) closeMenu();
    });
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") closeMenu();
  });

  window.addEventListener("resize", function () {
    if (window.innerWidth > 760) closeMenu();
  });
})();
</script>
'''


def clean_title(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    value = html_module.unescape(value)
    return " ".join(value.split()).strip()


def extract_site_title(source: str) -> str:
    match = re.search(
        r'<[^>]+id=["\']wsite-title["\'][^>]*>(.*?)</[^>]+>',
        source,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return "JYE-SHANE YANG"
    title = clean_title(match.group(1))
    return title or "JYE-SHANE YANG"


def extract_menu(source: str) -> list[MenuItem]:
    parser = WeeblyMenuParser()
    try:
        parser.feed(source)
    except Exception:
        return DEFAULT_MENU
    items = [
        item for item in parser.root_items
        if item.title and item.href and not item.href.lower().startswith("javascript:")
    ]
    return items or DEFAULT_MENU


def page_name_from_href(href: str) -> str:
    href = html_module.unescape(href.strip())
    return Path(urlsplit(href).path).name.lower()


def item_contains_page(item: MenuItem, page_name: str) -> bool:
    if page_name_from_href(item.href) == page_name:
        return True
    return any(item_contains_page(child, page_name) for child in item.children)


def render_menu_item(item: MenuItem, current_page: str) -> str:
    title = html_module.escape(item.title)
    href = html_module.escape(item.href, quote=True)
    current = item_contains_page(item, current_page)

    if not item.children:
        current_class = " is-current" if current else ""
        return f'<a class="static-nav-item{current_class}" href="{href}">{title}</a>'

    current_class = " is-current" if current else ""
    child_parts: list[str] = []
    for child in item.children:
        if not child.title:
            continue
        child_current = " is-current" if page_name_from_href(child.href) == current_page else ""
        child_parts.append(
            f'<a class="{child_current.strip()}" '
            f'href="{html_module.escape(child.href, quote=True)}">'
            f'{html_module.escape(child.title)}</a>'
        )
    child_html = "\n".join(child_parts)

    return (
        '<div class="static-dropdown">\n'
        f'  <a class="{current_class.strip()}" href="{href}">{title}</a>\n'
        '  <div class="static-dropdown-menu">\n'
        f'    {child_html}\n'
        '  </div>\n'
        '</div>'
    )


def render_header(site_title: str, menu: list[MenuItem], current_page: str) -> str:
    menu_html = "\n".join(render_menu_item(item, current_page) for item in menu if item.title)
    return (
        f'\n<header id="{HEADER_ID}">\n'
        '  <div class="static-header-inner">\n'
        f'    <a class="static-site-brand" href="index.html">{html_module.escape(site_title)}</a>\n'
        '    <button class="static-menu-toggle" type="button" '
        'aria-label="Open navigation menu" aria-controls="static-main-nav" '
        'aria-expanded="false"><span></span></button>\n'
        '    <nav id="static-main-nav" class="static-main-nav" aria-label="Main navigation">\n'
        f'      {menu_html}\n'
        '    </nav>\n'
        '  </div>\n'
        '</header>\n'
    )


def remove_existing_fix(source: str) -> str:
    source = re.sub(
        rf'\s*<style[^>]+id=["\']{re.escape(STYLE_ID)}["\'][^>]*>.*?</style>\s*',
        "\n", source, flags=re.IGNORECASE | re.DOTALL,
    )
    source = re.sub(
        rf'\s*<script[^>]+id=["\']{re.escape(SCRIPT_ID)}["\'][^>]*>.*?</script>\s*',
        "\n", source, flags=re.IGNORECASE | re.DOTALL,
    )
    return source


def find_original_header_range(source: str) -> tuple[int, int] | None:
    header_match = re.search(
        r'<div\b[^>]*class=["\'][^"\']*\bbirdseye-header\b[^"\']*["\'][^>]*>',
        source,
        flags=re.IGNORECASE,
    )
    if not header_match:
        return None

    for pattern in (
        r'<div\b[^>]*class=["\'][^"\']*\bbanner-wrap\b[^"\']*["\'][^>]*>',
        r'<div\b[^>]*class=["\'][^"\']*\bmain-wrap\b[^"\']*["\'][^>]*>',
    ):
        marker = re.search(pattern, source[header_match.end():], flags=re.IGNORECASE)
        if marker:
            return header_match.start(), header_match.end() + marker.start()
    return None


def find_static_header_range(source: str) -> tuple[int, int] | None:
    start_match = re.search(
        rf'<header\b[^>]*id=["\']{re.escape(HEADER_ID)}["\'][^>]*>',
        source,
        flags=re.IGNORECASE,
    )
    if not start_match:
        return None
    end_match = re.search(r'</header\s*>', source[start_match.end():], flags=re.IGNORECASE)
    if not end_match:
        return None
    return start_match.start(), start_match.end() + end_match.end()


def insert_before_closing_tag(source: str, tag: str, insertion: str) -> str:
    match = re.search(rf'</{re.escape(tag)}\s*>', source, flags=re.IGNORECASE)
    if not match:
        raise ValueError(f"找不到 </{tag}>")
    return source[:match.start()] + insertion + "\n" + source[match.start():]


def insert_after_body(source: str, insertion: str) -> str:
    match = re.search(r'<body\b[^>]*>', source, flags=re.IGNORECASE)
    if not match:
        raise ValueError("找不到 <body>")
    return source[:match.end()] + "\n" + insertion + source[match.end():]


def replace_http_weebly_resources(source: str) -> str:
    return (
        source
        .replace("http://cdn11.editmysite.com", "https://cdn11.editmysite.com")
        .replace("http://cdn2.editmysite.com", "https://cdn2.editmysite.com")
        .replace("http://cdn1.editmysite.com", "https://cdn1.editmysite.com")
    )


def process_file(path: Path, force: bool = False) -> tuple[str, str]:
    source = path.read_text(encoding="utf-8-sig", errors="replace")

    if HEADER_ID in source and STYLE_ID in source and not force:
        return "skipped", "已經修復過"

    site_title = extract_site_title(source)
    menu = extract_menu(source)
    current_page = path.name.lower()

    source = remove_existing_fix(source)
    source = replace_http_weebly_resources(source)

    header_range = find_original_header_range(source)
    if header_range is None:
        header_range = find_static_header_range(source)

    if header_range is not None:
        start, end = header_range
        source = source[:start] + source[end:]
    elif not force:
        return "skipped", "找不到 Weebly birdseye-header"

    source = insert_before_closing_tag(source, "head", HEADER_CSS)
    source = insert_after_body(source, render_header(site_title, menu, current_page))
    source = insert_before_closing_tag(source, "body", HEADER_SCRIPT)
    path.write_text(source, encoding="utf-8")
    return "changed", f"{len(menu)} 個主選單項目"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批次修復同一資料夾中所有 Weebly HTML 的上方導覽列。")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="網站根目錄；預設為程式所在資料夾。",
    )
    parser.add_argument("--recursive", action="store_true", help="遞迴掃描子資料夾。")
    parser.add_argument("--force", action="store_true", help="即使頁面已修復也重新產生。")
    parser.add_argument("--no-backup", action="store_true", help="不建立備份（不建議）。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.expanduser().resolve()

    if not root.is_dir():
        print(f"錯誤：找不到資料夾：{root}")
        return 2

    html_files = sorted(root.glob("**/*.html" if args.recursive else "*.html"))
    html_files += sorted(root.glob("**/*.htm" if args.recursive else "*.htm"))
    html_files = [
        path for path in html_files
        if path.is_file() and not any(part.startswith("_html_header_backup_") for part in path.parts)
    ]

    if not html_files:
        print(f"找不到 HTML：{root}")
        return 1

    backup_dir: Path | None = None
    if not args.no_backup:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = root / f"_html_header_backup_{timestamp}"
        backup_dir.mkdir(parents=True, exist_ok=False)
        for path in html_files:
            relative = path.relative_to(root)
            destination = backup_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
        print(f"已備份原始 HTML：{backup_dir}")

    changed = skipped = failed = 0
    print(f"找到 {len(html_files)} 個 HTML。\n")

    for index, path in enumerate(html_files, start=1):
        relative = path.relative_to(root)
        try:
            status, note = process_file(path, force=args.force)
            if status == "changed":
                changed += 1
                label = "已修復"
            else:
                skipped += 1
                label = "略過"
            print(f"[{index}/{len(html_files)}] {label}：{relative}（{note}）")
        except Exception as exc:
            failed += 1
            print(f"[{index}/{len(html_files)}] 失敗：{relative}（{type(exc).__name__}: {exc}）")

    print("\n========== 完成 ==========")
    print(f"已修復：{changed}")
    print(f"略過：{skipped}")
    print(f"失敗：{failed}")
    if backup_dir is not None:
        print(f"備份位置：{backup_dir}")

    if failed:
        print("\n部分頁面失敗；原始檔仍保存在備份資料夾。")
        return 1

    print("\n請將修改後的 HTML commit 到 GitHub，再用 Command + Option + R 強制重新整理。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
