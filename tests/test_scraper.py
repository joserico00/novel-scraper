"""Tests for scraper.py. No network: every request goes through a fake session."""

import ast
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scraper

CHAPTER_ONE = """
<html><head><title>Site — Chapter 1</title></head><body>
  <h1>Chapter 1: The Departure</h1>
  <div class="wp-block-post-content entry-content is-layout-constrained">
    <p>The first paragraph ends here.</p>
    <p>The second paragraph starts here.</p>
  </div>
  <a rel="next" href="/chapter-2/">Next chapter</a>
</body></html>
"""

CHAPTER_TWO = """
<html><body>
  <h1>Chapter 2: The Arrival</h1>
  <div class="entry-content"><p>Only one paragraph.</p></div>
</body></html>
"""

ROBOTS_ALLOWING = "User-agent: *\nDisallow: /admin/\n"
ROBOTS_BLOCKING = "User-agent: *\nDisallow: /chapter-1/\n"


class FakeResponse:
    def __init__(self, text="", status_code=200):
        self.text = text
        self.status_code = status_code
        self.encoding = "utf-8"

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} for url")


class FakeSession:
    """Serves canned pages and records what was asked for."""

    def __init__(self, pages, user_agent=scraper.USER_AGENT):
        self.pages = pages
        self.headers = {"User-Agent": user_agent}
        self.requested = []

    def get(self, url, timeout=None):
        self.requested.append(url)
        if url not in self.pages:
            return FakeResponse("not found", status_code=404)
        page = self.pages[url]
        if isinstance(page, Exception):
            raise page
        return FakeResponse(page)


class ExtractTests(unittest.TestCase):
    def test_pulls_body_title_and_next_link(self):
        chapter = scraper.extract_chapter(CHAPTER_ONE, "https://example.com/chapter-1/")

        self.assertEqual(chapter.title, "Chapter 1: The Departure")
        self.assertIn("The first paragraph ends here.", chapter.text)
        self.assertEqual(chapter.next_url, "https://example.com/chapter-2/")

    def test_paragraph_breaks_survive(self):
        chapter = scraper.extract_chapter(CHAPTER_ONE, "https://example.com/chapter-1/")

        # .text would give "...ends here.The second paragraph..." with no break.
        self.assertNotIn("here.The", chapter.text)
        self.assertEqual(len(chapter.text.splitlines()), 2)

    def test_class_order_does_not_matter(self):
        """The old exact-string match needed the classes in one fixed order."""
        shuffled = CHAPTER_ONE.replace(
            'class="wp-block-post-content entry-content is-layout-constrained"',
            'class="is-layout-constrained entry-content wp-block-post-content"',
        )

        self.assertIn("first paragraph", scraper.extract_chapter(shuffled).text)

    def test_missing_selector_says_what_to_do(self):
        with self.assertRaises(scraper.ChapterNotFound) as caught:
            scraper.extract_chapter("<html><body><p>An error page.</p></body></html>",
                                    "https://example.com/gone/")

        message = str(caught.exception)
        self.assertIn("https://example.com/gone/", message)
        self.assertIn("--selector", message)

    def test_missing_next_link_is_not_an_error(self):
        self.assertIsNone(scraper.extract_chapter(CHAPTER_TWO).next_url)


class FetchTests(unittest.TestCase):
    def test_error_pages_raise_instead_of_being_parsed(self):
        session = FakeSession({})

        with self.assertRaises(requests.HTTPError):
            scraper.fetch(session, "https://example.com/missing/")

    def test_session_identifies_itself(self):
        self.assertIn("novel-scraper", scraper.build_session().headers["User-Agent"])


class RobotsTests(unittest.TestCase):
    def test_disallowed_path_is_refused(self):
        session = FakeSession({"https://example.com/robots.txt": ROBOTS_BLOCKING})

        self.assertFalse(scraper.robots_allows(session, "https://example.com/chapter-1/"))
        self.assertTrue(scraper.robots_allows(session, "https://example.com/chapter-2/"))

    def test_allowed_when_robots_permits(self):
        session = FakeSession({"https://example.com/robots.txt": ROBOTS_ALLOWING})

        self.assertTrue(scraper.robots_allows(session, "https://example.com/chapter-1/"))

    def test_missing_or_unreachable_robots_means_no_rules(self):
        self.assertTrue(scraper.robots_allows(FakeSession({}), "https://example.com/c/"))

        offline = FakeSession({"https://example.com/robots.txt": requests.ConnectionError("down")})
        self.assertTrue(scraper.robots_allows(offline, "https://example.com/c/"))


