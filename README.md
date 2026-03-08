## Waivatar

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

To re-ingest and re-embed the wiki data, uncomment the relevant lines in `local.sh` before running.

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

The chart deploys Qdrant, runs a data pipeline job (wiki ingest + embed), and starts the MCP server. See [charts/waivatar/values.yaml](./charts/waivatar/values.yaml) for all configurable values.

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

## License

This project is licensed under the MIT License – see the [LICENSE](./LICENSE) file for details.
