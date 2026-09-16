# Novel Scraper

A small command-line tool that downloads a web-novel chapter and saves it as plain text. Give it the chapter URL; it fetches the page, pulls out the story body, and can follow the site's next-chapter links for a run of chapters.

```bash
python scraper.py https://example.com/chapter-1/                     # print one chapter
python scraper.py https://example.com/chapter-1/ -n 5 -o book.txt    # five chapters into a file
```

It checks `robots.txt` before fetching, identifies itself honestly, waits between requests, and stops with a readable message rather than a traceback when a page is not what it expected.

## Contents

| File | Description |
|---|---|
| `scraper.py` | The tool: `fetch`, `extract_chapter`, `robots_allows`, `scrape`, and the CLI |
| `tests/test_scraper.py` | 20 tests, all offline — a fake session serves canned pages |

## Options

| Option | Default | What it does |
|---|---|---|
| `url` | required | Chapter to start from |
| `-n`, `--chapters` | `1` | How many chapters to follow from that one |
| `-o`, `--output` | stdout | Write the text to this file instead |
| `--selector` | `div.entry-content` | CSS selector for the chapter body |
| `--next-selector` | `a[rel="next"]` | CSS selector for the next-chapter link |
| `--delay` | `2.0` | Seconds to wait between pages |
| `--timeout` | `20.0` | Seconds to wait for each response |
| `--user-agent` | `novel-scraper/1.0 …` | How the client identifies itself |
| `--ignore-robots` | off | Skip the `robots.txt` check (only with the site's permission) |

The defaults suit WordPress block themes, which wrap the post body in `<div class="entry-content …">` and mark the following chapter with `rel="next"`. For any other site, open a chapter in your browser, inspect the element holding the story text, and pass its selector with `--selector`.

## How it works

```
robots.txt ──► allowed?          ──no──► stop with an explanation
     │ yes
     ▼
session.get(url, timeout)        retries 429/5xx with backoff
     │
     ▼
raise_for_status()               an error page is an error, not content
     │
     ▼
soup.select_one(selector)        ──no match──► ChapterNotFound, naming --selector
     │
     ▼
get_text("\n")  ──► chapter text, paragraph breaks intact
soup.select_one('a[rel="next"]') ──► next URL, resolved against the current one
```

Some details worth knowing:

- **The selector matches classes individually.** A page listing its classes in a different order still matches, which an exact `class="a b c"` comparison would not.
- **Paragraph breaks survive.** Text is extracted with a newline separator, so the last word of one paragraph does not run into the first word of the next.
- **A chapter that links to itself does not loop.** Visited URLs are remembered, and the run stops when there is no next link.
- **Importing fetches nothing.** `get_novel_text(url)` is available for use from another script, and nothing runs until you call it.

## Requirements

- Python 3.9+
- `requests`, `beautifulsoup4`

```bash
pip install -r requirements.txt
```

## Tests

```bash
python tests/test_scraper.py        # or: python -m unittest discover tests
```

The tests never touch the network: a fake session serves canned HTML, so they also cover the failure paths (404, blocked by robots, selector miss) that are awkward to trigger against a real site.

## Responsible use

Before pointing this at any site:

- **Read the site's Terms of Service.** Many novel and publishing sites prohibit automated downloading or republishing.
- **Respect `robots.txt`.** The tool checks it for you; `--ignore-robots` exists for sites you have permission to crawl, not as a convenience.
- **Keep the request rate low.** The default two-second delay is a floor, not a target, and `--delay` raises it.
- **Respect copyright.** Downloaded chapters are for permitted personal use. Don't redistribute them, and support authors and translators through official channels.

## Author

Jose E. Rodriguez Rios
