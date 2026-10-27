"""
waivatar — Avatar Wiki Ingestion Script
Fetches every article from the Avatar fandom wiki via the MediaWiki Action
API, strips wikitext to plaintext, and writes a gzipped chunk snapshot plus
a SNAPSHOT metadata file next to this script.

    python data/ingest_wiki.py

The snapshot is committed to the repo and baked into the data image so a
fresh install is populated without touching the wiki. sync_wiki.py keeps a
running deployment current afterwards.
"""

import time
from datetime import datetime, timezone

import wiki
from snapshot import CHUNKS_FILE, SNAPSHOT_FILE, write_chunks, write_snapshot_meta


def main():
    pages = wiki.list_pages()
    pageids = sorted(pages)

    chunks: list[dict] = []
    indexed = 0
    skipped = 0

    for i, batch in enumerate(wiki.batched(pageids, wiki.CONTENT_BATCH), 1):
        # fetch_wikitext retries internally; if it still fails, let the
        # exception abort the run rather than write a snapshot with a hole.
        fetched = wiki.fetch_wikitext(batch)

        for pageid in batch:
            page = fetched.get(pageid)
            page_chunks = wiki.page_to_chunks(pageid, page) if page else []
            if page_chunks:
                chunks.extend(page_chunks)
                indexed += 1
            else:
                skipped += 1

        if i % 10 == 0:
            print(f"  [{min(i * wiki.CONTENT_BATCH, len(pageids))}/{len(pageids)}] processed — {len(chunks)} chunks so far")
        time.sleep(wiki.REQUEST_DELAY)

    write_chunks(chunks, CHUNKS_FILE)
    meta = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": wiki.BASE_URL,
        "pages_seen": len(pageids),
        "articles": indexed,
        "chunks": len(chunks),
    }
    write_snapshot_meta(meta, SNAPSHOT_FILE)

    print("\nDone.")
    print(f"  Articles indexed : {indexed}")
    print(f"  Pages skipped    : {skipped}")
    print(f"  Total chunks     : {len(chunks)}")
    print(f"  Output file      : {CHUNKS_FILE}")
    print(f"  Snapshot meta    : {SNAPSHOT_FILE}")


if __name__ == "__main__":
    main()
