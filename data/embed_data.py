"""
waivatar — Snapshot Load Script
Reads the chunk snapshot, embeds anything new or changed, and stores vectors
in Qdrant. Points not present in the snapshot are deleted, so the collection
mirrors the snapshot exactly after a run.

    QDRANT_URL=http://localhost:6333 python data/embed_data.py

Env:
    OPENAI_API_KEY    required
    OPENAI_MODEL      default text-embedding-3-small
    QDRANT_URL        default: embedded Qdrant at ./qdrant_storage
    CHUNKS_FILE       default: data/avatar_chunks.jsonl.gz
    RESET_COLLECTION  true/1/yes to drop and recreate the collection first
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

import store
from snapshot import CHUNKS_FILE, read_chunks

RESET_COLLECTION = os.environ.get("RESET_COLLECTION", "").lower() in {"1", "true", "yes"}


def main():
    qdrant = store.get_qdrant()
    store.ensure_collection(qdrant, reset=RESET_COLLECTION)

    print(f"\nLoading chunks from {CHUNKS_FILE}...")
    chunks = read_chunks(CHUNKS_FILE)
    print(f"Loaded {len(chunks)} chunks.")

    existing = store.scan_existing(qdrant)
    if existing:
        print(f"Existing vectors   : {len(existing)}")

    # A deployment that has run sync_wiki.py may hold pages newer than this
    # snapshot. Never move those backwards: skip their chunks and keep their
    # points. Pages the snapshot does not know about are left alone too; the
    # sync is the only thing that deletes pages.
    stored_revid: dict[int, int] = {}
    for info in existing.values():
        if info["pageid"] is not None and info["revid"] is not None:
            stored_revid[info["pageid"]] = max(stored_revid.get(info["pageid"], 0), info["revid"])

    to_load = [c for c in chunks if stored_revid.get(c["pageid"], -1) <= c["revid"]]
    newer = len(chunks) - len(to_load)
    if newer:
        print(f"Already newer      : {newer} chunks (kept from a previous sync)")

    embedded, failed = store.upsert_chunks(qdrant, to_load, existing)

    loaded_pages = {c["pageid"] for c in to_load}
    keep = {store.point_id(c["id"]) for c in to_load}
    for pid, info in existing.items():
        if info["pageid"] is not None and info["pageid"] not in loaded_pages:
            keep.add(pid)
    pruned = store.prune(qdrant, existing, keep)

    print("\nDone.")
    print(f"  Embedded : {embedded}")
    print(f"  Failed   : {failed}")
    print(f"  Unchanged: {len(to_load) - embedded - failed}")
    print(f"  Pruned   : {pruned}")
    print(f"  Total vectors in collection: {store.count(qdrant)}")

    if failed:
        print(f"\nERROR: {failed} chunks could not be embedded; exiting non-zero so the run is retried.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
