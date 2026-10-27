"""
waivatar — snapshot file helpers
The snapshot is a gzipped JSONL of chunks committed to the repo and baked
into the data image. It is only a bootstrap: sync_wiki.py converges a
deployment on the live wiki regardless of snapshot age.
"""

import gzip
import json
import os
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
CHUNKS_FILE = Path(os.environ.get("CHUNKS_FILE", DATA_DIR / "avatar_chunks.jsonl.gz"))
SNAPSHOT_FILE = DATA_DIR / "SNAPSHOT"


def _open(path: Path, mode: str):
    if str(path).endswith(".gz"):
        if "w" in mode:
            # mtime=0 and an empty embedded filename keep the archive
            # byte-identical when the content is unchanged, so CI can diff it
            # to decide whether a refresh actually changed anything.
            return gzip.GzipFile(filename="", mode="wb", fileobj=open(path, "wb"), mtime=0)
        return gzip.open(path, mode)
    return open(path, mode)


def write_chunks(chunks: list[dict], path: Path = CHUNKS_FILE) -> None:
    with _open(path, "wb") as f:
        for chunk in chunks:
            f.write((json.dumps(chunk, ensure_ascii=False) + "\n").encode("utf-8"))


def read_chunks(path: Path = CHUNKS_FILE) -> list[dict]:
    chunks = []
    with _open(path, "rb") as f:
        for line in f:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return chunks


def write_snapshot_meta(meta: dict, path: Path = SNAPSHOT_FILE) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, sort_keys=True)
        f.write("\n")
