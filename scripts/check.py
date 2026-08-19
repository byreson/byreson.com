#!/usr/bin/env python3
"""Run dependency-free structural checks against the generated RESON site."""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.references: list[tuple[str, str]] = []
        self.title_count = 0
        self.main_count = 0
        self.h1_count = 0
        self.html_lang = ""
        self.images_without_alt = 0
        self.json_ld: list[str] = []
        self._json_buffer: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "html":
            self.html_lang = values.get("lang") or ""
        if tag == "main":
            self.main_count += 1
        if tag == "h1":
            self.h1_count += 1
        if tag == "title":
            self.title_count += 1
        if "id" in values and values["id"]:
            self.ids.append(str(values["id"]))
        if tag in {"a", "link"} and values.get("href"):
            self.references.append(("href", str(values["href"])))
        if tag in {"img", "script"} and values.get("src"):
            self.references.append(("src", str(values["src"])))
        if tag == "img" and "alt" not in values:
            self.images_without_alt += 1
        if tag == "script" and values.get("type") == "application/ld+json":
            self._json_buffer = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._json_buffer is not None:
            self.json_ld.append("".join(self._json_buffer))
            self._json_buffer = None

    def handle_data(self, data: str) -> None:
        if self._json_buffer is not None:
            self._json_buffer.append(data)


def parse_page(path: Path) -> PageParser:
    parser = PageParser()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    return parser


def route_file(route: str) -> Path:
    clean = unquote(route).lstrip("/")
    candidate = DIST / clean
    if not clean or route.endswith("/"):
        return candidate / "index.html"
    return candidate


def check_html(errors: list[str]) -> int:
    pages = sorted(DIST.rglob("*.html"))
    parsed = {page: parse_page(page) for page in pages}

    for page, parser in parsed.items():
        label = page.relative_to(DIST)
        duplicates = sorted({item for item in parser.ids if parser.ids.count(item) > 1})
        if duplicates:
            errors.append(f"{label}: duplicate ids: {', '.join(duplicates)}")
        if parser.html_lang != "en":
            errors.append(f"{label}: expected html lang=\"en\"")
        if parser.title_count != 1:
            errors.append(f"{label}: expected one title, found {parser.title_count}")
        if parser.main_count != 1:
            errors.append(f"{label}: expected one main, found {parser.main_count}")
        if parser.h1_count != 1:
            errors.append(f"{label}: expected one h1, found {parser.h1_count}")
        if parser.images_without_alt:
            errors.append(f"{label}: {parser.images_without_alt} image(s) lack alt attributes")

        for payload in parser.json_ld:
            try:
                json.loads(payload)
            except json.JSONDecodeError as exc:
                errors.append(f"{label}: invalid JSON-LD: {exc}")

        for attribute, reference in parser.references:
            parsed_url = urlparse(reference)
            if parsed_url.scheme in {"http", "https", "mailto", "data"} or reference.startswith("//"):
                continue
            target_route = parsed_url.path
            if not target_route:
                target = page
            elif target_route.startswith("/"):
                target = route_file(target_route)
            else:
                target = (page.parent / target_route).resolve()
                if target_route.endswith("/"):
                    target /= "index.html"
            if not target.exists():
                errors.append(f"{label}: broken {attribute} reference {reference!r}")
                continue
            if parsed_url.fragment and target.suffix.lower() == ".html":
                target_parser = parsed.get(target) or parse_page(target)
                if parsed_url.fragment not in target_parser.ids:
                    errors.append(f"{label}: missing fragment #{parsed_url.fragment} in {target.relative_to(DIST)}")

    homepage = (DIST / "index.html").read_text(encoding="utf-8") if (DIST / "index.html").exists() else ""
    for required in ('href="style.css"', 'href="content.css"', 'src="script.js"'):
        if required not in homepage:
            errors.append(f"index.html: missing required link {required}")
    return len(pages)


def check_generated_data(errors: list[str]) -> None:
    for name in ("rss.xml", "feed.xml", "sitemap.xml"):
        try:
            ET.parse(DIST / name)
        except (OSError, ET.ParseError) as exc:
            errors.append(f"{name}: invalid XML: {exc}")

    try:
        search = json.loads((DIST / "search-index.json").read_text(encoding="utf-8"))
        if not isinstance(search, list):
            errors.append("search-index.json: root value must be an array")
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"search-index.json: invalid JSON: {exc}")


def check_source_hygiene(errors: list[str]) -> int:
    extensions = {".html", ".css", ".js", ".py", ".md", ".json", ".xml", ".txt"}
    checked = 0
    # .private holds working material that is never committed, rendered, or published.
    # The checker does not read it either, so private text can never reach an error message.
    ignored_roots = {".git", ".private", "dist", "__pycache__"}
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in extensions:
            continue
        if any(part in ignored_roots for part in path.relative_to(ROOT).parts):
            continue
        if path.name.startswith("OFL-"):
            continue  # Preserve upstream licence text byte-for-byte.
        checked += 1
        text = path.read_text(encoding="utf-8")
        if "\r" in text:
            errors.append(f"{path.relative_to(ROOT)}: use LF line endings")
        for number, line in enumerate(text.splitlines(), start=1):
            if line.rstrip() != line:
                errors.append(f"{path.relative_to(ROOT)}:{number}: trailing whitespace")
        if path.name in {"style.css", "content.css"}:
            without_comments = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
            if without_comments.count("{") != without_comments.count("}"):
                errors.append(f"{path.relative_to(ROOT)}: unbalanced CSS braces")
    return checked


def main() -> int:
    if not DIST.is_dir():
        print("Check failed: dist/ does not exist; run python build.py first.", file=sys.stderr)
        return 1

    errors: list[str] = []
    page_count = check_html(errors)
    check_generated_data(errors)
    source_count = check_source_hygiene(errors)

    leaked = []
    for path in DIST.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".html", ".xml", ".json", ".css", ".js"}:
            text = path.read_text(encoding="utf-8")
            if "TODO(RESON)" in text or "draft: true" in text:
                leaked.append(str(path.relative_to(DIST)))
    if leaked:
        errors.append(f"Draft markers leaked into: {', '.join(leaked)}")

    if errors:
        print("Checks failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Checks passed: {page_count} HTML pages and {source_count} source files inspected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
