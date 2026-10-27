## Waivatar

[![Casino funds](https://img.shields.io/badge/Casino_funds-Ko--fi-ff5f5f?logo=ko-fi&logoColor=white)](https://ko-fi.com/wbattles)

Avatar universe knowledge base exposed as an MCP server. Search lore, characters, locations, creatures, and technology from James Cameron's Avatar films via RAG over the Avatar fandom wiki.

## Tools

| Tool | Description |
|------|-------------|
| `search_avatar_wiki` | Semantic search across all wiki articles. Returns the most relevant passages for a natural language query. |
| `get_article` | Retrieve the full text of a specific wiki article by exact title (e.g. "Jake Sully", "Pandora"). |
| `list_articles` | Browse article titles, optionally filtered by a prefix. Useful for discovery. |

## Quickstart

### Hosted (Streamable HTTP)

A public instance is live at **waivatar.waisuite.com**. Connect any MCP client to it:

```
https://waivatar.waisuite.com/mcp
```

### Local (stdio)

Run the local setup script:

```bash
OPENAI_API_KEY=sk-... ./local.sh
```

This will:
1. Start a local Qdrant instance via Docker (or reuse an existing one)
2. Pack the MCP server into a `waivatar.mcpb` extension file

To load the wiki data into your local Qdrant, uncomment the relevant lines in `local.sh` before running. See [Refreshing Data](#refreshing-data).

### Claude Desktop

In Claude Desktop, go to **Settings → Extensions → Install Extension** and select the generated `waivatar.mcpb` file.

Claude Desktop will launch the MCP server automatically over stdio.

Or connect to the hosted instance over streamable HTTP:

```json
{
  "mcpServers": {
    "waivatar": {
      "type": "streamable-http",
      "url": "https://your-waivatar-host/mcp"
    }
  }
}
```

## Deploy with Helm

```bash
helm install waivatar charts/waivatar \
  --set secrets.openaiApiKey=sk-...
```

The chart deploys Qdrant, runs a data pipeline job (loads the baked wiki snapshot, then syncs against the live wiki), and starts the MCP server. See [charts/waivatar/values.yaml](./charts/waivatar/values.yaml) for all configurable values.

To expose the server externally:

```bash
helm install waivatar charts/waivatar \
  --set secrets.openaiApiKey=sk-... \
  --set ingress.enabled=true \
  --set ingress.host=mcp.example.com
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | **Required.** OpenAI API key for embeddings. |
| `OPENAI_MODEL` | `text-embedding-3-small` | Embedding model to use. |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant instance URL. |
| `MCP_PORT` | `8080` | Port for streamable HTTP transport. |
| `RESET_COLLECTION` | `false` | When running `data/embed_data.py`, delete and recreate the Qdrant collection before embedding. |
| `CHUNKS_FILE` | `data/avatar_chunks.jsonl.gz` | Snapshot file read by `data/embed_data.py` and written by `data/ingest_wiki.py`. |

## Data

Wiki content is pulled from the [Avatar fandom wiki](https://james-camerons-avatar.fandom.com) via the MediaWiki API. The repo carries no dependency on external storage: a gzipped snapshot of the chunked articles lives at `data/avatar_chunks.jsonl.gz` and is baked into the data image.

There are three scripts in `data/`:

| Script | What it does |
|--------|--------------|
| `ingest_wiki.py` | Full crawl of the wiki. Writes `data/avatar_chunks.jsonl.gz` and `data/SNAPSHOT`. Takes about a minute. |
| `embed_data.py` | Loads the snapshot into Qdrant. Embeds only new or changed chunks and never moves a page backwards if a sync already has a newer revision. |
| `sync_wiki.py` | Incremental sync. Compares every page's latest revision ID with what Qdrant holds, refetches only changed pages, re-embeds only changed chunks, and removes deleted pages. Works regardless of how old the snapshot was. |

### Refreshing Data

**Snapshot (monthly, automatic).** The `waivatar data refresh` workflow runs on the first of each month, re-ingests the wiki, commits the new snapshot if it changed, and publishes a data image tagged `snapshot-YYYY-MM-DD` and `latest`. Run it from the Actions tab to refresh sooner.

**Deployed index.** The Helm pipeline Job loads the snapshot and then runs `sync_wiki.py` on every install and upgrade. To keep the index tracking the wiki between upgrades, enable the sync CronJob with `--set sync.enabled=true`. See the comments in `charts/waivatar/values.yaml` for guidance on frequency.

**Locally.**

```bash
QDRANT_URL=http://localhost:6333 python data/embed_data.py   # load the committed snapshot
QDRANT_URL=http://localhost:6333 python data/sync_wiki.py    # bring it up to date with the wiki
python data/ingest_wiki.py                                   # regenerate the snapshot itself
```

For a full rebuild that discards everything in the collection first, run the embed step with `RESET_COLLECTION=true`.

## License

This project is licensed under the MIT License – see the [LICENSE](./LICENSE) file for details.
