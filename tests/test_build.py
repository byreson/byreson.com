from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

import build


class ContentParsingTests(unittest.TestCase):
    def test_front_matter_supports_lists_and_scalars(self) -> None:
        metadata, body = build.parse_front_matter(
            """---
title: A real title
topics:
  - technology
  - life
featured: true
draft: false
---

The body.
"""
        )
        self.assertEqual(metadata["topics"], ["technology", "life"])
        self.assertTrue(metadata["featured"])
        self.assertFalse(metadata["draft"])
        self.assertEqual(body, "The body.")

    def test_markdown_escapes_html_and_keeps_safe_links(self) -> None:
        rendered = build.markdown_to_html(
            "A <script>alert('no')</script> with [a link](https://example.com)."
        )
        self.assertIn("&lt;script&gt;", rendered)
        self.assertNotIn("<script>", rendered)
        self.assertIn('rel="noopener noreferrer"', rendered)

    def test_unsafe_url_scheme_is_rejected(self) -> None:
        with self.assertRaises(build.ContentError):
            build.markdown_to_html("[not safe](javascript:alert)")


class ArticleMediaTests(unittest.TestCase):
    """Inline photographs and video placed anywhere inside an article body."""

    def test_markdown_image_renders_a_responsive_figure(self) -> None:
        rendered = build.markdown_to_html("![Rocky coastline](/assets/photos/kiama.jpg)")
        self.assertIn("<figure", rendered)
        self.assertIn('alt="Rocky coastline"', rendered)
        self.assertIn('loading="lazy"', rendered)
        self.assertIn('decoding="async"', rendered)
        self.assertNotIn("<figcaption", rendered)

    def test_markdown_image_path_with_spaces_needs_angle_brackets(self) -> None:
        rendered = build.markdown_to_html("![Coast](</assets/photos/coastal photo.jpg>)")
        self.assertIn('src="/assets/photos/coastal%20photo.jpg"', rendered)
        # A real asset, so intrinsic dimensions are emitted to prevent layout shift.
        self.assertRegex(rendered, r'width="\d+" height="\d+"')

    def test_markdown_image_title_becomes_a_caption(self) -> None:
        rendered = build.markdown_to_html('![Coast](/assets/photos/kiama.jpg "Kiama, NSW.")')
        self.assertIn("<figcaption>Kiama, NSW.</figcaption>", rendered)

    def test_image_directive_supports_caption_and_width(self) -> None:
        normal = build.markdown_to_html(
            '{{ image\nsrc="/assets/photos/kiama.jpg"\nalt="Coast"\ncaption="Kiama, NSW."\n}}'
        )
        self.assertIn('class="article-media"', normal)
        self.assertIn("<figcaption>Kiama, NSW.</figcaption>", normal)
        self.assertNotIn("media-wide", normal)

        wide = build.markdown_to_html(
            '{{ image src="/assets/photos/kiama.jpg" alt="Coast" size="wide" }}'
        )
        self.assertIn("article-media media-wide", wide)

    def test_image_directive_requires_alt_but_allows_decorative_empty(self) -> None:
        with self.assertRaises(build.ContentError):
            build.markdown_to_html('{{ image src="/assets/photos/kiama.jpg" caption="No alt" }}')

        decorative = build.markdown_to_html('{{ image src="/assets/photos/kiama.jpg" alt="" }}')
        self.assertIn('alt=""', decorative)

    def test_directive_rejects_unknown_options_and_sizes(self) -> None:
        for bad in (
            '{{ image src="/a.jpg" alt="a" captoin="typo" }}',
            '{{ image src="/a.jpg" alt="a" size="enormous" }}',
            '{{ image alt="no src" }}',
            '{{ image\nsrc="/a.jpg"\nalt="unclosed"',
        ):
            with self.subTest(directive=bad[:40]):
                with self.assertRaises(build.ContentError):
                    build.markdown_to_html(bad)

    def test_local_video_uses_native_controls_and_never_autoplays(self) -> None:
        rendered = build.markdown_to_html(
            '{{ video\nsrc="/assets/video/clip.mp4"\nposter="/assets/photos/kiama.jpg"\n'
            'caption="A short clip."\n}}'
        )
        self.assertIn("<video controls playsinline preload=\"metadata\"", rendered)
        self.assertIn('poster="/assets/photos/kiama.jpg"', rendered)
        self.assertIn("<figcaption>A short clip.</figcaption>", rendered)
        for forbidden in ("autoplay", "loop", "muted"):
            self.assertNotIn(forbidden, rendered)

    def test_local_video_supports_a_caption_track_when_supplied(self) -> None:
        rendered = build.markdown_to_html(
            '{{ video src="/assets/video/clip.mp4" captions="/assets/video/clip.vtt" title="Clip" }}'
        )
        self.assertIn('<track kind="captions"', rendered)
        self.assertIn('src="/assets/video/clip.vtt"', rendered)

    def test_supported_providers_become_privacy_friendly_lazy_embeds(self) -> None:
        youtube = build.markdown_to_html(
            '{{ video url="https://www.youtube.com/watch?v=dQw4w9WgXcQ" title="A talk" }}'
        )
        self.assertIn("https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ", youtube)
        self.assertIn('title="A talk"', youtube)
        self.assertIn('loading="lazy"', youtube)
        self.assertIn('class="video-embed"', youtube)
        self.assertNotIn("autoplay", youtube)

        short = build.markdown_to_html('{{ video url="https://youtu.be/dQw4w9WgXcQ" caption="Clip" }}')
        self.assertIn("youtube-nocookie.com/embed/dQw4w9WgXcQ", short)

        vimeo = build.markdown_to_html('{{ video url="https://vimeo.com/123456789" title="Clip" }}')
        self.assertIn("https://player.vimeo.com/video/123456789", vimeo)

    def test_unsupported_or_unsafe_embeds_are_refused(self) -> None:
        for bad in (
            '{{ video url="https://evil.example.com/embed/x" title="nope" }}',
            '{{ video url="https://youtu.be/dQw4w9WgXcQ" }}',            # no accessible title
            '{{ video src="/a.mp4" url="https://youtu.be/dQw4w9WgXcQ" title="both" }}',
            '{{ video title="neither src nor url" }}',
            '{{ image src="javascript:alert(1)" alt="x" }}',
        ):
            with self.subTest(directive=bad[:45]):
                with self.assertRaises(build.ContentError):
                    build.markdown_to_html(bad)

    def test_raw_media_html_in_markdown_stays_escaped(self) -> None:
        """Raw markup becomes inert text: no live element, so no handler can fire."""
        for raw in (
            '<iframe src="https://evil.example.com"></iframe>',
            '<video src="x.mp4" onerror="alert(1)"></video>',
            '<img src=x onerror="alert(1)">',
            '<script>alert(1)</script>',
        ):
            with self.subTest(raw=raw[:30]):
                rendered = build.markdown_to_html(raw)
                self.assertIn("&lt;", rendered)
                for tag in ("<iframe", "<video", "<img", "<script", "<object", "<embed"):
                    self.assertNotIn(tag, rendered)
                # Only the builder's own directives may emit real media elements.
                self.assertNotIn("<figure", rendered)

    def test_an_article_may_mix_many_photos_and_videos(self) -> None:
        body = "\n\n".join([
            "First paragraph.",
            '{{ image src="/assets/photos/a.jpg" alt="One" }}',
            "Second paragraph.",
            '{{ image src="/assets/photos/b.jpg" alt="Two" size="wide" caption="Wide one." }}',
            "Third paragraph.",
            '{{ video src="/assets/video/clip.mp4" caption="Clip." }}',
            '{{ video url="https://youtu.be/dQw4w9WgXcQ" title="Embed" }}',
            "Closing paragraph.",
        ])
        rendered = build.markdown_to_html(body)
        self.assertEqual(rendered.count("<figure"), 4)
        self.assertEqual(rendered.count("<p>"), 4)
        self.assertEqual(rendered.count("media-wide"), 1)
        self.assertEqual(rendered.count("<video"), 1)
        self.assertEqual(rendered.count("<iframe"), 1)
        # Media must never introduce a comment thread.
        self.assertNotIn("cusdis", rendered)


