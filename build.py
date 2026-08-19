#!/usr/bin/env python3
"""Build the static RESON site from portable content files.

The builder intentionally uses only Python's standard library. It is small enough
to audit, keeps published content as the single source of truth, and produces
plain static files under dist/.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import struct
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from email.utils import format_datetime
from pathlib import Path
from string import Template
from typing import Any, Iterable
from urllib.parse import quote, urlparse


ROOT = Path(__file__).resolve().parent
CONTENT_DIR = ROOT / "content"
TEMPLATE_DIR = ROOT / "templates"
DEFAULT_OUTPUT = ROOT / "dist"
BASE_URL = "https://byreson.com"
TEXT_ENCODING = "utf-8"
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FOOTER_HTML = (TEMPLATE_DIR / "footer.html").read_text(encoding=TEXT_ENCODING).strip()


@dataclass(frozen=True)
class Entry:
    kind: str
    slug: str
    title: str
    description: str
    published: date | None
    updated: date | None
    topics: tuple[str, ...]
    featured: bool
    image: str
    image_alt: str
    html_body: str
    plain_body: str
    metadata: dict[str, Any]
    source: Path

    @property
    def url(self) -> str:
        prefix = "writing" if self.kind == "writing" else "work"
        return f"/{prefix}/{self.slug}/"


class ContentError(ValueError):
    """Raised when source content would produce an unsafe or inconsistent site."""


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding=TEXT_ENCODING))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContentError(f"Could not read valid JSON from {path.relative_to(ROOT)}: {exc}") from exc


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.lower() in {"null", "none"}:
        return None
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [] if not inner else [parse_scalar(item) for item in inner.split(",")]
    if value.startswith('"') and value.endswith('"'):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


def parse_front_matter(source: str, path: Path | None = None) -> tuple[dict[str, Any], str]:
    lines = source.replace("\r\n", "\n").split("\n")
    label = str(path.relative_to(ROOT)) if path and path.is_relative_to(ROOT) else str(path or "content")
    if not lines or lines[0].strip() != "---":
        raise ContentError(f"{label} must begin with YAML-style front matter")

    try:
        end_index = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration as exc:
        raise ContentError(f"{label} is missing the closing front-matter delimiter") from exc

    metadata: dict[str, Any] = {}
    front_lines = lines[1:end_index]
    index = 0
    while index < len(front_lines):
        line = front_lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        if line.startswith((" ", "\t")) or ":" not in line:
            raise ContentError(f"Invalid front-matter line in {label}: {line!r}")

        key, raw_value = line.split(":", 1)
        key = key.strip()
        if not re.fullmatch(r"[a-z_][a-z0-9_]*", key):
            raise ContentError(f"Invalid front-matter key in {label}: {key!r}")

        if raw_value.strip():
            metadata[key] = parse_scalar(raw_value)
            index += 1
            continue

        values: list[Any] = []
        index += 1
        while index < len(front_lines) and re.match(r"^\s+-\s+", front_lines[index]):
            values.append(parse_scalar(re.sub(r"^\s+-\s+", "", front_lines[index], count=1)))
            index += 1
        metadata[key] = values

    body = "\n".join(lines[end_index + 1 :]).strip()
    return metadata, body


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def parse_date(value: Any, field: str, path: Path) -> date:
    if not isinstance(value, str) or not value:
        raise ContentError(f"{path.relative_to(ROOT)} requires a YYYY-MM-DD {field}")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ContentError(f"Invalid {field} in {path.relative_to(ROOT)}: {value!r}") from exc


def normalise_topics(value: Any, path: Path) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ContentError(f"{path.relative_to(ROOT)} requires at least one topic")
    topics = tuple(dict.fromkeys(slugify(str(topic)) for topic in value if str(topic).strip()))
    if not topics or any(not SLUG_PATTERN.fullmatch(topic) for topic in topics):
        raise ContentError(f"Invalid topics in {path.relative_to(ROOT)}")
    return topics


def safe_url(value: str) -> str:
    value = value.strip()
    parsed = urlparse(value)
    if parsed.scheme and parsed.scheme not in {"http", "https", "mailto"}:
        raise ContentError(f"Unsupported URL scheme in content: {value!r}")
    if value.startswith("//"):
        raise ContentError(f"Protocol-relative URLs are not allowed: {value!r}")
    return value


JPEG_SIZE_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def asset_url(value: str) -> str:
    """Normalise a content-authored image path into a safe, root-relative URL."""
    raw = safe_url(value)
    if not raw or raw.startswith(("http://", "https://")):
        return raw
    if not raw.startswith("/"):
        raw = "/" + raw
    return quote(raw, safe="/")


def image_size(value: str) -> tuple[int, int] | None:
    """Read intrinsic pixel dimensions from a local PNG or JPEG.

    Emitting real width/height lets the browser reserve space before the file
    arrives, which removes layout shift without any build-time image pipeline.
    """
    raw = value.strip()
    if not raw or raw.startswith(("http://", "https://")):
        return None
    candidate = ROOT / raw.lstrip("/")
    if not candidate.is_file():
        return None
    try:
        with candidate.open("rb") as handle:
            header = handle.read(32)
            if header[:8] == b"\x89PNG\r\n\x1a\n":
                width, height = struct.unpack(">II", header[16:24])
                return int(width), int(height)
            if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
                chunk = header[12:16]
                if chunk == b"VP8 ":
                    width, height = struct.unpack("<HH", header[26:30])
                    return int(width) & 0x3FFF, int(height) & 0x3FFF
                if chunk == b"VP8L":
                    bits = int.from_bytes(header[21:25], "little")
                    return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
                if chunk == b"VP8X":
                    width = int.from_bytes(header[24:27], "little") + 1
                    height = int.from_bytes(header[27:30], "little") + 1
                    return width, height
                return None
            if header[:2] == b"\xff\xd8":
                handle.seek(2)
                while True:
                    marker = handle.read(2)
                    if len(marker) < 2 or marker[0] != 0xFF:
                        return None
                    if marker[1] in JPEG_SIZE_MARKERS:
                        handle.read(3)
                        height, width = struct.unpack(">HH", handle.read(4))
                        return int(width), int(height)
                    (length,) = struct.unpack(">H", handle.read(2))
                    handle.seek(length - 2, 1)
    except (OSError, struct.error):
        return None
    return None


def render_image(source: str, alt: str, *, eager: bool = False, sizes: str = "") -> str:
    """One image element for every route, with intrinsic size and honest alt text."""
    url = asset_url(source)
    if not url:
        return ""
    dimensions = image_size(source)
    size_attributes = f' width="{dimensions[0]}" height="{dimensions[1]}"' if dimensions else ""
    loading = ' fetchpriority="high"' if eager else ' loading="lazy"'
    sizes_attribute = f' sizes="{html.escape(sizes, quote=True)}"' if sizes else ""
    return (
        f'<img src="{html.escape(url, quote=True)}" alt="{html.escape(alt, quote=True)}"'
        f'{size_attributes}{sizes_attribute}{loading} decoding="async">'
    )


def render_inline(value: str) -> str:
    tokens: dict[str, str] = {}

    def stash(markup: str) -> str:
        token = f"@@RESON{len(tokens)}@@"
        tokens[token] = markup
        return token

    working = re.sub(
        r"`([^`]+)`",
        lambda match: stash(f"<code>{html.escape(match.group(1))}</code>"),
        value,
    )

    def image_replacement(match: re.Match[str]) -> str:
        url = match.group(2) if match.group(2) is not None else match.group(3)
        return stash(render_image(url, match.group(1)))

    working = re.sub(BLOCK_IMAGE_PATTERN, image_replacement, working)

    def link_replacement(match: re.Match[str]) -> str:
        label, url = match.group(1), safe_url(match.group(2))
        external = url.startswith(("http://", "https://"))
        attributes = ' class="external-link" rel="noopener noreferrer"' if external else ""
        return stash(
            f'<a href="{html.escape(url, quote=True)}"{attributes}>{html.escape(label)}</a>'
        )

    working = re.sub(r"\[([^\]]+)\]\(([^\s\)]+)\)", link_replacement, working)
    rendered = html.escape(working, quote=False)
    rendered = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", rendered)
    rendered = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", rendered)
    rendered = re.sub(r"(?<!_)_([^_]+)_(?!_)", r"<em>\1</em>", rendered)

    for token, markup in tokens.items():
        rendered = rendered.replace(token, markup)
    return rendered


def is_block_start(line: str) -> bool:
    stripped = line.strip()
    return bool(
        not stripped
        or stripped.startswith(("```", "#", "> "))
        or re.match(r"^[-*+]\s+", stripped)
        or re.match(r"^\d+\.\s+", stripped)
        or re.fullmatch(r"(?:---+|\*\*\*+|___+)", stripped)
        or bool(re.fullmatch(BLOCK_IMAGE_PATTERN, stripped))
        or bool(MEDIA_DIRECTIVE_START.match(stripped))
    )


# A path may be bare, or wrapped in <> when it contains spaces (CommonMark).
BLOCK_IMAGE_PATTERN = r"!\[([^\]]*)\]\(\s*(?:<([^>]+)>|([^\s\)]+))(?:\s+\"([^\"]+)\")?\s*\)"

MEDIA_DIRECTIVE_START = re.compile(r"^\{\{\s*(image|video)\b")
MEDIA_ATTRIBUTE = re.compile(r'([a-z_]+)\s*=\s*"([^"]*)"')
MEDIA_SIZES = {"normal", "wide"}

# Only these providers may ever become an iframe. Anything else is a build error,
# so article Markdown can never inject an arbitrary embed.
VIDEO_PROVIDERS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "YouTube",
        re.compile(
            r"^https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/)|youtu\.be/)"
            r"(?P<id>[A-Za-z0-9_-]{11})"
        ),
        "https://www.youtube-nocookie.com/embed/{id}",
    ),
    (
        "Vimeo",
        re.compile(r"^https?://(?:www\.)?vimeo\.com/(?:video/)?(?P<id>\d+)"),
        "https://player.vimeo.com/video/{id}",
    ),
)


def parse_media_attributes(body: str, kind: str, allowed: set[str]) -> dict[str, str]:
    attributes: dict[str, str] = {}
    for match in MEDIA_ATTRIBUTE.finditer(body):
        key, value = match.group(1), match.group(2)
        if key not in allowed:
            raise ContentError(
                f"Unknown {kind} option {key!r}. Supported: {', '.join(sorted(allowed))}"
            )
        attributes[key] = value.strip()
    leftovers = MEDIA_ATTRIBUTE.sub("", body).replace("}}", "").strip()
    leftovers = re.sub(r"^\{\{\s*(image|video)\b", "", leftovers).strip()
    if leftovers:
        raise ContentError(f"Could not parse {kind} directive near: {leftovers[:60]!r}")
    return attributes


def render_media_image(attributes: dict[str, str]) -> str:
    source = attributes.get("src", "").strip()
    if not source:
        raise ContentError("An image directive requires src")
    if "alt" not in attributes:
        raise ContentError(
            f"The image {source!r} requires alt. Use alt=\"\" only for a decorative image."
        )
    size = attributes.get("size", "normal").strip() or "normal"
    if size not in MEDIA_SIZES:
        raise ContentError(f"Unsupported image size {size!r}. Use: {', '.join(sorted(MEDIA_SIZES))}")

    caption = attributes.get("caption", "").strip()
    caption_markup = f"<figcaption>{render_inline(caption)}</figcaption>" if caption else ""
    sizes = "(max-width: 44rem) 100vw, 90vw" if size == "wide" else "(max-width: 44rem) 100vw, 46rem"
    classes = "article-media" + (" media-wide" if size == "wide" else "")
    return f'<figure class="{classes}">{render_image(source, attributes["alt"], sizes=sizes)}{caption_markup}</figure>'


def render_media_video(attributes: dict[str, str]) -> str:
    source = attributes.get("src", "").strip()
    url = attributes.get("url", "").strip()
    if source and url:
        raise ContentError("A video directive takes either src (local file) or url (provider), not both")
    if not source and not url:
        raise ContentError("A video directive requires src or url")

    size = attributes.get("size", "normal").strip() or "normal"
    if size not in MEDIA_SIZES:
        raise ContentError(f"Unsupported video size {size!r}. Use: {', '.join(sorted(MEDIA_SIZES))}")
    caption = attributes.get("caption", "").strip()
    caption_markup = f"<figcaption>{render_inline(caption)}</figcaption>" if caption else ""
    classes = "article-media" + (" media-wide" if size == "wide" else "")

    if source:
        # Local file: native controls, metadata only, and never autoplay or loop.
        poster = attributes.get("poster", "").strip()
        poster_markup = f' poster="{html.escape(asset_url(poster), quote=True)}"' if poster else ""
        track = attributes.get("captions", "").strip()
        track_markup = ""
        if track:
            track_markup = (
                f'<track kind="captions" src="{html.escape(asset_url(track), quote=True)}" '
                f'srclang="en" label="English" default>'
            )
        return (
            f'<figure class="{classes}"><video controls playsinline preload="metadata"'
            f'{poster_markup} src="{html.escape(asset_url(source), quote=True)}">{track_markup}'
            "Your browser cannot play this video."
            f"</video>{caption_markup}</figure>"
        )

    title = attributes.get("title", "").strip() or caption
    if not title:
        raise ContentError(f"The embedded video {url!r} requires a title (or a caption) for accessibility")
    for name, pattern, template in VIDEO_PROVIDERS:
        match = pattern.match(url)
        if match:
            embed = template.format(id=match.group("id"))
            return (
                f'<figure class="{classes}"><div class="video-embed">'
                f'<iframe src="{html.escape(embed, quote=True)}" '
                f'title="{html.escape(title, quote=True)}" loading="lazy" '
                'referrerpolicy="strict-origin-when-cross-origin" '
                'allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture" '
                "allowfullscreen></iframe></div>"
                f"{caption_markup}</figure>"
            )
    supported = ", ".join(name for name, _, _ in VIDEO_PROVIDERS)
    raise ContentError(f"Unsupported video provider for {url!r}. Supported: {supported}")


def parse_media_directive(lines: list[str], index: int) -> tuple[str, int]:
    """Read a `{{ image ... }}` or `{{ video ... }}` block and render it."""
    kind = MEDIA_DIRECTIVE_START.match(lines[index].strip()).group(1)
    collected: list[str] = []
    closed = False
    while index < len(lines):
        current = lines[index].strip()
        collected.append(current)
        index += 1
        if current.endswith("}}"):
            closed = True
            break
    if not closed:
        raise ContentError(f"Unclosed {{{{ {kind} }}}} directive")

    body = " ".join(collected)
    if kind == "image":
        allowed = {"src", "alt", "caption", "size"}
        return render_media_image(parse_media_attributes(body, kind, allowed)), index
    allowed = {"src", "url", "poster", "caption", "title", "size", "captions"}
    return render_media_video(parse_media_attributes(body, kind, allowed)), index


def markdown_to_html(markdown: str) -> str:
    lines = markdown.replace("\r\n", "\n").split("\n")
    output: list[str] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            index += 1
            continue

        if stripped.startswith("```"):
            language = re.sub(r"[^a-zA-Z0-9_-]", "", stripped[3:].strip())
            code_lines: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            if index == len(lines):
                raise ContentError("Unclosed fenced code block")
            language_class = f' class="language-{language}"' if language else ""
            output.append(f"<pre><code{language_class}>{html.escape(chr(10).join(code_lines))}</code></pre>")
            index += 1
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            level = min(len(heading.group(1)) + 1, 6)
            text = heading.group(2).strip()
            heading_id = slugify(re.sub(r"[*_`]", "", text))
            output.append(f'<h{level} id="{heading_id}">{render_inline(text)}</h{level}>')
            index += 1
            continue

        if re.fullmatch(r"(?:---+|\*\*\*+|___+)", stripped):
            output.append("<hr>")
            index += 1
            continue

        if stripped.startswith("> "):
            quote_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("> "):
                quote_lines.append(lines[index].strip()[2:])
                index += 1
            output.append(f"<blockquote><p>{render_inline(' '.join(quote_lines))}</p></blockquote>")
            continue

        unordered = re.match(r"^[-*+]\s+(.+)$", stripped)
        ordered = re.match(r"^\d+\.\s+(.+)$", stripped)
        if unordered or ordered:
            tag = "ul" if unordered else "ol"
            items: list[str] = []
            pattern = r"^[-*+]\s+(.+)$" if unordered else r"^\d+\.\s+(.+)$"
            while index < len(lines):
                match = re.match(pattern, lines[index].strip())
                if not match:
                    break
                items.append(f"<li>{render_inline(match.group(1))}</li>")
                index += 1
            output.append(f"<{tag}>{''.join(items)}</{tag}>")
            continue

        if MEDIA_DIRECTIVE_START.match(stripped):
            markup, index = parse_media_directive(lines, index)
            output.append(markup)
            continue

        image = re.fullmatch(BLOCK_IMAGE_PATTERN, stripped)
        if image:
            alt = image.group(1)
            url = image.group(2) if image.group(2) is not None else image.group(3)
            caption = image.group(4)
            caption_markup = f"<figcaption>{render_inline(caption)}</figcaption>" if caption else ""
            output.append(
                f'<figure class="article-media">{render_image(url, alt)}{caption_markup}</figure>'
            )
            index += 1
            continue

        paragraph_lines = [stripped]
        index += 1
        while index < len(lines) and not is_block_start(lines[index]):
            paragraph_lines.append(lines[index].strip())
            index += 1
        output.append(f"<p>{render_inline(' '.join(paragraph_lines))}</p>")

    return "\n".join(output)


def plain_text_from_html(markup: str) -> str:
    text = re.sub(r"<[^>]+>", " ", markup)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def load_entries(directory: Path, kind: str) -> list[Entry]:
    entries: list[Entry] = []
    if not directory.exists():
        return entries

    for path in sorted(directory.glob("*.md")):
        if path.name.startswith("_"):
            continue
        metadata, body = parse_front_matter(path.read_text(encoding=TEXT_ENCODING), path)
        if bool(metadata.get("draft", True)) or bool(metadata.get("demo", False)):
            continue
        if "TODO(RESON)" in body:
            raise ContentError(f"Published content contains a TODO in {path.relative_to(ROOT)}")

        title = str(metadata.get("title", "")).strip()
        description = str(metadata.get("description", "")).strip()
        if not title or not description:
            raise ContentError(f"{path.relative_to(ROOT)} requires title and description")

        slug = slugify(str(metadata.get("slug", path.stem)))
        if not SLUG_PATTERN.fullmatch(slug):
            raise ContentError(f"Invalid slug for {path.relative_to(ROOT)}")

        published_value = metadata.get("date", metadata.get("published"))
        if kind == "writing" and not published_value:
            raise ContentError(f"{path.relative_to(ROOT)} requires a YYYY-MM-DD date")
        published = parse_date(published_value, "date", path) if published_value else None
        updated_value = metadata.get("updated")
        updated = parse_date(updated_value, "updated", path) if updated_value else None
        topics = normalise_topics(metadata.get("topics"), path)
        image = str(metadata.get("image", "")).strip()
        image_alt = str(metadata.get("image_alt", "")).strip()
        if image:
            safe_url(image)
            if not image_alt:
                raise ContentError(f"{path.relative_to(ROOT)} requires image_alt when image is set")

        rendered = markdown_to_html(body)
        entries.append(
            Entry(
                kind=kind,
                slug=slug,
                title=title,
                description=description,
                published=published,
                updated=updated,
                topics=topics,
                featured=bool(metadata.get("featured", False)),
                image=image,
                image_alt=image_alt,
                html_body=rendered,
                plain_body=plain_text_from_html(rendered),
                metadata=metadata,
                source=path,
            )
        )

    slugs = [entry.slug for entry in entries]
    if len(slugs) != len(set(slugs)):
        raise ContentError(f"Duplicate published {kind} slug")
    return sorted(entries, key=lambda entry: (entry.published or date.min, entry.slug), reverse=True)


def human_date(value: date) -> str:
    return f"{value.day} {value.strftime('%B %Y')}"


def entry_sort_date(entry: Entry) -> date:
    """Return a stable sort key without inventing dates for undated projects."""
    return entry.updated or entry.published or date.min


def absolute_url(path: str) -> str:
    return f"{BASE_URL}{path}"


def topic_chips(topics: Iterable[str], topic_titles: dict[str, str], available: set[str]) -> str:
    chips: list[str] = []
    for topic in topics:
        label = topic_titles.get(topic, topic.replace("-", " ").title())
        if topic in available:
            chips.append(f'<a href="/explore/{topic}/">{html.escape(label)}</a>')
        else:
            chips.append(f"<span>{html.escape(label)}</span>")
    return '<div class="topic-chips" aria-label="Topics">' + "".join(chips) + "</div>"


def writing_rows(entries: Iterable[Entry], topic_titles: dict[str, str]) -> str:
    rows: list[str] = []
    for entry in entries:
        if not entry.published:
            raise ContentError(f"Writing entry {entry.slug!r} is missing its publication date")
        labels = " · ".join(topic_titles.get(topic, topic.replace("-", " ").title()) for topic in entry.topics)
        row_class = "writing-row has-image" if entry.image else "writing-row"
        image_markup = ""
        if entry.image:
            picture = render_image(entry.image, entry.image_alt, sizes="(max-width: 44rem) 100vw, 12rem")
            image_markup = f'<div class="writing-row-image">{picture}</div>'
        rows.append(
            f'<article class="{row_class}">'
            f'{image_markup}'
            f'<div class="writing-row-meta"><time datetime="{entry.published.isoformat()}">{human_date(entry.published)}</time>'
            f"<span>{html.escape(labels)}</span></div>"
            f'<h2><a href="{entry.url}">{html.escape(entry.title)}</a></h2>'
            f"<p>{html.escape(entry.description)}</p>"
            "</article>"
        )
    return "\n".join(rows)


def rank_related(entry: Entry, entries: Iterable[Entry], limit: int = 3) -> list[Entry]:
    candidates: list[tuple[int, date, Entry]] = []
    source_topics = set(entry.topics)
    for candidate in entries:
        if candidate.slug == entry.slug:
            continue
        score = len(source_topics.intersection(candidate.topics))
        if score:
            candidates.append((score, entry_sort_date(candidate), candidate))
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in candidates[:limit]]


def page_json_ld(title: str, description: str, url: str, page_type: str = "WebPage") -> str:
    payload = {
        "@context": "https://schema.org",
        "@type": page_type,
        "name": title,
        "description": description,
        "url": absolute_url(url),
        "isPartOf": {"@id": f"{BASE_URL}/#website"},
        "inLanguage": "en",
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def entry_json_ld(entry: Entry) -> str:
    payload: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "Article" if entry.kind == "writing" else "CreativeWork",
        "headline": entry.title,
        "description": entry.description,
        "mainEntityOfPage": absolute_url(entry.url),
        "url": absolute_url(entry.url),
        "author": {"@id": f"{BASE_URL}/#person"},
        "keywords": list(entry.topics),
        "inLanguage": "en",
    }
    if entry.updated:
        payload["dateModified"] = entry.updated.isoformat()
    if entry.image:
        payload["image"] = absolute_url(entry.image) if entry.image.startswith("/") else entry.image
    if entry.published:
        payload["datePublished"] = entry.published.isoformat()
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def render_base(
    template: Template,
    *,
    title: str,
    description: str,
    canonical_path: str,
    main: str,
    active: str = "",
    body_class: str = "",
    structured_data: str = "",
    social_image: str = "",
    og_type: str = "website",
    preload_newsreader: bool = False,
) -> str:
    title_full = title if title.endswith("— RESON") else f"{title} — RESON"
    social_markup = ""
    twitter_card = "summary"
    if social_image:
        image_url = absolute_url(social_image) if social_image.startswith("/") else social_image
        social_markup = (
            f'<meta property="og:image" content="{html.escape(image_url, quote=True)}">\n'
            f'    <meta property="og:image:alt" content="{html.escape(title, quote=True)}">\n'
            f'    <meta name="twitter:image" content="{html.escape(image_url, quote=True)}">'
        )
        twitter_card = "summary_large_image"

    head_extra = ""
    if preload_newsreader:
        head_extra = (
            '<link rel="preload" href="/assets/fonts/newsreader-latin-variable.woff2" '
            'as="font" type="font/woff2" crossorigin>'
        )

    current = {name: (' aria-current="page"' if active == name else "") for name in ("work", "writing", "explore", "about")}
    return template.substitute(
        lang="en",
        title=html.escape(title_full),
        description=html.escape(description, quote=True),
        canonical=html.escape(absolute_url(canonical_path), quote=True),
        og_type=og_type,
        twitter_card=twitter_card,
        social_meta=social_markup,
        structured_data=(f'<script type="application/ld+json">{structured_data}</script>' if structured_data else ""),
        head_extra=head_extra,
        body_class=html.escape(body_class, quote=True),
        main=main,
        work_current=current["work"],
        writing_current=current["writing"],
        explore_current=current["explore"],
        about_current=current["about"],
        footer=FOOTER_HTML,
    )


def replace_region(source: str, name: str, content: str) -> str:
    pattern = re.compile(
        rf"(<!-- RESON_{re.escape(name)}_START -->).*?(<!-- RESON_{re.escape(name)}_END -->)",
        re.DOTALL,
    )
    if not pattern.search(source):
        raise ContentError(f"index.html is missing the RESON_{name} build markers")
    return pattern.sub(rf"\1\n{content}\n          \2", source, count=1)


def published_now_items(now_data: dict[str, Any]) -> list[tuple[str, str, bool]]:
    items = now_data.get("items", [])
    if not isinstance(items, list):
        raise ContentError("content/now.json items must be a list")
    if bool(now_data.get("demo", False)):
        return []
    published: list[tuple[str, str, bool]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ContentError("Every Now item must be an object")
        label = str(item.get("label", "")).strip()
        value = str(item.get("value", "")).strip()
        if label and value:
            published.append((label, value, bool(item.get("wide", False))))
    return published


def render_now_items(now_data: dict[str, Any]) -> str:
    published = published_now_items(now_data)
    if not published:
        return (
            '<div class="empty-state"><p class="eyebrow">Nothing here yet</p>'
            '<h2>The snapshot is still being written.</h2>'
            '<p>This stays empty until there is something real to record.</p></div>'
        )
    rendered: list[str] = ['<dl class="now-grid">']
    for label, value, wide in published:
        wide_class = " now-item-wide" if wide else ""
        rendered.append(
            f'<div class="now-item{wide_class}"><dt>{html.escape(label)}</dt><dd>{html.escape(value)}</dd></div>'
        )
    rendered.append("</dl>")
    return "\n".join(rendered)


def topic_description(topic: dict[str, Any]) -> str:
    if bool(topic.get("demo", False)):
        return ""
    return str(topic.get("description", "")).strip()


def render_home_work(entries: list[Entry]) -> str:
    selected = sorted(entries, key=lambda entry: (entry.featured, entry_sort_date(entry)), reverse=True)[:2]
    if not selected:
        return (
            '<div class="empty-state"><p class="eyebrow">Work in progress</p>'
            '<h3>The project room is taking shape.</h3></div>'
        )
    rows: list[str] = ['<div class="project-list">']
    for index, entry in enumerate(selected, start=1):
        detail = project_meta(entry)
        screenshot = project_screenshot(entry, lazy=True)
        rows.append(
            '<article class="project">'
            f'{screenshot}'
            f'<p class="project-number" aria-hidden="true">{index:02d}</p><div class="project-body">'
            f'{f"<p class=\"eyebrow\">{html.escape(detail)}</p>" if detail else ""}'
            f'<h3><a href="{entry.url}">{html.escape(entry.title)}</a></h3>'
            f'<p>{html.escape(entry.description)}</p>'
            f'<a class="project-link text-link" href="{entry.url}">View project</a></div></article>'
        )
    rows.append("</div>")
    return "\n".join(rows)


def render_home_explore(topics: list[dict[str, Any]], available: set[str], limit: int | None = None) -> str:
    """The homepage teaser lists every primary topic. A truncated map is a misleading map."""
    links: list[str] = []
    for topic in topics if limit is None else topics[:limit]:
        topic_id = str(topic["id"])
        title = str(topic["title"])
        href = f"/explore/{topic_id}/" if topic_id in available else f"/explore/#{topic_id}"
        links.append(f'<a href="{href}">{html.escape(title)}</a>')
    return '<nav class="interest-field" aria-label="Explore interests">' + "".join(links) + "</nav>"


def project_meta(entry: Entry) -> str:
    context = str(entry.metadata.get("context", "")).strip()
    year = str(entry.metadata.get("year", "")).strip()
    status = str(entry.metadata.get("status", "")).strip()
    return " · ".join(value for value in (context, year, status) if value)


def project_screenshot(entry: Entry, *, lazy: bool, sizes: str = "") -> str:
    if not entry.image:
        return ""
    picture = render_image(entry.image, entry.image_alt, eager=not lazy, sizes=sizes)
    return f'<figure class="project-screenshot">{picture}</figure>'


def project_live_link(entry: Entry) -> str:
    live_url = str(entry.metadata.get("live_url", "")).strip()
    if not live_url:
        return ""
    return (
        f'<a class="text-link" href="{html.escape(safe_url(live_url), quote=True)}" rel="noopener noreferrer">'
        'View live <span aria-hidden="true">↗</span></a>'
    )


def project_source_link(entry: Entry) -> str:
    source = str(entry.metadata.get("source", "")).strip()
    if not source:
        return ""
    return (
        f'<a class="text-link" href="{html.escape(safe_url(source), quote=True)}" rel="noopener noreferrer">'
        'View source <span aria-hidden="true">↗</span></a>'
    )


def render_home_photo(home_data: dict[str, Any]) -> str:
    image = str(home_data.get("image", "")).strip()
    if not image:
        return ""
    image_alt = str(home_data.get("image_alt", "")).strip()
    if not image_alt:
        raise ContentError("content/home.json requires image_alt when image is set")
    caption = str(home_data.get("caption", "")).strip()
    caption_markup = f"<figcaption>{html.escape(caption)}</figcaption>" if caption else ""
    picture = render_image(image, image_alt, eager=True, sizes="(max-width: 44rem) 100vw, 90vw")
    return f'<figure class="home-photo media-shell">{picture}{caption_markup}</figure>'


def render_explore_photos(photos: list[dict[str, Any]]) -> str:
    figures: list[str] = []
    for photo in photos[:3]:
        if not isinstance(photo, dict):
            raise ContentError("Every entry in content/explore-photos.json must be an object")
        image = str(photo.get("image", "")).strip()
        if not image:
            continue
        image_alt = str(photo.get("image_alt", "")).strip()
        if not image_alt:
            raise ContentError("Every configured Explore photo requires image_alt")
        caption = str(photo.get("caption", "")).strip()
        caption_markup = f"<figcaption>{html.escape(caption)}</figcaption>" if caption else ""
        picture = render_image(image, image_alt, sizes="(max-width: 44rem) 100vw, 33vw")
        figures.append(f"<figure>{picture}{caption_markup}</figure>")
    if not figures:
        return ""
    return '<div class="explore-photos" aria-label="A few photographs">' + "".join(figures) + "</div>"


def render_work_intro(site: dict[str, Any], has_projects: bool) -> str:
    tagline = str(site.get("tagline", "")).strip()
    tagline_markup = f'<p class="work-role">{html.escape(tagline)}</p>' if tagline else ""

    cv_path = str(site.get("cv", "")).strip()
    cv_available = bool(cv_path) and (ROOT / cv_path).is_file()

    actions: list[str] = []
    if has_projects:
        actions.append('<a class="work-cta work-cta-primary" href="#projects">View projects</a>')
    if cv_available:
        actions.append(
            f'<a class="work-cta work-cta-secondary" href="{asset_url(cv_path)}" download>Download CV</a>'
        )
    actions_markup = f'<div class="work-actions">{"".join(actions)}</div>' if actions else ""

    links: list[str] = []
    github = str(site.get("github", "")).strip()
    if github:
        links.append(
            f'<a class="external-link" href="{html.escape(safe_url(github), quote=True)}" '
            'target="_blank" rel="noopener noreferrer">GitHub</a>'
        )
    linkedin = str(site.get("linkedin", "")).strip()
    if linkedin:
        links.append(
            f'<a class="external-link" href="{html.escape(safe_url(linkedin), quote=True)}" '
            'target="_blank" rel="noopener noreferrer">LinkedIn</a>'
        )
    email = str(site.get("email", "")).strip()
    if email:
        links.append(f'<a class="text-link" href="mailto:{html.escape(email, quote=True)}">Email</a>')
    links_markup = f'<nav class="work-links" aria-label="Professional links">{"".join(links)}</nav>' if links else ""

    return tagline_markup + actions_markup + links_markup


def load_page(path: Path) -> tuple[dict[str, Any], str]:
    metadata, body = parse_front_matter(path.read_text(encoding=TEXT_ENCODING), path)
    title = str(metadata.get("title", "")).strip()
    description = str(metadata.get("description", "")).strip()
    if not title or not description:
        raise ContentError(f"{path.relative_to(ROOT)} requires title and description")
    if "TODO(RESON)" in body:
        raise ContentError(f"Page content contains a TODO in {path.relative_to(ROOT)}")
    return metadata, markdown_to_html(body)


def render_home_writing(entries: list[Entry], topic_titles: dict[str, str]) -> str:
    if not entries:
        return (
            '<div class="journal-empty home-writing-empty">'
            '<p class="eyebrow">Nothing published yet</p>'
            '<h3>Writing starts when there is something worth saying.</h3>'
            '<p>The structure is ready. The opinions and stories will be Rijan\'s.</p>'
            '</div>'
        )
    featured = next((entry for entry in entries if entry.featured), entries[0])
    latest = [entry for entry in entries if entry.slug != featured.slug][:3]
    selected = latest or entries[:1]
    return f'<div class="home-writing-list">{writing_rows(selected, topic_titles)}</div>'


def render_home_feature(entries: list[Entry], topic_titles: dict[str, str]) -> str:
    if not entries:
        return (
            '<div class="feature-empty"><p class="eyebrow">Writing</p>'
            '<h2>The first story will appear when it is ready.</h2></div>'
        )
    featured = next((entry for entry in entries if entry.featured), entries[0])
    labels = " · ".join(topic_titles.get(topic, topic.replace("-", " ").title()) for topic in featured.topics)
    date_markup = (
        f'<time datetime="{featured.published.isoformat()}">{human_date(featured.published)}</time>'
        if featured.published
        else ""
    )
    image_markup = ""
    if featured.image:
        picture = render_image(featured.image, featured.image_alt, sizes="(max-width: 44rem) 100vw, 80vw")
        image_markup = f'<figure class="lead-story-image">{picture}</figure>'
    return (
        '<article class="lead-story">'
        f'{image_markup}<div class="lead-story-meta"><span>{html.escape(labels)}</span>{date_markup}</div>'
        f'<h2><a href="{featured.url}">{html.escape(featured.title)}</a></h2>'
        f'<p class="lead-story-dek">{html.escape(featured.description)}</p>'
        f'<a class="text-link" href="{featured.url}">Read story <span aria-hidden="true">→</span></a>'
        '</article>'
    )


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding=TEXT_ENCODING, newline="\n")


def render_writing_index(template: Template, entries: list[Entry], topic_titles: dict[str, str]) -> str:
    if entries:
        featured = next((entry for entry in entries if entry.featured), None)
        featured_markup = ""
        if featured:
            labels = " · ".join(topic_titles.get(topic, topic.title()) for topic in featured.topics)
            featured_markup = (
                '<section class="featured-writing" aria-labelledby="featured-writing-title">'
                '<p class="eyebrow">Featured</p><div class="featured-writing-inner">'
                f'<div><p class="record-meta">{html.escape(labels)}</p>'
                f'<h2 id="featured-writing-title"><a href="{featured.url}">{html.escape(featured.title)}</a></h2></div>'
                f'<div><p>{html.escape(featured.description)}</p>'
                f'<a class="text-link" href="{featured.url}">Read the piece</a></div></div></section>'
            )
        groups: list[str] = []
        for year in sorted({entry.published.year for entry in entries}, reverse=True):
            year_entries = [entry for entry in entries if entry.published.year == year]
            groups.append(
                f'<section class="writing-year" aria-labelledby="year-{year}"><h2 id="year-{year}">{year}</h2>'
                f'<div class="writing-list">{writing_rows(year_entries, topic_titles)}</div></section>'
            )
        used_topics = sorted({topic for entry in entries for topic in entry.topics})
        topics_markup = ""
        if used_topics:
            topic_links = "".join(
                f'<a href="/explore/{topic}/">{html.escape(topic_titles.get(topic, topic.title()))}</a>'
                for topic in used_topics
            )
            topics_markup = (
                '<div class="writing-topics-section"><p class="eyebrow">Topics</p>'
                f'<nav class="writing-topics" aria-label="Browse writing by topic">{topic_links}</nav></div>'
            )
        latest_markup = '<div class="latest-writing"><p class="eyebrow">Latest</p>' + "".join(groups) + "</div>"
        content = featured_markup + latest_markup + topics_markup
    else:
        content = (
            '<div class="empty-state"><p class="eyebrow">Nothing here yet</p>'
            '<h2>I’m getting to it.</h2><p>The publishing system is ready. The first piece will appear when it is written.</p></div>'
        )

    main = (
        '<section class="page-hero shell"><p class="page-kicker">Writing</p>'
        '<h1>Thoughts, stories,<br>questions, and notes.</h1>'
        '<div class="page-dek-row"><p class="page-dek">Long or short. Polished or immediate. Connected by curiosity rather than a single category.</p>'
        '<a class="context-link" href="/rss.xml">Follow via RSS <span aria-hidden="true">↗</span></a></div>'
        '</section><section class="page-section shell">'
        f"{content}</section>"
    )
    return render_base(
        template,
        title="Writing",
        description="Writing by Rijan Pradhan: thoughts, stories, questions, and notes across technology, space, cinema, life, and more.",
        canonical_path="/writing/",
        main=main,
        active="writing",
        body_class="writing-page",
        structured_data=page_json_ld("Writing — RESON", "What Reson has been thinking about.", "/writing/", "CollectionPage"),
        social_image="/og.png",
    )


def render_comments(entry: Entry, cusdis_app_id: str) -> str:
    if not cusdis_app_id:
        return ""
    page_url = html.escape(absolute_url(entry.url), quote=True)
    return (
        '<section class="comments-section shell" aria-labelledby="comments-title">'
        '<h2 id="comments-title">Comments</h2>'
        f'<div id="cusdis_thread" data-host="https://cusdis.com" '
        f'data-app-id="{html.escape(cusdis_app_id, quote=True)}" '
        f'data-page-id="{html.escape(entry.slug, quote=True)}" data-page-url="{page_url}" '
        f'data-page-title="{html.escape(entry.title, quote=True)}"></div>'
        '<script async defer src="https://cusdis.com/js/cusdis.es.js"></script>'
        '</section>'
    )


def render_article(
    template: Template,
    entry: Entry,
    all_entries: list[Entry],
    topic_titles: dict[str, str],
    available_topics: set[str],
    cusdis_app_id: str = "",
) -> str:
    updated = (
        f'<span>Updated <time datetime="{entry.updated.isoformat()}">{human_date(entry.updated)}</time></span>'
        if entry.updated and entry.updated != entry.published
        else ""
    )
    figure = ""
    if entry.image:
        picture = render_image(entry.image, entry.image_alt, eager=True, sizes="(max-width: 44rem) 100vw, 90vw")
        figure = f'<figure class="article-lead-image media-shell">{picture}</figure>'
    related = rank_related(entry, all_entries)
    related_markup = ""
    if related:
        related_markup = (
            '<aside class="related-writing" aria-labelledby="related-title"><p class="eyebrow">Keep exploring</p>'
            '<h2 id="related-title">A few connected pieces.</h2>'
            f'<div class="related-list">{writing_rows(related, topic_titles)}</div></aside>'
        )

    main = (
        '<article class="article-page">'
        '<header class="article-header shell">'
        f'{topic_chips(entry.topics, topic_titles, available_topics)}'
        f'<h1>{html.escape(entry.title)}</h1><p class="article-dek">{html.escape(entry.description)}</p>'
        '<div class="article-dates">'
        f'<span>Published <time datetime="{entry.published.isoformat()}">{human_date(entry.published)}</time></span>{updated}'
        '</div></header>'
        f'{figure}<div class="article-prose shell">{entry.html_body}</div>'
        f'<div class="article-after shell">{related_markup}<a class="text-link" href="/writing/">All writing</a></div>'
        f'{render_comments(entry, cusdis_app_id)}'
        '</article>'
    )
    return render_base(
        template,
        title=entry.title,
        description=entry.description,
        canonical_path=entry.url,
        main=main,
        active="writing",
        body_class="article-route",
        structured_data=entry_json_ld(entry),
        social_image=entry.image,
        og_type="article",
        preload_newsreader=True,
    )


def render_topic_page(
    template: Template,
    topic: dict[str, Any],
    entries: list[Entry],
    projects: list[Entry],
    records: list[dict[str, Any]],
    topic_titles: dict[str, str],
    published_slugs: set[str],
) -> str:
    topic_id = str(topic["id"])
    sections: list[str] = []
    if records:
        record_rows: list[str] = []
        for record in records:
            title = str(record.get("title", "")).strip()
            if not title:
                raise ContentError(f"A {topic_id} record is missing title")
            metadata_values = [
                str(value)
                for key, value in record.items()
                if key not in {"title", "note", "writing", "demo", "_source_note"}
                and value not in ("", None, [], {})
            ]
            record_meta = " · ".join(metadata_values)
            note = str(record.get("note", "")).strip()
            writing_slug = str(record.get("writing", "")).strip()
            linked = (
                f'<a class="text-link" href="/writing/{html.escape(writing_slug, quote=True)}/">Read the connected writing</a>'
                if writing_slug and writing_slug in published_slugs
                else ""
            )
            record_rows.append(
                '<article class="record-row">'
                f'<div><p class="record-meta">{html.escape(record_meta)}</p><h2>{html.escape(title)}</h2></div>'
                f'<div>{f"<p>{html.escape(note)}</p>" if note else ""}{linked}</div>'
                '</article>'
            )
        sections.append('<section class="module-records">' + "".join(record_rows) + "</section>")
    if entries:
        sections.append(
            '<section class="module-writing" aria-labelledby="module-writing-title">'
            '<p class="eyebrow">Writing</p><h2 id="module-writing-title">Connected thoughts and stories.</h2>'
            f'<div class="writing-list">{writing_rows(entries, topic_titles)}</div></section>'
        )
    if projects:
        project_rows = "".join(
            '<article class="writing-row">'
            f'<div class="writing-row-meta"><span>{html.escape(project_meta(project))}</span></div>'
            f'<h2><a href="{project.url}">{html.escape(project.title)}</a></h2>'
            f'<p>{html.escape(project.description)}</p></article>'
            for project in projects
        )
        sections.append(
            '<section class="module-writing" aria-labelledby="module-work-title">'
            '<p class="eyebrow">Work</p><h2 id="module-work-title">Connected projects.</h2>'
            f'<div class="writing-list">{project_rows}</div></section>'
        )

    title = str(topic["title"])
    description = topic_description(topic)
    dek = f'<p class="page-dek">{html.escape(description)}</p>' if description else ""
    meta_description = description or f"{title} on RESON."
    main = (
        '<section class="page-hero shell"><p class="page-kicker">Explore / '
        f'{html.escape(title)}</p><h1>{html.escape(title)}</h1>{dek}</section>'
        f'<section class="page-section shell">{"".join(sections)}</section>'
    )
    return render_base(
        template,
        title=title,
        description=meta_description,
        canonical_path=f"/explore/{topic_id}/",
        main=main,
        active="explore",
        body_class="module-page",
        structured_data=page_json_ld(f"{title} — RESON", meta_description, f"/explore/{topic_id}/", "CollectionPage"),
        social_image="/og.png",
    )


def render_explore_index(
    template: Template,
    topics: list[dict[str, Any]],
    available: set[str],
    counts: dict[str, int],
    photos: list[dict[str, Any]],
) -> str:
    rows: list[str] = []
    for index, topic in enumerate(topics, start=1):
        topic_id = str(topic["id"])
        title = str(topic["title"])
        description = topic_description(topic)
        if topic_id in available:
            count = counts.get(topic_id, 0)
            noun = "entry" if count == 1 else "entries"
            action = f'<a href="/explore/{topic_id}/" aria-label="Explore {html.escape(title)}">{count} {noun} <span aria-hidden="true">↗</span></a>'
        else:
            action = '<span class="module-empty">Waiting for a story.</span>'
        description_markup = f"<p>{html.escape(description)}</p>" if description else ""
        rows.append(
            f'<article class="explore-row{"" if description else " no-description"}" '
            f'id="{html.escape(topic_id, quote=True)}">'
            f'<div class="explore-name"><span>{index:02d}</span><h2>{html.escape(title)}</h2></div>'
            f'{description_markup}<div class="explore-action">{action}</div>'
            '</article>'
        )
    photos_markup = render_explore_photos(photos)
    main = (
        '<section class="page-hero shell"><p class="page-kicker">Explore</p>'
        '<h1>A few doors.<br>A lot behind them.</h1>'
        '<p class="page-dek">Interests connect through writing, records, projects, and time. Empty rooms stay quiet until something real belongs there.</p>'
        f'</section><section class="page-section shell">{photos_markup}<div class="explore-list">{"".join(rows)}</div></section>'
    )
    return render_base(
        template,
        title="Explore",
        description="Explore the interests that connect Reson: space, cinema, books, technology, running, chess, travel, music, food, and life.",
        canonical_path="/explore/",
        main=main,
        active="explore",
        body_class="explore-page",
        structured_data=page_json_ld("Explore — RESON", "A doorway into Reson's interests.", "/explore/", "CollectionPage"),
        social_image="/og.png",
    )


def render_now_page(template: Template, now_data: dict[str, Any]) -> str:
    updated = parse_date(now_data.get("updated"), "updated", CONTENT_DIR / "now.json")
    dek = (
        'A few things that have my attention lately.'
        if published_now_items(now_data)
        else 'This snapshot fills in as real updates arrive.'
    )
    main = (
        '<section class="page-hero shell"><p class="page-kicker">Now</p>'
        '<h1>A snapshot,<br>not a status report.</h1>'
        f'<p class="page-dek">Updated <time datetime="{updated.isoformat()}">{human_date(updated)}</time>. '
        f'{dek}</p></section>'
        f'<section class="page-section shell">{render_now_items(now_data)}</section>'
    )
    return render_base(
        template,
        title="Now",
        description="What Rijan Pradhan is building, learning, watching, and doing now.",
        canonical_path="/now/",
        main=main,
        body_class="now-page",
        structured_data=page_json_ld("Now — RESON", "What has Rijan's attention lately.", "/now/"),
        social_image="/og.png",
    )


def render_experience(experience: dict[str, Any], project_slugs: set[str]) -> str:
    """Selected experience and education, subordinate to the projects above it.

    Non-technology roles are shown honestly as what they are; the markup never
    implies an operations job was a software job.
    """
    sections: list[str] = []

    roles = experience.get("roles", [])
    if not isinstance(roles, list):
        raise ContentError("content/experience.json roles must be a list")
    role_rows: list[str] = []
    for role in roles:
        if not isinstance(role, dict):
            raise ContentError("Every experience role must be an object")
        organisation = str(role.get("organisation", "")).strip()
        if not organisation:
            raise ContentError("Every experience role requires an organisation")
        title = str(role.get("title", "")).strip()
        location = str(role.get("location", "")).strip()
        note = str(role.get("note", "")).strip()
        slug = str(role.get("project", "")).strip()
        link = (
            f'<a class="text-link" href="/work/{html.escape(slug, quote=True)}/">See the project</a>'
            if slug and slug in project_slugs
            else ""
        )
        label = " · ".join(value for value in (organisation, location) if value)
        role_rows.append(
            '<article class="experience-row">'
            f'<div><p class="record-meta">{html.escape(label)}</p>'
            f'{f"<h3>{html.escape(title)}</h3>" if title else ""}</div>'
            f'<div>{f"<p>{html.escape(note)}</p>" if note else ""}{link}</div>'
            '</article>'
        )
    if role_rows:
        sections.append(
            '<section class="experience-block" aria-labelledby="experience-title">'
            '<p class="eyebrow">Experience</p>'
            '<h2 id="experience-title">Where the work has happened.</h2>'
            f'<div class="experience-list">{"".join(role_rows)}</div></section>'
        )

    education = experience.get("education", [])
    if not isinstance(education, list):
        raise ContentError("content/experience.json education must be a list")
    education_rows: list[str] = []
    for item in education:
        if not isinstance(item, dict):
            raise ContentError("Every education entry must be an object")
        qualification = str(item.get("qualification", "")).strip()
        if not qualification:
            continue
        institution = str(item.get("institution", "")).strip()
        note = str(item.get("note", "")).strip()
        detail = " · ".join(value for value in (institution, note) if value)
        education_rows.append(
            '<article class="experience-row">'
            f'<div><h3>{html.escape(qualification)}</h3></div>'
            f'<div>{f"<p>{html.escape(detail)}</p>" if detail else ""}</div>'
            '</article>'
        )
    if education_rows:
        sections.append(
            '<section class="experience-block" aria-labelledby="education-title">'
            '<p class="eyebrow">Education</p>'
            '<h2 id="education-title">Qualifications.</h2>'
            f'<div class="experience-list">{"".join(education_rows)}</div></section>'
        )

    return "".join(sections)


def project_technologies(entry: Entry) -> list[str]:
    technologies = entry.metadata.get("technologies", [])
    if not isinstance(technologies, list):
        return []
    return [str(item).strip() for item in technologies if str(item).strip()]


def render_work_index(
    template: Template,
    entries: list[Entry],
    site: dict[str, Any],
    experience: dict[str, Any] | None = None,
) -> str:
    if entries:
        rows: list[str] = []
        for index, entry in enumerate(entries, start=1):
            technologies = project_technologies(entry)
            tech_markup = ""
            if technologies:
                tech_markup = '<ul class="work-index-tech">' + "".join(
                    f"<li>{html.escape(item)}</li>" for item in technologies
                ) + "</ul>"
            screenshot = project_screenshot(
                entry, lazy=index > 1, sizes="(max-width: 58rem) 100vw, 45vw"
            )
            meta = project_meta(entry)
            actions = f'<a class="text-link" href="{entry.url}">View project</a>{project_live_link(entry)}{project_source_link(entry)}'
            rows.append(
                f'<article class="work-index-row{" has-screenshot" if screenshot else ""}">'
                f'<div class="work-index-visual">{screenshot}</div>'
                '<div class="work-index-body">'
                f'<p class="work-index-number" aria-hidden="true">{index:02d}</p>'
                f'{f"<p class=\"record-meta\">{html.escape(meta)}</p>" if meta else ""}'
                f'<h2><a href="{entry.url}">{html.escape(entry.title)}</a></h2>'
                f'<p class="work-index-summary">{html.escape(entry.description)}</p>'
                f'{tech_markup}'
                f'<div class="work-index-actions">{actions}</div>'
                '</div></article>'
            )
        content = '<div class="work-index-list">' + "".join(rows) + "</div>"
    else:
        content = '<div class="empty-state"><p class="eyebrow">Nothing published yet</p><h2>The work room is taking shape.</h2></div>'

    # Aggregated from published projects only. Never a hand-written skills list.
    used_technologies = sorted({item for entry in entries for item in project_technologies(entry)}, key=str.lower)
    technology_section = ""
    if used_technologies:
        chips = "".join(f"<li>{html.escape(item)}</li>" for item in used_technologies)
        technology_section = (
            '<section class="work-technologies" aria-labelledby="work-technologies-title">'
            '<p class="eyebrow">Technologies</p>'
            '<h2 id="work-technologies-title">Demonstrated by the work above.</h2>'
            f'<ul class="technology-cloud">{chips}</ul></section>'
        )

    experience_section = ""
    if experience:
        experience_section = render_experience(experience, {entry.slug for entry in entries})

    intro = render_work_intro(site, bool(entries))
    main = (
        '<section class="page-hero work-hero shell"><p class="page-kicker">Work</p>'
        '<h1>Selected work,<br>documented honestly.</h1>'
        '<p class="page-dek">Projects, systems, and experiments — with the details that can be shared accurately.</p>'
        f'{intro}'
        f'</section><section class="page-section shell" id="projects">'
        f'{content}{technology_section}{experience_section}</section>'
    )
    return render_base(
        template, title="Work", description="Selected work and projects by Rijan Pradhan.",
        canonical_path="/work/", main=main, active="work", body_class="work-page",
        structured_data=page_json_ld("Work — RESON", "Selected work and projects by Rijan Pradhan.", "/work/", "CollectionPage"),
        social_image="/og.png",
    )


def render_content_page(
    template: Template,
    *,
    metadata: dict[str, Any],
    body: str,
    slug: str,
    active: str = "",
) -> str:
    title = str(metadata["title"])
    description = str(metadata["description"])
    statement = str(metadata.get("statement", "")).strip()
    heading = statement or title

    image = str(metadata.get("image", "")).strip()
    image_alt = str(metadata.get("image_alt", "")).strip()
    if image and not image_alt:
        raise ContentError(f"content/pages/{slug}.md requires image_alt when image is set")
    portrait = ""
    body_class_extra = ""
    if image:
        picture = render_image(image, image_alt, sizes="(max-width: 58rem) 100vw, 38vw")
        caption = str(metadata.get("image_caption", "")).strip()
        caption_markup = f"<figcaption>{html.escape(caption)}</figcaption>" if caption else ""
        portrait = f'<figure class="page-portrait">{picture}{caption_markup}</figure>'
        body_class_extra = " has-portrait"

    main = (
        f'<section class="page-hero shell"><p class="page-kicker">{html.escape(title)}</p>'
        f'<h1>{html.escape(heading)}</h1><p class="page-dek">{html.escape(description)}</p></section>'
        f'<section class="page-section shell"><div class="page-with-portrait{body_class_extra}">'
        f'{portrait}<div class="editorial-page-copy">{body}</div></div></section>'
    )
    return render_base(
        template, title=title, description=description, canonical_path=f"/{slug}/", main=main,
        active=active, body_class=f"{slug}-page", structured_data=page_json_ld(f"{title} — RESON", description, f"/{slug}/"),
        social_image=image or "/og.png",
    )


def render_project(template: Template, entry: Entry) -> str:
    technologies = entry.metadata.get("technologies", [])
    tech_markup = ""
    if isinstance(technologies, list) and technologies:
        tech_markup = '<ul class="technology-list" aria-label="Technologies">' + "".join(
            f"<li>{html.escape(str(item))}</li>" for item in technologies
        ) + "</ul>"
    details = project_meta(entry)
    date_markup = (
        f'<time datetime="{entry.published.isoformat()}">{human_date(entry.published)}</time>'
        if entry.published
        else ""
    )
    source_markup = project_source_link(entry)
    live_markup = project_live_link(entry)
    screenshot = project_screenshot(entry, lazy=False, sizes="(max-width: 44rem) 100vw, 90vw")
    screenshot_markup = f'<div class="project-screenshot-frame media-shell">{screenshot}</div>' if screenshot else ""
    main = (
        '<article class="project-page"><header class="article-header shell"><p class="page-kicker">Work</p>'
        f'<h1>{html.escape(entry.title)}</h1><p class="article-dek">{html.escape(entry.description)}</p>'
        f'{f"<p class=\"project-context\">{html.escape(details)}</p>" if details else ""}{tech_markup}'
        f'<div class="article-dates">{date_markup}{live_markup}{source_markup}</div>'
        f'</header>{screenshot_markup}<div class="project-prose shell">{entry.html_body}</div></article>'
    )
    return render_base(
        template,
        title=entry.title,
        description=entry.description,
        canonical_path=entry.url,
        main=main,
        active="work",
        body_class="project-route",
        structured_data=entry_json_ld(entry),
        social_image=entry.image,
        og_type="article",
    )


def make_feed(entries: list[Entry]) -> str:
    items: list[str] = []
    for entry in entries:
        published_dt = datetime.combine(entry.published, time.min, tzinfo=timezone.utc)
        items.append(
            "    <item>\n"
            f"      <title>{html.escape(entry.title)}</title>\n"
            f"      <link>{html.escape(absolute_url(entry.url))}</link>\n"
            f"      <guid isPermaLink=\"true\">{html.escape(absolute_url(entry.url))}</guid>\n"
            f"      <pubDate>{format_datetime(published_dt)}</pubDate>\n"
            f"      <description>{html.escape(entry.description)}</description>\n"
            "    </item>"
        )
    joined = "\n".join(items)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        "    <title>RESON Writing</title>\n"
        f"    <link>{BASE_URL}/writing/</link>\n"
        "    <description>What Reson has been thinking about.</description>\n"
        "    <language>en-au</language>\n"
        f'    <atom:link href="{BASE_URL}/rss.xml" rel="self" type="application/rss+xml" />\n'
        f"{joined}\n"
        "  </channel>\n"
        "</rss>"
    )


def make_sitemap(urls: list[tuple[str, date | None]]) -> str:
    rows: list[str] = []
    for path, modified in urls:
        lastmod = f"\n    <lastmod>{modified.isoformat()}</lastmod>" if modified else ""
        rows.append(f"  <url>\n    <loc>{html.escape(absolute_url(path))}</loc>{lastmod}\n  </url>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(rows)
        + "\n</urlset>"
    )


def prepare_output(output: Path) -> None:
    output = output.resolve()
    if output == ROOT or output.parent != ROOT or output.name != "dist":
        raise ContentError("The build output must be the repository's dist directory")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)


def copy_public_assets(output: Path) -> None:
    files = [
        "style.css",
        "content.css",
        "script.js",
        "og.png",
        "404.html",
        "robots.txt",
        "_headers",
        "_redirects",
    ]
    for name in files:
        source = ROOT / name
        if not source.exists():
            raise ContentError(f"Missing public asset: {name}")
        shutil.copy2(source, output / name)
    shutil.copytree(ROOT / "assets", output / "assets")


def validate_records(topics: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    records: dict[str, list[dict[str, Any]]] = {}
    for topic in topics:
        filename = topic.get("records")
        if not filename:
            records[str(topic["id"])] = []
            continue
        path = CONTENT_DIR / "records" / str(filename)
        payload = read_json(path)
        if not isinstance(payload, list):
            raise ContentError(f"{path.relative_to(ROOT)} must contain a JSON array")
        for record in payload:
            if not isinstance(record, dict) or not str(record.get("title", "")).strip():
                raise ContentError(f"Every record in {path.relative_to(ROOT)} requires a title")
        records[str(topic["id"])] = [record for record in payload if not bool(record.get("demo", False))]
    return records


IMAGE_BUDGET_BYTES = 512_000


def audit_image_weight(output: Path) -> list[str]:
    """Warn about oversized images.

    There is no build-time image pipeline by design, so this keeps the manual
    preparation workflow honest instead of letting a 2 MB photograph ship quietly.
    """
    oversized: list[str] = []
    assets = output / "assets"
    if not assets.is_dir():
        return oversized
    for path in sorted(assets.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".avif"}:
            continue
        size = path.stat().st_size
        if size > IMAGE_BUDGET_BYTES:
            oversized.append(f"{path.relative_to(output).as_posix()} is {size / 1024:.0f} KB")
    return oversized


def validate_dist(output: Path) -> None:
    for path in output.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".html", ".xml", ".json", ".css", ".js", ".txt"}:
            text = path.read_text(encoding=TEXT_ENCODING)
            if "TODO(RESON)" in text or "draft: true" in text:
                raise ContentError(f"Draft marker leaked into {path.relative_to(output)}")


def build(output: Path = DEFAULT_OUTPUT) -> dict[str, int]:
    output = output.resolve()
    prepare_output(output)

    base_template = Template((TEMPLATE_DIR / "base.html").read_text(encoding=TEXT_ENCODING))
    topics = read_json(CONTENT_DIR / "topics.json")
    if not isinstance(topics, list):
        raise ContentError("content/topics.json must contain a JSON array")
    topic_titles = {str(topic["id"]): str(topic["title"]) for topic in topics}
    topic_records = validate_records(topics)
    now_data = read_json(CONTENT_DIR / "now.json")
    if not isinstance(now_data, dict):
        raise ContentError("content/now.json must contain a JSON object")
    home_data = read_json(CONTENT_DIR / "home.json")
    if not isinstance(home_data, dict):
        raise ContentError("content/home.json must contain a JSON object")
    explore_photos = read_json(CONTENT_DIR / "explore-photos.json")
    if not isinstance(explore_photos, list):
        raise ContentError("content/explore-photos.json must contain a JSON array")
    site = read_json(CONTENT_DIR / "site.json")
    if not isinstance(site, dict):
        raise ContentError("content/site.json must contain a JSON object")
    cusdis_app_id = str(site.get("cusdis_app_id", "")).strip()
    experience = read_json(CONTENT_DIR / "experience.json")
    if not isinstance(experience, dict):
        raise ContentError("content/experience.json must contain a JSON object")

    writing = load_entries(CONTENT_DIR / "writing", "writing")
    projects = load_entries(CONTENT_DIR / "projects", "project")
    pages = {
        slug: load_page(CONTENT_DIR / "pages" / f"{slug}.md")
        for slug in ("about", "colophon", "lab")
    }
    writing_by_topic: dict[str, list[Entry]] = {}
    for entry in writing:
        for topic in entry.topics:
            writing_by_topic.setdefault(topic, []).append(entry)

    projects_by_topic: dict[str, list[Entry]] = {}
    for entry in projects:
        for topic in entry.topics:
            projects_by_topic.setdefault(topic, []).append(entry)

    all_topic_ids = set(writing_by_topic) | set(projects_by_topic) | {topic_id for topic_id, values in topic_records.items() if values}
    topic_lookup = {str(topic["id"]): topic for topic in topics}
    for topic_id in sorted(all_topic_ids - set(topic_lookup)):
        topic_lookup[topic_id] = {
            "id": topic_id,
            "title": topic_id.replace("-", " ").title(),
            "description": f"Writing connected with {topic_id.replace('-', ' ')}.",
        }

    copy_public_assets(output)

    homepage = (ROOT / "index.html").read_text(encoding=TEXT_ENCODING)
    homepage = replace_region(homepage, "PHOTO", render_home_photo(home_data))
    homepage = replace_region(homepage, "FEATURE", render_home_feature(writing, topic_titles))
    homepage = replace_region(homepage, "WORK", render_home_work(projects))
    homepage = replace_region(homepage, "WRITING", render_home_writing(writing, topic_titles))
    homepage = replace_region(homepage, "EXPLORE", render_home_explore(topics, all_topic_ids))
    if homepage.count("<!-- RESON_FOOTER -->") != 1:
        raise ContentError("index.html must contain one RESON_FOOTER marker")
    homepage = homepage.replace("<!-- RESON_FOOTER -->", FOOTER_HTML)
    write_text(output / "index.html", homepage)

    not_found = (ROOT / "404.html").read_text(encoding=TEXT_ENCODING)
    if not_found.count("<!-- RESON_FOOTER -->") != 1:
        raise ContentError("404.html must contain one RESON_FOOTER marker")
    write_text(output / "404.html", not_found.replace("<!-- RESON_FOOTER -->", FOOTER_HTML))

    write_text(output / "work" / "index.html", render_work_index(base_template, projects, site, experience))
    write_text(output / "writing" / "index.html", render_writing_index(base_template, writing, topic_titles))
    write_text(output / "explore" / "index.html", render_explore_index(
        base_template,
        topics,
        all_topic_ids,
        {
            topic_id: len(writing_by_topic.get(topic_id, []))
            + len(projects_by_topic.get(topic_id, []))
            + len(topic_records.get(topic_id, []))
            for topic_id in topic_lookup
        },
        explore_photos,
    ))
    write_text(output / "now" / "index.html", render_now_page(base_template, now_data))
    for slug, (metadata, body) in pages.items():
        write_text(
            output / slug / "index.html",
            render_content_page(base_template, metadata=metadata, body=body, slug=slug, active="about" if slug == "about" else ""),
        )

    published_slugs = {entry.slug for entry in writing}
    for entry in writing:
        write_text(
            output / "writing" / entry.slug / "index.html",
            render_article(base_template, entry, writing, topic_titles, all_topic_ids, cusdis_app_id),
        )

    for topic_id in sorted(all_topic_ids):
        topic = topic_lookup[topic_id]
        write_text(
            output / "explore" / topic_id / "index.html",
            render_topic_page(
                base_template,
                topic,
                writing_by_topic.get(topic_id, []),
                projects_by_topic.get(topic_id, []),
                topic_records.get(topic_id, []),
                topic_titles,
                published_slugs,
            ),
        )

    for entry in projects:
        write_text(output / "work" / entry.slug / "index.html", render_project(base_template, entry))

    rss = make_feed(writing)
    write_text(output / "rss.xml", rss)
    # Keep the original path available for existing feed readers and bookmarks.
    write_text(output / "feed.xml", rss)
    now_updated = parse_date(now_data.get("updated"), "updated", CONTENT_DIR / "now.json")
    latest_home = max((entry.updated or entry.published for entry in writing), default=now_updated)
    sitemap_urls: list[tuple[str, date | None]] = [
        ("/", latest_home),
        ("/work/", latest_home),
        ("/writing/", latest_home),
        ("/explore/", latest_home),
        ("/now/", now_updated),
        ("/about/", latest_home),
        ("/colophon/", latest_home),
        ("/lab/", latest_home),
    ]
    sitemap_urls.extend((entry.url, entry.updated or entry.published) for entry in writing + projects)
    sitemap_urls.extend((f"/explore/{topic_id}/", latest_home) for topic_id in sorted(all_topic_ids))
    write_text(output / "sitemap.xml", make_sitemap(sitemap_urls))

    search_index = [
        {
            "type": entry.kind,
            "title": entry.title,
            "description": entry.description,
            "url": entry.url,
            "date": entry.published.isoformat() if entry.published else "",
            "topics": list(entry.topics),
            "text": entry.plain_body,
        }
        for entry in writing + projects
    ]
    search_index.extend(
        {
            "type": "topic",
            "title": str(topic["title"]),
            "description": topic_description(topic),
            "url": f'/explore/{topic["id"]}/' if str(topic["id"]) in all_topic_ids else f'/explore/#{topic["id"]}',
            "date": "",
            "topics": [str(topic["id"])],
            "text": topic_description(topic),
        }
        for topic in topics
    )
    write_text(output / "search-index.json", json.dumps(search_index, ensure_ascii=False, indent=2))
    validate_dist(output)
    return {
        "writing": len(writing),
        "projects": len(projects),
        "topic_pages": len(all_topic_ids),
        "files": sum(1 for path in output.rglob("*") if path.is_file()),
        "oversized_images": audit_image_weight(output),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the static RESON site")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Build output (must be ./dist)")
    args = parser.parse_args()
    try:
        summary = build(args.output)
    except ContentError as exc:
        parser.exit(1, f"Build failed: {exc}\n")
    print(
        "Built RESON: "
        f"{summary['files']} files, {summary['writing']} published writing entries, "
        f"{summary['projects']} published projects, {summary['topic_pages']} active topic pages."
    )
    oversized = summary.get("oversized_images") or []
    if oversized:
        print(
            f"\nImages over the {IMAGE_BUDGET_BYTES // 1024} KB budget "
            "(export a compressed JPEG — see content/README.md):",
            file=sys.stderr,
        )
        for line in oversized:
            print(f"  - {line}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
