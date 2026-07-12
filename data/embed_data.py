"""
waivatar — Embed & Store Script
Reads avatar_chunks.jsonl, embeds chunks using the configured provider,
and stores vectors in Qdrant. Run locally then rsync qdrant_storage/ to tcz,
or set QDRANT_URL to target a running instance directly.
"""

import json
import hashlib
import os
import time

from dotenv import load_dotenv
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

INPUT_FILE = "avatar_chunks.jsonl"
COLLECTION_NAME = "avatar_wiki"
BATCH_SIZE = 256
VECTOR_SIZE = 1536

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL   = os.environ.get("OPENAI_MODEL", "text-embedding-3-small")

QDRANT_PATH = "./qdrant_storage"
QDRANT_URL  = os.environ.get("QDRANT_URL")
RESET_COLLECTION = os.environ.get("RESET_COLLECTION", "").lower() in {"1", "true", "yes"}

# ── Embedding ─────────────────────────────────────────────────────────────────

openai_client = OpenAI(api_key=OPENAI_API_KEY)

def embed_batch(texts: list[str]) -> list[list[float]]:
    response = openai_client.embeddings.create(model=OPENAI_MODEL, input=texts)
    return [r.embedding for r in response.data]

# ── Qdrant client ─────────────────────────────────────────────────────────────

if QDRANT_URL:
    print(f"Qdrant             : {QDRANT_URL}")
    qdrant = QdrantClient(url=QDRANT_URL)
else:
    print(f"Qdrant             : local ({QDRANT_PATH})")
    qdrant = QdrantClient(path=QDRANT_PATH)

# ── Create collection if needed ───────────────────────────────────────────────

existing = [c.name for c in qdrant.get_collections().collections]

if RESET_COLLECTION and COLLECTION_NAME in existing:
    qdrant.delete_collection(collection_name=COLLECTION_NAME)
    existing.remove(COLLECTION_NAME)
    print(f"Reset collection  : {COLLECTION_NAME}")

if COLLECTION_NAME not in existing:
    qdrant.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
    )
    print(f"Created collection : {COLLECTION_NAME}")
else:
    print(f"Collection exists  : {COLLECTION_NAME}")

# ── Load chunks ───────────────────────────────────────────────────────────────

print(f"\nLoading chunks from {INPUT_FILE}...")
chunks = []
with open(INPUT_FILE, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line:
            chunks.append(json.loads(line))

print(f"Loaded {len(chunks)} chunks.")

def chunk_id_to_int(chunk_id: str) -> int:
    digest = hashlib.sha256(chunk_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big") & ((1 << 63) - 1)

def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

# Skip unchanged chunks and upsert chunks whose text changed at a stable ID.
existing_hashes_by_id: dict = {}
try:
    offset = None
    while True:
        scroll_result, offset = qdrant.scroll(
            collection_name=COLLECTION_NAME,
            limit=10_000,
            offset=offset,
            with_payload=["text", "text_hash"],
            with_vectors=False,
        )
        for point in scroll_result:
            payload = point.payload or {}
            stored_text_hash = payload.get("text_hash")
            if stored_text_hash is None and payload.get("text"):
                stored_text_hash = text_hash(payload["text"])
            if stored_text_hash:
                existing_hashes_by_id[point.id] = stored_text_hash
        if offset is None:
            break
    if existing_hashes_by_id:
        print(f"Existing vectors : {len(existing_hashes_by_id)}")
except Exception:
    pass

chunks_to_embed = [
    c for c in chunks
    if existing_hashes_by_id.get(chunk_id_to_int(c["id"])) != text_hash(c["text"])
]
print(f"Already current   : {len(chunks) - len(chunks_to_embed)}")
print(f"Chunks to embed    : {len(chunks_to_embed)}")

if not chunks_to_embed:
    print("Nothing to do — all chunks already in Qdrant.")
    exit(0)

# ── Embed + upsert ────────────────────────────────────────────────────────────

total  = len(chunks_to_embed)
stored = 0

for i in range(0, total, BATCH_SIZE):
    batch = chunks_to_embed[i : i + BATCH_SIZE]
    texts = [c["text"][:6000] for c in batch]

    try:
        embeddings = embed_batch(texts)
    except Exception as e:
        print(f"  ERROR embedding batch at {i}: {e}")
        time.sleep(5)
        continue

    points = [
        PointStruct(
            id=chunk_id_to_int(chunk["id"]),
            vector=embedding,
            payload={
                "chunk_id":    chunk["id"],
                "title":       chunk["title"],
                "chunk_index": chunk["chunk_index"],
                "word_count":  chunk["word_count"],
                "text_hash":   text_hash(chunk["text"]),
                "text":        chunk["text"],
            },
        )
        for chunk, embedding in zip(batch, embeddings)
    ]

    qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
    stored += len(batch)
    print(f"  [{stored}/{total}] embedded and stored")

print(f"\nDone.")
print(f"Total vectors in collection: {qdrant.count(COLLECTION_NAME).count}")

if not QDRANT_URL:
    print()
    print("To push to tcz:")
    print(f"  rsync -avz --progress qdrant_storage/ wbattles@100.73.231.117:/opt/waivatar/qdrant_storage/")