class PublishingTests(unittest.TestCase):
    def test_drafts_are_excluded_and_published_todos_fail(self) -> None:
        with tempfile.TemporaryDirectory(dir=build.ROOT) as temporary:
            directory = Path(temporary)
            draft = directory / "draft.md"
            draft.write_text(
                """---
title: Draft
description: A private draft.
date: 2026-08-15
topics: [life]
draft: true
---
TODO(RESON): Private notes.
""",
                encoding="utf-8",
            )
            self.assertEqual(build.load_entries(directory, "writing"), [])

            draft.write_text(draft.read_text(encoding="utf-8").replace("draft: true", "draft: false"), encoding="utf-8")
            with self.assertRaises(build.ContentError):
                build.load_entries(directory, "writing")

    def test_demo_fixtures_are_never_published_even_when_not_drafts(self) -> None:
        with tempfile.TemporaryDirectory(dir=build.ROOT) as temporary:
            directory = Path(temporary)
            fixture = directory / "fixture.md"
            fixture.write_text(
                """---
title: Verification fixture
description: A fixture that must never publish.
date: 2026-08-15
topics: [life]
demo: true
draft: false
---
Fixture body.
""",
                encoding="utf-8",
            )
            self.assertEqual(build.load_entries(directory, "writing"), [])

            fixture.write_text(fixture.read_text(encoding="utf-8").replace("demo: true", "demo: false"), encoding="utf-8")
            self.assertEqual(len(build.load_entries(directory, "writing")), 1)

    def test_related_writing_prefers_shared_topics(self) -> None:
        def entry(slug: str, topics: tuple[str, ...], published: date) -> build.Entry:
            return build.Entry(
                kind="writing",
                slug=slug,
                title=slug.title(),
                description="Description",
                published=published,
                updated=None,
                topics=topics,
                featured=False,
                image="",
                image_alt="",
                html_body="<p>Body</p>",
                plain_body="Body",
                metadata={},
                source=Path(f"{slug}.md"),
            )

        source = entry("source", ("technology", "life"), date(2026, 8, 15))
        strongest = entry("strongest", ("technology", "life"), date(2025, 1, 1))
        newer = entry("newer", ("technology",), date(2026, 1, 1))
        unrelated = entry("unrelated", ("cinema",), date(2026, 8, 1))
        related = build.rank_related(source, [source, newer, strongest, unrelated])
        self.assertEqual([item.slug for item in related], ["strongest", "newer"])


if __name__ == "__main__":
    unittest.main()
