#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "Starting Qdrant..."
docker run -d \
  --name qdrant \
  -p 6333:6333 \
  -v "$(pwd)/qdrant_storage:/qdrant/storage" \
  qdrant/qdrant:latest 2>/dev/null || docker start qdrant

# Uncomment to load data into the local Qdrant:
# OPENAI_API_KEY=${OPENAI_API_KEY} QDRANT_URL=http://localhost:6333 python data/embed_data.py   # load committed snapshot
# OPENAI_API_KEY=${OPENAI_API_KEY} QDRANT_URL=http://localhost:6333 python data/sync_wiki.py    # sync with live wiki
# Regenerate the snapshot itself (committed to the repo, refreshed monthly by CI):
# python data/ingest_wiki.py
# Full rebuild:
# RESET_COLLECTION=true OPENAI_API_KEY=${OPENAI_API_KEY} QDRANT_URL=http://localhost:6333 python data/embed_data.py

echo "Packing .mcpb..."
mcpb pack

echo "Done! Install waivatar.mcpb via Claude Desktop → Settings → Extensions → Install Extension"
echo "Claude Desktop will launch the MCP server automatically over stdio."
