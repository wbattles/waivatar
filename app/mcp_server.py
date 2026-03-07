"""
waivatar — FastMCP Server
Exposes Avatar wiki RAG as MCP tools via FastMCP.

Hosted mode: clients pass their OpenAI key via X-OpenAI-Key header.
Local/stdio mode: falls back to OPENAI_API_KEY env var.

Clients connect over streamable-http (hosted) or stdio (local).
"""

import os
import sys
from dotenv import load_dotenv
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
import fastmcp
from fastmcp.server.dependencies import get_http_request

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = "avatar_wiki"
TOP_K = 5
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "text-embedding-3-small")

# Fallback key for local/stdio use
OPENAI_API_KEY_FALLBACK = os.environ.get("OPENAI_API_KEY", "")

# ── Qdrant client ─────────────────────────────────────────────────────────────

qdrant = QdrantClient(url=QDRANT_URL)

# ── Embedding ─────────────────────────────────────────────────────────────────

def embed(text: str, api_key: str) -> list[float]:
    """Embed a query string using the provided OpenAI API key."""
    if not api_key:
        raise RuntimeError(
            "No OpenAI API key provided. "
            "Pass your key via the X-OpenAI-Key header or set OPENAI_API_KEY env var."
        )
    client = OpenAI(api_key=api_key)
    response = client.embeddings.create(model=OPENAI_MODEL, input=[text])
    return response.data[0].embedding


def get_api_key() -> str:
    """Get OpenAI key from request header, falling back to env var for stdio."""
    try:
        request = get_http_request()
        key = request.headers.get("x-openai-key", "")
        if key:
            return key
    except Exception:
        pass
    return OPENAI_API_KEY_FALLBACK


# ── MCP Server ────────────────────────────────────────────────────────────────

mcp = fastmcp.FastMCP(
    name="waivatar",
    instructions="""
    You are connected to waivatar — a knowledge base for James Cameron's Avatar universe.
    Use the available tools to search for lore, characters, locations, creatures, technology,
    and events from the Avatar films and expanded universe.
    Always search before answering Avatar-related questions.
    """,
)

# ── Tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def search_avatar_wiki(query: str, top_k: int = TOP_K) -> str:
    """
    Search the Avatar wiki for lore, characters, locations, creatures,
    technology, factions, and events. Returns the most relevant passages.

    Args:
        query:  Natural language question or topic to search for.
        top_k:  Number of results to return (default 5, max 10).
    """
    top_k = min(top_k, 10)
    api_key = get_api_key()
    vector = embed(query, api_key)

    results = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=top_k,
        with_payload=True,
    ).points

    if not results:
        return "No results found for that query."

    output = []
    for i, hit in enumerate(results, 1):
        payload = hit.payload
        score = round(hit.score, 3)
        output.append(
            f"[{i}] {payload['title']} (relevance: {score})\n{payload['text']}"
        )

    return "\n\n---\n\n".join(output)


@mcp.tool()
def get_article(title: str) -> str:
    """
    Retrieve all stored chunks for a specific Avatar wiki article by exact title.
    Useful when you know the exact name of a character, location, or concept.

    Args:
        title: Exact article title (e.g. "Jake Sully", "Pandora", "AMP Suit").
    """
    results, _ = qdrant.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(
            must=[FieldCondition(key="title", match=MatchValue(value=title))]
        ),
        limit=20,
        with_payload=True,
        with_vectors=False,
    )

    if not results:
        return f"No article found with title '{title}'. Try search_avatar_wiki() instead."

    chunks = sorted(results, key=lambda p: p.payload.get("chunk_index", 0))
    full_text = "\n\n".join(c.payload["text"] for c in chunks)

    return f"# {title}\n\n{full_text}"


@mcp.tool()
def list_articles(prefix: str = "", limit: int = 50) -> str:
    """
    List article titles in the Avatar wiki, optionally filtered by a prefix.
    Useful for discovery when you're not sure of an exact title.

    Args:
        prefix: Optional title prefix to filter by (e.g. "AMP" returns all AMP variants).
        limit:  Max number of titles to return (default 50).
    """
    all_titles: set[str] = set()
    offset = None

    while len(all_titles) < limit:
        results, offset = qdrant.scroll(
            collection_name=COLLECTION_NAME,
            limit=256,
            offset=offset,
            with_payload=["title"],
            with_vectors=False,
        )
        for point in results:
            title = point.payload.get("title", "")
            if not prefix or title.lower().startswith(prefix.lower()):
                all_titles.add(title)
        if offset is None:
            break

    sorted_titles = sorted(all_titles)[:limit]

    if not sorted_titles:
        return f"No articles found with prefix '{prefix}'."

    return f"Found {len(sorted_titles)} articles:\n" + "\n".join(f"- {t}" for t in sorted_titles)


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    transport = sys.argv[1] if len(sys.argv) > 1 else "streamable-http"

    print(f"waivatar starting — transport={transport}")

    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(
            transport="streamable-http",
            host="0.0.0.0",
            port=int(os.environ.get("MCP_PORT", 8080)),
        )
