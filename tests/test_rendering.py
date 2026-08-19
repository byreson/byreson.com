from __future__ import annotations

import unittest
from datetime import date, timedelta
from pathlib import Path
from string import Template

import build


def make_entry(
    slug: str,
    *,
    title: str | None = None,
    topics: tuple[str, ...] = ("life",),
    published: date = date(2026, 8, 15),
    body: str = "<p>A short piece.</p>",
) -> build.Entry:
    return build.Entry(
        kind="writing",
        slug=slug,
        title=title or slug.replace("-", " ").title(),
        description="A precise description of the piece without inventing an opinion.",
        published=published,
        updated=None,
        topics=topics,
        featured=False,
        image="",
        image_alt="",
        html_body=body,
        plain_body="A short piece.",
        metadata={},
        source=Path(f"{slug}.md"),
    )


class RouteRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template = Template((build.TEMPLATE_DIR / "base.html").read_text(encoding="utf-8"))

    def test_article_handles_long_title_many_topics_and_missing_image(self) -> None:
        topics = ("space", "cinema", "philosophy", "life", "technology", "science")
        entry = make_entry(
            "long-title",
            title="A deliberately long article title that must remain readable across narrow and wide screens",
            topics=topics,
            body="<p>Paragraph one.</p>" * 40,
        )
        rendered = build.render_article(
            self.template,
            entry,
            [entry],
            {topic: topic.title() for topic in topics},
            set(topics),
        )
        self.assertIn("newsreader-latin-variable.woff2", rendered)
        self.assertNotIn('property="og:image"', rendered)
        self.assertEqual(rendered.count('class="topic-chips"'), 1)
        self.assertEqual(rendered.count("/explore/"), len(topics) + 1)  # Topic links plus primary navigation.
        self.assertIn("<article", rendered)

    def test_writing_index_keeps_large_archive_off_the_homepage_model(self) -> None:
        entries = [
            make_entry(
                f"piece-{index}",
                published=date(2026, 12, 31) - timedelta(days=index),
            )
            for index in range(500)
        ]
        rendered = build.render_writing_index(self.template, entries, {"life": "Life"})
        self.assertEqual(rendered.count('class="writing-row"'), 500)
        self.assertIn("2026", rendered)
        self.assertIn("2025", rendered)

    def test_now_hides_empty_fields(self) -> None:
        rendered = build.render_now_items(
            {
                "items": [
                    {"label": "Building", "value": "byreson.com"},
                    {"label": "Reading", "value": ""},
                    {"label": "", "value": "Hidden"},
                ]
            }
        )
        self.assertIn("Building", rendered)
        self.assertNotIn("Reading", rendered)
        self.assertNotIn("Hidden", rendered)

    def test_undated_project_renders_without_inventing_a_date(self) -> None:
        project = make_entry("undated-project")
        project = build.Entry(
            kind="project",
            slug=project.slug,
            title=project.title,
            description=project.description,
            published=None,
            updated=None,
            topics=("technology",),
            featured=True,
            image="",
            image_alt="",
            html_body=project.html_body,
            plain_body=project.plain_body,
            metadata={"context": "Internship", "technologies": ["JavaScript"]},
            source=project.source,
        )
        rendered = build.render_project(self.template, project)
        self.assertIn("Internship", rendered)
        self.assertIn("JavaScript", rendered)
        self.assertNotIn("datePublished", rendered)
        self.assertNotIn("<time", rendered)

    def test_project_screenshot_status_and_live_link_only_render_when_configured(self) -> None:
        bare = make_entry("bare-project")
        bare = build.Entry(
            kind="project", slug=bare.slug, title=bare.title, description=bare.description,
            published=None, updated=None, topics=("technology",), featured=False,
            image="", image_alt="", html_body=bare.html_body, plain_body=bare.plain_body,
            metadata={}, source=bare.source,
        )
        rendered = build.render_project(self.template, bare)
        self.assertNotIn("project-screenshot", rendered)
        self.assertNotIn("View live", rendered)

        rich = build.Entry(
            kind="project", slug="rich-project", title="Rich Project", description=bare.description,
            published=None, updated=None, topics=("technology",), featured=False,
            image="/assets/projects/shot.png", image_alt="A screenshot of the app",
            html_body=bare.html_body, plain_body=bare.plain_body,
            metadata={"status": "In development", "live_url": "https://example.com"},
            source=Path("rich-project.md"),
        )
        rendered = build.render_project(self.template, rich)
        self.assertIn('class="project-screenshot"', rendered)
        self.assertIn("In development", rendered)
        self.assertIn("View live", rendered)

    def test_writing_row_shows_a_thumbnail_only_when_an_image_is_set(self) -> None:
        plain = make_entry("plain-piece")
        with_image = build.Entry(
            kind="writing", slug="photo-piece", title="Photo Piece", description=plain.description,
            published=plain.published, updated=None, topics=("life",), featured=False,
            image="/assets/writing/photo.jpg", image_alt="A documentary photograph",
            html_body=plain.html_body, plain_body=plain.plain_body, metadata={},
            source=Path("photo-piece.md"),
        )
        rendered = build.writing_rows([plain, with_image], {"life": "Life"})
        self.assertEqual(rendered.count('class="writing-row"'), 1)
        self.assertEqual(rendered.count('class="writing-row has-image"'), 1)
        self.assertEqual(rendered.count("writing-row-image"), 1)

    def test_comments_render_only_when_cusdis_is_configured(self) -> None:
        entry = make_entry("commentable")
        without = build.render_article(self.template, entry, [entry], {"life": "Life"}, {"life"})
        self.assertNotIn("comments-section", without)
        self.assertNotIn("cusdis", without)

        with_comments = build.render_article(self.template, entry, [entry], {"life": "Life"}, {"life"}, "real-app-id")
        self.assertIn('data-app-id="real-app-id"', with_comments)
        self.assertIn('data-page-id="commentable"', with_comments)
        self.assertIn("cusdis.com/js/cusdis.es.js", with_comments)

    def test_home_photo_requires_alt_text_and_omits_cleanly_when_unset(self) -> None:
        self.assertEqual(build.render_home_photo({"image": "", "image_alt": "", "caption": ""}), "")
        with self.assertRaises(build.ContentError):
            build.render_home_photo({"image": "/assets/photos/hero.jpg", "image_alt": "", "caption": ""})
        rendered = build.render_home_photo(
            {"image": "/assets/photos/hero.jpg", "image_alt": "A real photograph", "caption": "Kiama, 2026"}
        )
        self.assertIn('class="home-photo media-shell"', rendered)
        self.assertIn("Kiama, 2026", rendered)

    def test_local_images_get_intrinsic_dimensions_and_encoded_paths(self) -> None:
        # A real repository asset: the builder should read its true pixel size.
        rendered = build.render_image("assets/photos/coastal photo.jpg", "A coastal scene")
        self.assertIn('src="/assets/photos/coastal%20photo.jpg"', rendered)
        self.assertRegex(rendered, r'width="\d+" height="\d+"')
        self.assertIn('loading="lazy"', rendered)

        eager = build.render_image("assets/photos/coastal photo.jpg", "A coastal scene", eager=True)
        self.assertIn('fetchpriority="high"', eager)
        self.assertNotIn('loading="lazy"', eager)

        # A path with no file behind it still renders, just without dimensions.
        missing = build.render_image("/assets/photos/not-here.jpg", "Missing")
        self.assertIn('src="/assets/photos/not-here.jpg"', missing)
        self.assertNotIn("width=", missing)

    def test_about_portrait_is_optional_and_requires_alt_text(self) -> None:
        without = build.render_content_page(
            self.template, metadata={"title": "About", "description": "Desc"}, body="<p>Copy</p>", slug="about"
        )
        self.assertNotIn("page-portrait", without)
        self.assertIn("page-with-portrait", without)

        with self.assertRaises(build.ContentError):
            build.render_content_page(
                self.template,
                metadata={"title": "About", "description": "Desc", "image": "/a.jpg", "image_alt": ""},
                body="<p>Copy</p>",
                slug="about",
            )

        with_portrait = build.render_content_page(
            self.template,
            metadata={"title": "About", "description": "Desc", "image": "/a.jpg", "image_alt": "A portrait"},
            body="<p>Copy</p>",
            slug="about",
        )
        self.assertIn('class="page-portrait"', with_portrait)
        self.assertIn("has-portrait", with_portrait)

    def test_explore_photos_cap_at_three_and_omit_when_empty(self) -> None:
        self.assertEqual(build.render_explore_photos([]), "")
        photos = [
            {"image": f"/assets/photos/{index}.jpg", "image_alt": f"Photo {index}"}
            for index in range(5)
        ]
        rendered = build.render_explore_photos(photos)
        self.assertEqual(rendered.count("<figure>"), 3)


if __name__ == "__main__":
    unittest.main()