class ScrapeTests(unittest.TestCase):
    def pages(self):
        return {
            "https://example.com/robots.txt": ROBOTS_ALLOWING,
            "https://example.com/chapter-1/": CHAPTER_ONE,
            "https://example.com/chapter-2/": CHAPTER_TWO,
        }

    def test_follows_next_links_and_stops_at_the_end(self):
        session = FakeSession(self.pages())
        slept = []

        chapters = list(scraper.scrape("https://example.com/chapter-1/", chapters=5,
                                       session=session, sleep=slept.append))

        self.assertEqual([c.title for c in chapters],
                         ["Chapter 1: The Departure", "Chapter 2: The Arrival"])
        self.assertEqual(slept, [scraper.DEFAULT_DELAY])   # waited once, between the two

    def test_honours_the_chapter_limit(self):
        session = FakeSession(self.pages())

        chapters = list(scraper.scrape("https://example.com/chapter-1/", chapters=1,
                                       session=session, sleep=lambda _: None))

        self.assertEqual(len(chapters), 1)
        self.assertNotIn("https://example.com/chapter-2/", session.requested)

    def test_a_chapter_linking_to_itself_does_not_loop(self):
        looping = CHAPTER_ONE.replace('href="/chapter-2/"', 'href="/chapter-1/"')
        session = FakeSession({**self.pages(), "https://example.com/chapter-1/": looping})

        chapters = list(scraper.scrape("https://example.com/chapter-1/", chapters=10,
                                       session=session, sleep=lambda _: None))

        self.assertEqual(len(chapters), 1)

    def test_robots_disallow_stops_the_run(self):
        session = FakeSession({**self.pages(),
                               "https://example.com/robots.txt": ROBOTS_BLOCKING})

        with self.assertRaises(scraper.DisallowedByRobots):
            list(scraper.scrape("https://example.com/chapter-1/", session=session))

        self.assertNotIn("https://example.com/chapter-1/", session.requested)

    def test_ignore_robots_skips_the_check(self):
        session = FakeSession({**self.pages(),
                               "https://example.com/robots.txt": ROBOTS_BLOCKING})

        chapters = list(scraper.scrape("https://example.com/chapter-1/", chapters=1,
                                       session=session, check_robots=False,
                                       sleep=lambda _: None))

        self.assertEqual(len(chapters), 1)


class CommandLineTests(unittest.TestCase):
    def run_main(self, argv, session):
        """Run main() with the network replaced, capturing its output."""
        original = scraper.build_session
        scraper.build_session = lambda *args, **kwargs: session
        out, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = scraper.main(argv)
        finally:
            scraper.build_session = original
        return code, out.getvalue(), err.getvalue()

    def test_prints_the_chapter(self):
        session = FakeSession({"https://example.com/robots.txt": ROBOTS_ALLOWING,
                               "https://example.com/chapter-1/": CHAPTER_ONE})

        code, out, _ = self.run_main(["https://example.com/chapter-1/", "-n", "1"], session)

        self.assertEqual(code, 0)
        self.assertIn("The second paragraph starts here.", out)

    def test_writes_a_file(self):
        session = FakeSession({"https://example.com/robots.txt": ROBOTS_ALLOWING,
                               "https://example.com/chapter-1/": CHAPTER_ONE})

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "chapter.txt"
            code, _, _ = self.run_main(
                ["https://example.com/chapter-1/", "-n", "1", "-o", str(target)], session)

            self.assertEqual(code, 0)
            self.assertIn("The Departure", target.read_text(encoding="utf-8"))

    def test_a_missing_selector_is_a_message_not_a_traceback(self):
        session = FakeSession({"https://example.com/robots.txt": ROBOTS_ALLOWING,
                               "https://example.com/chapter-1/": "<html><body>nope</body></html>"})

        code, _, err = self.run_main(["https://example.com/chapter-1/"], session)

        self.assertEqual(code, 1)
        self.assertIn("error:", err)

    def test_a_dead_url_is_a_message_not_a_traceback(self):
        session = FakeSession({"https://example.com/robots.txt": ROBOTS_ALLOWING})

        code, _, err = self.run_main(["https://example.com/gone/"], session)

        self.assertEqual(code, 1)
        self.assertIn("error:", err)


class ImportTests(unittest.TestCase):
    def test_importing_the_module_fetches_nothing(self):
        """The first version fired a request at import time."""
        tree = ast.parse((ROOT / "scraper.py").read_text(encoding="utf-8"))
        calls = [node for node in tree.body
                 if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)]

        self.assertEqual(calls, [], "module-level call would run on import")


if __name__ == "__main__":
    unittest.main(verbosity=2)
