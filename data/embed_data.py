"""
waivatar — Embed & Store Script
Reads avatar_chunks.jsonl, embeds chunks using the configured provider,
and stores vectors in Qdrant. Run locally then rsync qdrant_storage/ to tcz,
or set QDRANT_URL to target a running instance directly.
"""

import json
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
    return abs(hash(chunk_id)) % (2**63)

# Skip already-stored chunks (safe to re-run)
existing_ids: set = set()
try:
    scroll_result, _ = qdrant.scroll(
        collection_name=COLLECTION_NAME,
        limit=100_000,
        with_payload=False,
        with_vectors=False,
    )
    existing_ids = {p.id for p in scroll_result}
    if existing_ids:
        print(f"Already stored: {len(existing_ids)} — skipping those.")
except Exception:
    pass

chunks_to_embed = [c for c in chunks if chunk_id_to_int(c["id"]) not in existing_ids]
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
