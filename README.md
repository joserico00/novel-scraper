# Novel Scraper

A short Python script that downloads one web-novel chapter page, finds the chapter body in the HTML with BeautifulSoup, and prints it as plain text. It is a minimal example of the `requests` + `BeautifulSoup` workflow: fetch, parse, locate one element, extract its text. The chapter URL is hard-coded, and the CSS class it looks for matches the post-content container used by WordPress block themes.

## Contents

| File | Description |
|---|---|
| `scraper.py` | `get_novel_text(url)` plus a module-level call that fetches and prints one chapter |

## How `scraper.py` works

```
requests.get(url) ──► response.text (HTML)
        │
        ▼
BeautifulSoup(html, "html.parser")
        │
        ▼
soup.find("div", {"class": "entry-content wp-block-post-content has-global-padding is-layout-constrained"})
        │
        ├──► print(text_div)          # debug: the raw HTML of the element
        ▼
text_div.text ──► returned, then printed
```

`get_novel_text(url)` does the following:

1. **Fetch:** `requests.get(url)` sends a plain GET request with the library's default headers. There is no timeout and no status-code check.
2. **Parse:** `BeautifulSoup(response.text, 'html.parser')` builds a parse tree with Python's built-in HTML parser, so `lxml` is not needed.
3. **Find the chapter container:** `soup.find('div', {'class': "entry-content wp-block-post-content has-global-padding is-layout-constrained"})` returns the first `<div>` whose `class` attribute matches that string. When the class string contains spaces, BeautifulSoup compares it with the whole attribute value, so the classes must appear in the same order on the page. The comment in the code notes that other sites will need a different tag, class or id.
4. **Debug print:** `print(text_div)` writes the element's full HTML to stdout.
5. **Extract text:** `text_div.text` returns all text inside the div with the tags removed. Line breaks come from whitespace in the page source, not from `<p>` boundaries.

At module level, the script calls `get_novel_text(...)` with one chapter URL (line 15) and prints the result. **Output** goes to stdout: first the HTML dump from step 4, then the plain chapter text.

### Limitations

- **Fragile selector:** if the page uses a different theme, lists the classes in a different order, returns an error page, or blocks the request, `find` returns `None`. The script then fails with `AttributeError: 'NoneType' object has no attribute 'text'`.
- **No error handling:** no timeout, retry, `response.raise_for_status()` or explicit encoding. `response.text` uses the encoding that `requests` guesses.
- **One page per run:** to fetch another chapter you must edit the URL. The request runs at import time (there is no `if __name__ == "__main__":` guard), so importing `get_novel_text` from another script also fetches the hard-coded chapter.
- Anything inside the content `<div>`, such as author notes or embedded navigation, ends up in the output.

## Responsible use

Before scraping any site:

- **Read the site's Terms of Service.** Many novel and publishing sites prohibit automated downloading or republishing.
- **Check `robots.txt`** (for example `https://<site>/robots.txt`) and respect disallowed paths and crawl delays.
- **Limit your request rate.** If you extend the script to loop over chapters, add a delay between requests and identify your client honestly.
- **Respect copyright.** Keep downloaded chapters for permitted personal use, don't redistribute them, and support authors and translators through official channels.

## Requirements

- Python 3.7+
- `requests`
- `beautifulsoup4`

```bash
pip install requests beautifulsoup4
```

## Usage

```bash
python3 scraper.py                 # prints the element's HTML, then the chapter text
python3 scraper.py > chapter.txt   # save the output (the HTML dump comes first)
```

To adapt it to another chapter or site:

1. Open the chapter in a browser and use the developer tools to inspect the element that holds the story text.
2. Change the URL passed to `get_novel_text(...)` at the bottom of `scraper.py`.
3. Change the tag and `class` in the `soup.find(...)` call to match that element.

## Author

Jose E. Rodriguez Rios
