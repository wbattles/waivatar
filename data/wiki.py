"""
waivatar — MediaWiki client and text processing
Shared by ingest_wiki.py (full snapshot) and sync_wiki.py (incremental sweep).
"""

import re
import time

import requests
import mwparserfromhell

# ── Config ────────────────────────────────────────────────────────────────────

BASE_URL = "https://james-camerons-avatar.fandom.com/api.php"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
REQUEST_DELAY = 0.5
RETRIES = 4                      # attempts per API call
RETRY_BACKOFF = (2, 5, 10)       # seconds between attempts

LIST_BATCH = 500     # pages per allpages request (API max for non-bots)
CONTENT_BATCH = 50   # pages per content request (API max when fetching content)
MIN_WORDS = 30       # articles shorter than this are treated as junk

HEADERS = {
    "User-Agent": "waivatar-ingest/1.0 (waisuite; contact@waisuite.com)"
}

JUNK_PREFIXES = ("Forum:", "Thread:", "Board:", "Message Wall:")

# ── API ───────────────────────────────────────────────────────────────────────

_session = requests.Session()
_session.headers.update(HEADERS)


def api_get(params: dict) -> dict:
    """
    Single GET against the Action API with retries. Raises after RETRIES
    failed attempts so callers never proceed on a partial result.
    """
    params = {"format": "json", **params}
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            resp = _session.get(BASE_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(f"MediaWiki API error: {data['error']}")
            return data
        except Exception as e:  # network, HTTP, JSON, or API error
            last = e
            if attempt < RETRIES - 1:
                wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                print(f"  API call failed ({e}); retrying in {wait}s")
                time.sleep(wait)
    raise RuntimeError(f"MediaWiki API call failed after {RETRIES} attempts: {last}")


def list_pages() -> dict[int, dict]:
    """
    Walk every page in namespace 0 and return {pageid: {"title", "revid"}}.
    revid is the page's latest revision, which is what the sync compares.
    """
    pages: dict[int, dict] = {}
    params = {
        "action": "query",
        "generator": "allpages",
        "gapnamespace": 0,
        "gapfilterredir": "nonredirects",  # redirects are never indexed; skip them server-side
        "gaplimit": LIST_BATCH,
        "prop": "revisions",
        "rvprop": "ids",
    }

    print("Listing pages...")
    while True:
        data = api_get(params)
        for page in data.get("query", {}).get("pages", {}).values():
            revs = page.get("revisions")
            if not revs:
                continue
            pages[page["pageid"]] = {"title": page["title"], "revid": revs[0]["revid"]}
        print(f"  {len(pages)} pages listed...")

        cont = data.get("continue")
        if not cont:
            break
        params.update(cont)
        time.sleep(REQUEST_DELAY)

    print(f"Total pages: {len(pages)}")
    return pages


def fetch_wikitext(pageids: list[int]) -> dict[int, dict]:
    """
    Fetch latest wikitext for up to CONTENT_BATCH pages in one request.
    Returns {pageid: {"title", "revid", "wikitext"}}. Pages that are missing
    or have no revision are omitted.
    """
    if len(pageids) > CONTENT_BATCH:
        raise ValueError(f"fetch_wikitext takes at most {CONTENT_BATCH} pageids")

    results: dict[int, dict] = {}
    params = {
        "action": "query",
        "pageids": "|".join(str(p) for p in pageids),
        "prop": "revisions",
        "rvprop": "content|ids",
        "rvslots": "main",
    }

    # The API may split a large batch across continuation responses.
    while True:
        data = api_get(params)
        for page in data.get("query", {}).get("pages", {}).values():
            revs = page.get("revisions")
            if not revs or "missing" in page:
                continue
            results[page["pageid"]] = {
                "title": page["title"],
                "revid": revs[0]["revid"],
                "wikitext": revs[0]["slots"]["main"]["*"],
            }
        cont = data.get("continue")
        if not cont:
            break
        params.update(cont)
        time.sleep(REQUEST_DELAY)

    return results


def batched(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


# ── Text processing ───────────────────────────────────────────────────────────

def wikitext_to_plaintext(wikitext: str) -> str:
    """Strip wikitext markup and return clean plaintext."""
    parsed = mwparserfromhell.parse(wikitext)

    for template in parsed.filter_templates():
        try:
            parsed.remove(template)
        except Exception:
            pass

    text = parsed.strip_code()

    text = re.sub(r"\[\[Category:[^\]]+\]\]", "", text)
    text = re.sub(r"\[\[File:[^\]]+\]\]", "", text)
    text = re.sub(r"\[\[Image:[^\]]+\]\]", "", text)
    text = re.sub(r"={2,}(.+?)={2,}", r"\n\n## \1\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def is_redirect(wikitext: str) -> bool:
    return wikitext.strip().lower().startswith("#redirect")


def is_junk_article(title: str, text: str) -> bool:
    """Filter out stub/empty articles not worth indexing."""
    if len(text.split()) < MIN_WORDS:
        return True
    return title.startswith(JUNK_PREFIXES)


def chunk_text(title: str, text: str, pageid: int, revid: int) -> list[dict]:
    """Split text into overlapping word-count chunks."""
    words = text.split()
    if not words:
        return []

    chunks = []
    start = 0
    chunk_index = 0

    while start < len(words):
        end = start + CHUNK_SIZE
        chunk_words = words[start:end]

        chunks.append({
            "id": f"{title}::{chunk_index}",
            "title": title,
            "pageid": pageid,
            "revid": revid,
            "chunk_index": chunk_index,
            "text": " ".join(chunk_words),
            "word_count": len(chunk_words),
        })

        chunk_index += 1
        if end >= len(words):
            break
        start = end - CHUNK_OVERLAP

    return chunks


def page_to_chunks(pageid: int, page: dict) -> list[dict]:
    """
    Convert a fetched page into chunks. Returns [] for redirects and junk,
    which callers should treat as "this page is not indexed".
    """
    wikitext = page["wikitext"]
    if is_redirect(wikitext):
        return []
    plaintext = wikitext_to_plaintext(wikitext)
    if is_junk_article(page["title"], plaintext):
        return []
    return chunk_text(page["title"], plaintext, pageid, page["revid"])
