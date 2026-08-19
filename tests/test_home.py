from __future__ import annotations

import unittest

import build
from test_rendering import make_entry


class HomepageRenderingTests(unittest.TestCase):
    def test_recent_writing_is_one_grouped_homepage_region(self) -> None:
        entries = [make_entry(f"piece-{index}") for index in range(5)]
        rendered = build.render_home_writing(entries, {"life": "Life"})
        self.assertEqual(rendered.count('class="writing-row"'), 3)
        self.assertEqual(rendered.count('class="home-writing-list"'), 1)

    def test_homepage_feature_uses_one_published_story(self) -> None:
        entries = [make_entry(f"piece-{index}") for index in range(3)]
        rendered = build.render_home_feature(entries, {"life": "Life"})
        self.assertEqual(rendered.count('class="lead-story"'), 1)
        self.assertEqual(rendered.count("Read story"), 1)

    def test_selected_work_is_limited_to_two_projects(self) -> None:
        entries = [make_entry(f"project-{index}") for index in range(4)]
        rendered = build.render_home_work(entries)
        self.assertEqual(rendered.count('class="project"'), 2)
        self.assertEqual(rendered.count("View project"), 2)


if __name__ == "__main__":
    unittest.main()
