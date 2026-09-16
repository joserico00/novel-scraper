"""Download a web-novel chapter and print or save it as plain text.

The script takes the chapter URL on the command line, so nothing about a
particular site is baked into the code:

    python scraper.py https://example.com/chapter-1/
    python scraper.py https://example.com/chapter-1/ --chapters 5 -o book.txt

It checks robots.txt before fetching, identifies itself honestly, waits between
requests, and stops with a readable message instead of a traceback when a page
does not contain what the selector asks for. See "Responsible use" in the
README before pointing it at a site.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# WordPress block themes wrap the post body in <div class="entry-content ...">.
# This is a CSS selector, so it matches that class among others in any order —
# the page does not have to list its classes exactly the way this site does.
DEFAULT_SELECTOR = "div.entry-content"

# Themes mark the link to the following chapter with rel="next".
DEFAULT_NEXT_SELECTOR = 'a[rel="next"]'

USER_AGENT = "novel-scraper/1.0 (+https://github.com/joserico00/novel-scraper)"
DEFAULT_DELAY = 2.0
DEFAULT_TIMEOUT = 20.0
DEFAULT_RETRIES = 3


class ScraperError(Exception):
    """Something went wrong that the user can act on."""


class ChapterNotFound(ScraperError):
    """The page loaded, but the selector did not match anything in it."""


class DisallowedByRobots(ScraperError):
    """The site's robots.txt asks clients not to fetch this path."""


@dataclass
class Chapter:
    url: str
    title: str
    text: str
    next_url: str | None = None

    def __str__(self) -> str:
        return f"{self.title}\n\n{self.text}" if self.title else self.text


def build_session(user_agent: str = USER_AGENT, retries: int = DEFAULT_RETRIES) -> requests.Session:
    """A session that reuses one connection and backs off on 429/5xx."""
    session = requests.Session()
    session.headers["User-Agent"] = user_agent
    retry = Retry(
        total=retries,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def fetch(session: requests.Session, url: str, timeout: float = DEFAULT_TIMEOUT) -> str:
    """Return the page's HTML, raising on a 4xx/5xx instead of parsing an error page."""
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    if response.encoding is None:
        response.encoding = response.apparent_encoding
    return response.text


def robots_allows(
    session: requests.Session,
    url: str,
    user_agent: str = USER_AGENT,
    timeout: float = DEFAULT_TIMEOUT,
) -> bool:
    """Ask the site's robots.txt whether this path may be fetched.

    A missing or unreadable robots.txt means "no rules stated", which the
    standard treats as allowed.
    """
    parts = urlparse(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    try:
        response = session.get(robots_url, timeout=timeout)
    except requests.RequestException:
        return True
    if response.status_code != 200:
        return True

    parser = RobotFileParser()
    parser.parse(response.text.splitlines())
    return parser.can_fetch(user_agent, url)


def extract_chapter(
    html: str,
    url: str = "",
    selector: str = DEFAULT_SELECTOR,
    next_selector: str = DEFAULT_NEXT_SELECTOR,
) -> Chapter:
    """Pull the chapter body, its title and the link to the next chapter out of a page."""
    soup = BeautifulSoup(html, "html.parser")

    body = soup.select_one(selector)
    if body is None:
        raise ChapterNotFound(
            f"No element matched {selector!r} on {url or 'the page'}.\n"
            "Open the chapter in a browser, inspect the element holding the story "
            "text, and pass its selector with --selector."
        )

    # Separating on newlines keeps paragraph breaks, which .text does not:
    # it would run the last word of one paragraph into the first of the next.
    text = body.get_text("\n", strip=True)

    heading = soup.find("h1") or soup.find("title")
    title = heading.get_text(strip=True) if heading else ""

    next_url = None
    link = soup.select_one(next_selector)
    if link is not None and link.get("href"):
        next_url = urljoin(url, link["href"])

    return Chapter(url=url, title=title, text=text, next_url=next_url)


def scrape(
    url: str,
    chapters: int = 1,
    session: requests.Session | None = None,
    selector: str = DEFAULT_SELECTOR,
    next_selector: str = DEFAULT_NEXT_SELECTOR,
    delay: float = DEFAULT_DELAY,
    timeout: float = DEFAULT_TIMEOUT,
    check_robots: bool = True,
    sleep=time.sleep,
):
    """Yield chapters, following the next-chapter link up to `chapters` pages."""
    session = session or build_session()
    seen: set[str] = set()

    for index in range(chapters):
        if url in seen:            # some themes link the last chapter to itself
            return
        seen.add(url)

        if check_robots and not robots_allows(session, url, session.headers.get("User-Agent", USER_AGENT), timeout):
            raise DisallowedByRobots(
                f"{url} is disallowed by the site's robots.txt. "
                "Respect that, or pass --ignore-robots if you have permission."
            )

        if index:
            sleep(delay)           # be a polite guest between pages

        chapter = extract_chapter(fetch(session, url, timeout), url, selector, next_selector)
        yield chapter

        if not chapter.next_url:
            return
        url = chapter.next_url


def get_novel_text(
    url: str,
    session: requests.Session | None = None,
    selector: str = DEFAULT_SELECTOR,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """One chapter's text, for importing from another script.

    Unlike the first version of this module, importing it fetches nothing: you
    choose when a request happens, and which URL it goes to.
    """
    session = session or build_session()
    return extract_chapter(fetch(session, url, timeout), url, selector).text


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download a web-novel chapter and print or save it as plain text.",
        epilog="Read the site's terms and robots.txt first; keep downloads to personal use.",
    )
    parser.add_argument("url", help="URL of the chapter to download")
    parser.add_argument("-o", "--output", help="write the text here instead of stdout")
    parser.add_argument("-n", "--chapters", type=int, default=1,
                        help="how many chapters to follow from this one (default: 1)")
    parser.add_argument("--selector", default=DEFAULT_SELECTOR,
                        help=f"CSS selector for the chapter body (default: {DEFAULT_SELECTOR})")
    parser.add_argument("--next-selector", default=DEFAULT_NEXT_SELECTOR,
                        help=f"CSS selector for the next-chapter link (default: {DEFAULT_NEXT_SELECTOR})")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY,
                        help=f"seconds to wait between pages (default: {DEFAULT_DELAY})")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help=f"seconds to wait for each response (default: {DEFAULT_TIMEOUT})")
    parser.add_argument("--user-agent", default=USER_AGENT, help="how to identify this client")
    parser.add_argument("--ignore-robots", action="store_true",
                        help="skip the robots.txt check (only with the site's permission)")
    args = parser.parse_args(argv)
    if args.chapters < 1:
        parser.error("--chapters must be at least 1")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    session = build_session(args.user_agent)

    try:
        chapters = list(scrape(
            args.url,
            chapters=args.chapters,
            session=session,
            selector=args.selector,
            next_selector=args.next_selector,
            delay=args.delay,
            timeout=args.timeout,
            check_robots=not args.ignore_robots,
        ))
    except (ScraperError, requests.RequestException) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    output = "\n\n\n".join(str(chapter) for chapter in chapters)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(output + "\n")
        print(f"Saved {len(chapters)} chapter(s) to {args.output}", file=sys.stderr)
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
