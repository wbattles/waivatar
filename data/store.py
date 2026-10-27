"""
waivatar — Qdrant + embedding store
Shared by embed_data.py (snapshot load) and sync_wiki.py (incremental sweep).

Point IDs are derived deterministically from the chunk id ("<title>::<n>"),
so re-running against an existing collection upserts in place. Chunks whose
text is unchanged are not re-embedded; only their pageid/revid payload is
refreshed.
"""

import hashlib
import os
import time

from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

# ── Config ────────────────────────────────────────────────────────────────────

COLLECTION_NAME = "avatar_wiki"
BATCH_SIZE = 256
VECTOR_SIZE = 1536
MAX_CHARS = 6000

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "text-embedding-3-small")

QDRANT_PATH = "./qdrant_storage"
QDRANT_URL = os.environ.get("QDRANT_URL")

# ── Clients ───────────────────────────────────────────────────────────────────

_openai: OpenAI | None = None


def openai_client() -> OpenAI:
    """Created lazily so read-only runs (nothing to embed) need no key."""
    global _openai
    if _openai is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is required to embed chunks")
        _openai = OpenAI(api_key=OPENAI_API_KEY)
    return _openai


def get_qdrant() -> QdrantClient:
    if QDRANT_URL:
        print(f"Qdrant             : {QDRANT_URL}")
        return QdrantClient(url=QDRANT_URL)
    print(f"Qdrant             : local ({QDRANT_PATH})")
    return QdrantClient(path=QDRANT_PATH)


def ensure_collection(qdrant: QdrantClient, reset: bool = False) -> None:
    existing = [c.name for c in qdrant.get_collections().collections]

    if reset and COLLECTION_NAME in existing:
        qdrant.delete_collection(collection_name=COLLECTION_NAME)
        existing.remove(COLLECTION_NAME)
        print(f"Reset collection   : {COLLECTION_NAME}")

    if COLLECTION_NAME not in existing:
        qdrant.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        print(f"Created collection : {COLLECTION_NAME}")
    else:
        print(f"Collection exists  : {COLLECTION_NAME}")


# ── Hashing ───────────────────────────────────────────────────────────────────

def point_id(chunk_id: str) -> int:
    digest = hashlib.sha256(chunk_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big") & ((1 << 63) - 1)


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── Read ──────────────────────────────────────────────────────────────────────

def scan_existing(qdrant: QdrantClient) -> dict[int, dict]:
    """
    Return {point_id: {"text_hash", "pageid", "revid"}} for every point.
    Points written before pageid/revid were tracked have those set to None.
    """
    existing: dict[int, dict] = {}
    offset = None
    while True:
        points, offset = qdrant.scroll(
            collection_name=COLLECTION_NAME,
            limit=10_000,
            offset=offset,
            with_payload=["text", "text_hash", "pageid", "revid"],
            with_vectors=False,
        )
        for point in points:
            payload = point.payload or {}
            h = payload.get("text_hash")
            if h is None and payload.get("text"):
                h = text_hash(payload["text"])
            existing[point.id] = {
                "text_hash": h,
                "pageid": payload.get("pageid"),
                "revid": payload.get("revid"),
            }
        if offset is None:
            break
    return existing


# ── Write ─────────────────────────────────────────────────────────────────────

def embed_batch(texts: list[str]) -> list[list[float]]:
    response = openai_client().embeddings.create(model=OPENAI_MODEL, input=texts)
    return [r.embedding for r in response.data]


def _payload(chunk: dict) -> dict:
    return {
        "chunk_id": chunk["id"],
        "title": chunk["title"],
        "pageid": chunk.get("pageid"),
        "revid": chunk.get("revid"),
        "chunk_index": chunk["chunk_index"],
        "word_count": chunk["word_count"],
        "text_hash": text_hash(chunk["text"]),
        "text": chunk["text"],
    }


def upsert_chunks(qdrant: QdrantClient, chunks: list[dict], existing: dict[int, dict]) -> int:
    """
    Embed and upsert chunks whose text is new or changed. Chunks whose text
    hash already matches get only their pageid/revid payload refreshed.
    Returns the number of chunks embedded.
    """
    to_embed: list[dict] = []
    to_touch: dict[tuple, list[int]] = {}

    for chunk in chunks:
        pid = point_id(chunk["id"])
        cur = existing.get(pid)
        if cur and cur["text_hash"] == text_hash(chunk["text"]):
            if (cur["pageid"], cur["revid"]) != (chunk.get("pageid"), chunk.get("revid")):
                to_touch.setdefault((chunk.get("pageid"), chunk.get("revid")), []).append(pid)
        else:
            to_embed.append(chunk)

    for (pageid, revid), ids in to_touch.items():
        qdrant.set_payload(
            collection_name=COLLECTION_NAME,
            payload={"pageid": pageid, "revid": revid},
            points=ids,
        )

    embedded = 0
    for i in range(0, len(to_embed), BATCH_SIZE):
        batch = to_embed[i : i + BATCH_SIZE]
        texts = [c["text"][:MAX_CHARS] for c in batch]
        try:
            vectors = embed_batch(texts)
        except Exception as e:
            print(f"  ERROR embedding batch at {i}: {e}")
            time.sleep(5)
            continue
        qdrant.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                PointStruct(id=point_id(c["id"]), vector=v, payload=_payload(c))
                for c, v in zip(batch, vectors)
            ],
        )
        embedded += len(batch)
        print(f"  [{embedded}/{len(to_embed)}] embedded and stored")

    return embedded


def delete_points(qdrant: QdrantClient, ids: list[int]) -> None:
    for i in range(0, len(ids), 1000):
        qdrant.delete(collection_name=COLLECTION_NAME, points_selector=ids[i : i + 1000])


def prune(qdrant: QdrantClient, existing: dict[int, dict], keep: set[int]) -> int:
    """Delete every existing point whose id is not in `keep`. Returns count."""
    stale = [pid for pid in existing if pid not in keep]
    if stale:
        delete_points(qdrant, stale)
    return len(stale)


def count(qdrant: QdrantClient) -> int:
    return qdrant.count(COLLECTION_NAME).count
