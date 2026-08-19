from __future__ import annotations

import html
import re
import subprocess
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit

import build


class GeneratedRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.summary = build.build()
        cls.dist = build.DEFAULT_OUTPUT

    def read_route(self, route: str) -> str:
        path = self.dist / route.strip("/")
        if not route.strip("/") or route.endswith("/"):
            path /= "index.html"
        self.assertTrue(path.is_file(), f"Missing generated route: {route}")
        rendered = path.read_text(encoding="utf-8")
        self.assertIn("<main", rendered)
        self.assertIn("<h1", rendered)
        return rendered

    def test_primary_routes_render_real_content(self) -> None:
        expected = {
            "/": "Selected work",
            "/work/": "Address Autocomplete",
            "/writing/": "Featured",
            "/explore/": "Space",
            "/about/": "Rijan",
            "/now/": "still being written",
            "/colophon/": "complexity lives underneath",
        }
        for route, text in expected.items():
            with self.subTest(route=route):
                self.assertIn(text, self.read_route(route))

    def test_writing_archive_is_populated_and_ordered(self) -> None:
        self.assertGreaterEqual(self.summary["writing"], 5)

        index = self.read_route("/writing/")
        self.assertNotIn("Nothing here yet", index)
        self.assertLess(index.index(">Featured<"), index.index(">Latest<"))
        self.assertLess(index.index(">Latest<"), index.index(">Topics<"))

        # Exactly one featured piece, and it is a real published article.
        featured = re.findall(r'<section class="featured-writing".*?</section>', index, flags=re.DOTALL)
        self.assertEqual(len(featured), 1)

        for path in sorted((build.CONTENT_DIR / "writing").glob("*.md")):
            if path.name.startswith("_"):
                continue
            metadata, _ = build.parse_front_matter(path.read_text(encoding="utf-8"), path)
            slug = str(metadata.get("slug", path.stem))
            published = not bool(metadata.get("draft", True)) and not bool(metadata.get("demo", False))
            route = self.dist / "writing" / slug / "index.html"
            self.assertEqual(route.is_file(), published, f"{slug} publish state mismatch")

    def test_topic_routes_activate_from_published_content(self) -> None:
        # Every topic carrying published writing or work must have a real route.
        for topic in ("space", "cinema", "running", "chess", "technology", "life"):
            with self.subTest(topic=topic):
                rendered = self.read_route(f"/explore/{topic}/")
                self.assertIn("<h1", rendered)

        # Topics with nothing behind them yet stay quiet rather than generating a route.
        for topic in ("books", "music", "travel", "food"):
            with self.subTest(topic=topic):
                self.assertFalse((self.dist / "explore" / topic).exists())

    def test_multi_topic_articles_are_referenced_not_duplicated(self) -> None:
        interstellar = "Why Interstellar keeps pulling me back"
        for topic in ("cinema", "space"):
            with self.subTest(topic=topic):
                self.assertIn(interstellar, self.read_route(f"/explore/{topic}/"))

        # One canonical source, one canonical route.
        sources = list((build.CONTENT_DIR / "writing").glob("why-interstellar-keeps-pulling-me-back.md"))
        self.assertEqual(len(sources), 1)
        self.assertEqual(len(list((self.dist / "writing").glob("*/index.html"))), self.summary["writing"])

    def test_cusdis_is_configured_per_article_and_nowhere_else(self) -> None:
        app_id = build.read_json(build.CONTENT_DIR / "site.json")["cusdis_app_id"]
        self.assertTrue(app_id, "Expected a configured Cusdis app id")

        article_pages = sorted((self.dist / "writing").glob("*/index.html"))
        self.assertGreaterEqual(len(article_pages), 5)

        for page in article_pages:
            slug = page.parent.name
            source = page.read_text(encoding="utf-8")
            with self.subTest(slug=slug):
                self.assertIn(f'data-app-id="{app_id}"', source)
                self.assertIn('data-host="https://cusdis.com"', source)
                self.assertIn(f'data-page-id="{slug}"', source)
                self.assertIn(f'data-page-url="https://byreson.com/writing/{slug}/"', source)
                self.assertIn("cusdis.com/js/cusdis.es.js", source)
                # The title attribute must carry the real article title.
                title = re.search(r'data-page-title="([^"]+)"', source)
                self.assertIsNotNone(title)
                self.assertIn(html.unescape(title.group(1)), source)
                # No unresolved template placeholders.
                for placeholder in ("{{", "}}", "PAGE_ID", "PAGE_URL", "PAGE_TITLE"):
                    self.assertNotIn(placeholder, source)

        # Comments belong only on individual articles.
        for page in self.dist.rglob("*.html"):
            if page in set(article_pages):
                continue
            self.assertNotIn("cusdis", page.read_text(encoding="utf-8"), page.relative_to(self.dist))

    def test_homepage_explore_lists_every_primary_topic(self) -> None:
        homepage = self.read_route("/")
        field = re.search(r'<nav class="interest-field".*?</nav>', homepage, flags=re.DOTALL)
        self.assertIsNotNone(field)
        markup = field.group(0)

        topics = build.read_json(build.CONTENT_DIR / "topics.json")
        for topic in topics:
            with self.subTest(topic=topic["id"]):
                self.assertIn(f'>{topic["title"]}<', markup)

        # Food and Life were previously truncated by a hard limit.
        self.assertIn(">Food<", markup)
        self.assertIn(">Life<", markup)
        self.assertIn("Explore all", homepage)
        self.assertNotIn("The whole index", homepage)

    def test_rss_is_populated_and_linked_for_humans(self) -> None:
        writing = self.read_route("/writing/")
        self.assertIn('href="/rss.xml"', writing)
        self.assertIn("Follow via RSS", writing)
        self.assertNotIn("XML Feed", writing)

        root = ET.fromstring((self.dist / "rss.xml").read_text(encoding="utf-8"))
        items = root.findall("./channel/item")
        self.assertEqual(len(items), self.summary["writing"])
        for item in items:
            self.assertTrue(item.findtext("title"))
            self.assertTrue(item.findtext("link", "").startswith("https://byreson.com/writing/"))

        # Feed autodiscovery belongs in <head> on every page...
        explore = self.read_route("/explore/")
        self.assertIn('rel="alternate" type="application/rss+xml"', explore)
        # ...but RSS is never presented as an Explore topic in the body.
        explore_list = re.search(r'<div class="explore-list">.*?</section>', explore, flags=re.DOTALL)
        self.assertIsNotNone(explore_list)
        self.assertNotIn("rss", explore_list.group(0).lower())

    def test_private_material_is_never_built_or_tracked(self) -> None:
        """.private/ must stay out of the build output and out of version control."""
        private_dir = build.ROOT / ".private"

        # Nothing named after it may appear in the generated site.
        for path in self.dist.rglob("*"):
            self.assertNotIn(".private", str(path.relative_to(self.dist)))

        # Nothing under it may be tracked, on any machine.
        tracked = subprocess.run(
            ["git", "ls-files", ".private"],
            cwd=build.ROOT, capture_output=True, text=True,
        ).stdout.strip()
        self.assertEqual(tracked, "", "private files are tracked by git")

        # Hosting-level block, in case the repository root is ever served directly.
        self.assertIn("/.private/*", (build.ROOT / "_redirects").read_text(encoding="utf-8"))

        if not private_dir.is_dir():
            # A fresh clone has no .private/ and no local exclude rule for it.
            # The invariants above still hold; the rest only applies where it exists.
            self.skipTest("no .private directory present to leak-test")

        # Where the directory does exist it must be ignored, so `git add -A`
        # cannot stage it. The rule may live in .gitignore or, because it is
        # machine-local, in .git/info/exclude — either satisfies this.
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", ".private/"],
            cwd=build.ROOT, capture_output=True,
        )
        self.assertEqual(ignored.returncode, 0, ".private/ exists but is not ignored by git")

        # No distinctive sentence from private files may appear anywhere in dist.
        for source in private_dir.rglob("*"):
            if not source.is_file() or source.suffix.lower() not in {".md", ".txt", ".json"}:
                continue
            phrases = [
                line.strip()[:60]
                for line in source.read_text(encoding="utf-8", errors="ignore").splitlines()
                if len(line.strip()) > 45 and not line.strip().startswith(("#", "-", "|"))
            ]
            self.assertTrue(phrases, f"expected testable prose in {source.name}")
            for page in self.dist.rglob("*"):
                if not page.is_file() or page.suffix.lower() not in {".html", ".xml", ".json", ".txt"}:
                    continue
                rendered = page.read_text(encoding="utf-8", errors="ignore")
                for phrase in phrases[:8]:
                    self.assertNotIn(phrase, rendered, f"private text leaked into {page.name}")

    def test_no_demo_record_prose_reaches_the_generated_site(self) -> None:
        demo_fragments = (
            "Spider-Man and the people who keep heroes alive",
            "600 Elo",
            "Momo deserves the same global respect",
            "Building byreson.com without turning it into a tech demo",
        )
        for path in self.dist.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".html", ".xml", ".json"}:
                continue
            source = path.read_text(encoding="utf-8")
            for fragment in demo_fragments:
                self.assertNotIn(fragment, source, path.relative_to(self.dist))

    def test_homepage_navigation_is_same_tab_and_has_no_empty_links(self) -> None:
        homepage = self.read_route("/")
        self.assertNotIn('href="#"', homepage)
        for href in ("/", "/work/", "/writing/", "/explore/", "/about/"):
            self.assertRegex(homepage, rf'<a[^>]+href="{re.escape(href)}"(?![^>]+target=)')

    def test_site_has_one_light_identity_and_no_loading_theatre(self) -> None:
        forbidden_markup = (
            'class="theme-toggle"',
            "theme-init.js",
            "scroll-progress",
            "data-theme=",
            "transition-overlay",
            "page-overlay",
        )
        for page in self.dist.rglob("*.html"):
            source = page.read_text(encoding="utf-8")
            self.assertIn('<meta name="theme-color" content="#F8F7F3">', source, page.relative_to(self.dist))
            for fragment in forbidden_markup:
                self.assertNotIn(fragment, source, page.relative_to(self.dist))

        self.assertFalse((self.dist / "theme-init.js").exists())

        stylesheet = (self.dist / "style.css").read_text(encoding="utf-8")
        self.assertIn("color-scheme: only light", stylesheet)
        self.assertNotIn("prefers-color-scheme: dark", stylesheet)
        self.assertNotIn('[data-theme="dark"]', stylesheet)
        self.assertNotIn("is-reveal-ready", stylesheet)
        self.assertNotIn("hero-enter", stylesheet)

        script = (self.dist / "script.js").read_text(encoding="utf-8")
        for fragment in ("localStorage", "prefers-color-scheme", "IntersectionObserver", "requestAnimationFrame"):
            self.assertNotIn(fragment, script)

    def test_global_footer_and_contextual_links_are_deliberately_separated(self) -> None:
        source_url = "https://github.com/byreson/byreson.com"
        for page in self.dist.rglob("*.html"):
            source = page.read_text(encoding="utf-8")
            self.assertEqual(source.count('class="site-footer"'), 1, page.relative_to(self.dist))
            footer = re.search(r'<footer class="site-footer">.*?</footer>', source, flags=re.DOTALL)
            self.assertIsNotNone(footer, page.relative_to(self.dist))
            footer_markup = footer.group(0)
            self.assertIn("https://github.com/byreson", footer_markup)
            self.assertNotIn("/rss.xml", footer_markup)
            self.assertNotIn("/colophon/", footer_markup)
            self.assertNotIn(source_url, footer_markup)

        writing = self.read_route("/writing/")
        self.assertIn('href="/rss.xml"', writing)
        about = self.read_route("/about/")
        self.assertIn('href="/colophon/"', about)
        colophon = self.read_route("/colophon/")
        self.assertIn(f'href="{source_url}"', colophon)

        # The repository URL belongs on the colophon and, as a project source link, on Work.
        # Anywhere else it would be incidental clutter rather than a deliberate link.
        allowed = {
            self.dist / "colophon" / "index.html",
            self.dist / "work" / "index.html",
            self.dist / "work" / "byreson" / "index.html",
        }
        for page in self.dist.rglob("*.html"):
            if page in allowed:
                continue
            self.assertNotIn(source_url, page.read_text(encoding="utf-8"), page.relative_to(self.dist))

    def test_rss_is_static_valid_xml_not_an_html_route(self) -> None:
        feed = self.dist / "rss.xml"
        self.assertTrue(feed.is_file(), "Missing generated RSS feed")
        source = feed.read_text(encoding="utf-8")
        self.assertNotIn("<!doctype html", source.lower())
        root = ET.fromstring(source)
        self.assertEqual(root.tag, "rss")
        self.assertEqual(root.attrib.get("version"), "2.0")
        self.assertEqual(len(root.findall("./channel")), 1)
        self.assertEqual(len(root.findall("./channel/item")), self.summary["writing"])

    def test_all_generated_internal_links_resolve(self) -> None:
        for page in self.dist.rglob("*.html"):
            source = page.read_text(encoding="utf-8")
            self.assertNotIn('href="#"', source, f"Empty link in {page.relative_to(self.dist)}")
            for anchor in re.findall(r"<a\b[^>]*>", source, flags=re.IGNORECASE):
                href_match = re.search(r'href="([^"]+)"', anchor, flags=re.IGNORECASE)
                if not href_match:
                    continue
                href = href_match.group(1)
                parsed = urlsplit(href)
                if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
                    continue
                self.assertNotRegex(anchor, r"\btarget\s*=", f"Internal link opens a new tab: {href}")
                target = self.dist / parsed.path.lstrip("/")
                if not parsed.path.lstrip("/") or parsed.path.endswith("/"):
                    target /= "index.html"
                self.assertTrue(target.exists(), f"{page.relative_to(self.dist)} links to missing {href}")

    def test_unknown_routes_have_a_nonblank_404_document(self) -> None:
        not_found = (self.dist / "404.html").read_text(encoding="utf-8")
        self.assertIn("Page not found", not_found)
        self.assertIn("<h1", not_found)
        self.assertIn("Return to RESON", not_found)

    def test_cloudflare_pages_artifact_is_multi_route_not_spa(self) -> None:
        for name in ("404.html", "_headers", "_redirects"):
            self.assertTrue((self.dist / name).is_file(), f"Missing Pages artifact: {name}")

        for route in ("work", "writing", "explore", "about", "now", "colophon"):
            self.assertTrue((self.dist / route / "index.html").is_file())

        self.assertTrue((self.dist / "rss.xml").is_file())

        redirects = (self.dist / "_redirects").read_text(encoding="utf-8")
        self.assertNotIn("/* /index.html 200", redirects)
        self.assertNotIn("single-page-application", redirects)

        not_found = (self.dist / "404.html").read_text(encoding="utf-8")
        self.assertIn("Page not found", not_found)
        self.assertIn("Return to RESON", not_found)


if __name__ == "__main__":
    unittest.main()
