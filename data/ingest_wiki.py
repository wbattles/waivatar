"""
waivatar — Avatar Wiki Ingestion Script
Fetches all articles from the Avatar fandom wiki via MediaWiki Action API,
strips wikitext to clean plaintext, and saves chunked output as JSONL.
"""

import json
import time
import re
import requests
import mwparserfromhell

# ── Config ────────────────────────────────────────────────────────────────────

BASE_URL = "https://james-camerons-avatar.fandom.com/api.php"
OUTPUT_FILE = "avatar_chunks.jsonl"
CHUNK_SIZE = 500 
CHUNK_OVERLAP = 50
REQUEST_DELAY = 0.5

HEADERS = {
    "User-Agent": "waivatar-ingest/1.0 (waisuite; contact@waisuite.com)"
}

# Namespaces to skip (talk pages, user pages, etc.)
SKIP_NAMESPACES = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15}

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_all_page_titles() -> list[dict]:
    """Paginate through all pages in namespace 0 (main articles)."""
    titles = []
    params = {
        "action": "query",
        "list": "allpages",
        "apnamespace": 0,
        "aplimit": 500,
        "format": "json",
    }

    print("Fetching page list...")
    while True:
        resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        batch = data["query"]["allpages"]
        titles.extend(batch)
        print(f"  fetched {len(titles)} titles so far...")

        cont = data.get("continue", {}).get("apcontinue")
        if not cont:
            break
        params["apcontinue"] = cont
        time.sleep(REQUEST_DELAY)

    print(f"Total pages found: {len(titles)}")
    return titles


def fetch_article_wikitext(page_id: int) -> tuple[str, str] | None:
    """Fetch wikitext for a single page by ID. Returns (title, wikitext) or None."""
    params = {
        "action": "query",
        "pageids": page_id,
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "format": "json",
    }
    resp = requests.get(BASE_URL, params=params, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    page = data["query"]["pages"].get(str(page_id))
    if not page or "revisions" not in page:
        return None

    title = page["title"]
    wikitext = page["revisions"][0]["slots"]["main"]["*"]
    return title, wikitext


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
    text = text.strip()

    return text


def chunk_text(title: str, text: str) -> list[dict]:
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
        chunk_text = " ".join(chunk_words)

        chunks.append({
            "id": f"{title}::{chunk_index}",
            "title": title,
            "chunk_index": chunk_index,
            "text": chunk_text,
            "word_count": len(chunk_words),
        })

        chunk_index += 1
        if end >= len(words):
            break
        start = end - CHUNK_OVERLAP

    return chunks


def is_junk_article(title: str, text: str) -> bool:
    """Filter out stub/empty/redirect articles not worth indexing."""
    if len(text.split()) < 30:
        return True
    junk_prefixes = ["Forum:", "Thread:", "Board:", "Message Wall:"]
    if any(title.startswith(p) for p in junk_prefixes):
        return True
    return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    pages = get_all_page_titles()
    total_chunks = 0
    skipped = 0

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        for i, page in enumerate(pages):
            page_id = page["pageid"]
            title = page["title"]

            try:
                result = fetch_article_wikitext(page_id)
                if result is None:
                    skipped += 1
                    continue

                _, wikitext = result

                if wikitext.strip().lower().startswith("#redirect"):
                    skipped += 1
                    continue

                plaintext = wikitext_to_plaintext(wikitext)

                if is_junk_article(title, plaintext):
                    skipped += 1
                    continue

                chunks = chunk_text(title, plaintext)
                for chunk in chunks:
                    out.write(json.dumps(chunk, ensure_ascii=False) + "\n")

                total_chunks += len(chunks)

                if (i + 1) % 50 == 0:
                    print(f"  [{i+1}/{len(pages)}] processed — {total_chunks} chunks so far")

            except Exception as e:
                print(f"  ERROR on '{title}' (id={page_id}): {e}")
                skipped += 1

            time.sleep(REQUEST_DELAY)

    print(f"\nDone.")
    print(f"  Pages processed : {len(pages) - skipped}")
    print(f"  Pages skipped   : {skipped}")
    print(f"  Total chunks    : {total_chunks}")
    print(f"  Output file     : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
