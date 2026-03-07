#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "Starting Qdrant..."
docker run -d \
  --name qdrant \
  -p 6333:6333 \
  -v "$(pwd)/qdrant_storage:/qdrant/storage" \
  qdrant/qdrant:latest 2>/dev/null || docker start qdrant

echo "Starting waivatar MCP server on :8080..."
python data/ingest_wiki.py
EMBEDDING_PROVIDER=openai OPENAI_API_KEY=${OPENAI_API_KEY} QDRANT_URL=http://localhost:6333 python data/embed_data.py
EMBEDDING_PROVIDER=openai OPENAI_API_KEY=${OPENAI_API_KEY} QDRANT_URL=http://localhost:6333 python app/mcp_server.py streamable-http

# Build and install waivatar locally for Claude Desktop
echo "Packing .mcpb..."
mcpb pack

echo "Done! Install waivatar.mcpb via Claude Desktop → Settings → Extensions → Install Extension"
