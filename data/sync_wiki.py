"""
waivatar — Incremental Wiki Sync
Converges the Qdrant collection on the live Avatar wiki by comparing each
page's latest revision ID against what is stored. Only pages whose revision
changed are refetched; only chunks whose text changed are re-embedded. Pages
that were deleted, renamed, redirected, or shrank to junk are removed.

    QDRANT_URL=http://localhost:6333 python data/sync_wiki.py

Safe to run on any schedule. A collection loaded from a year-old snapshot
and one loaded yesterday both end up identical to the wiki after one run.
Points written before revision tracking existed are refetched once.
"""

import sys
import time

from dotenv import load_dotenv

load_dotenv()

import store
import wiki


def main() -> int:
    qdrant = store.get_qdrant()
    store.ensure_collection(qdrant)

    existing = store.scan_existing(qdrant)
    print(f"Existing vectors   : {len(existing)}")

    # Group stored points by page so we can tell which pages are current.
    by_page: dict[int, dict] = {}
    untracked: set[int] = set()
    for pid, info in existing.items():
        if info["pageid"] is None:
            untracked.add(pid)
            continue
        entry = by_page.setdefault(info["pageid"], {"revid": info["revid"], "ids": set()})
        entry["ids"].add(pid)
        if entry["revid"] != info["revid"]:
            entry["revid"] = None  # mixed revisions within a page: refetch it

    pages = wiki.list_pages()

    changed = [p for p, meta in pages.items() if by_page.get(p, {}).get("revid") != meta["revid"]]
    removed = [p for p in by_page if p not in pages]

    print(f"Pages on wiki      : {len(pages)}")
    print(f"Pages to refetch   : {len(changed)}")
    print(f"Pages removed      : {len(removed)}")
    if untracked:
        print(f"Untracked points   : {len(untracked)} (pre-revision data; will be reconciled)")

    keep: set[int] = set()
    for p, entry in by_page.items():
        if p in pages and p not in changed:
            keep |= entry["ids"]

    embedded = 0
    dropped_pages = 0
    for i, batch in enumerate(wiki.batched(sorted(changed), wiki.CONTENT_BATCH), 1):
        fetched = wiki.fetch_wikitext(batch)
        for pageid in batch:
            page = fetched.get(pageid)
            chunks = wiki.page_to_chunks(pageid, page) if page else []
            if not chunks:
                dropped_pages += 1
                continue
            embedded += store.upsert_chunks(qdrant, chunks, existing)
            keep |= {store.point_id(c["id"]) for c in chunks}
        print(f"  [{min(i * wiki.CONTENT_BATCH, len(changed))}/{len(changed)}] pages refetched")
        time.sleep(wiki.REQUEST_DELAY)

    pruned = store.prune(qdrant, existing, keep)

    print("\nDone.")
    print(f"  Pages refetched : {len(changed)}")
    print(f"  Pages dropped   : {dropped_pages + len(removed)}")
    print(f"  Chunks embedded : {embedded}")
    print(f"  Points pruned   : {pruned}")
    print(f"  Total vectors in collection: {store.count(qdrant)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
