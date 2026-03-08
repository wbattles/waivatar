# waivatar

Helm chart for **waivatar** — an Avatar: The Last Airbender wiki RAG MCP server backed by Qdrant.

## Components

| Resource | Description |
|---|---|
| **Qdrant** | Vector database (Deployment + Service + PVC) |
| **MCP server** | RAG-powered MCP server Deployment + Service |
| **Data pipeline** | Post-install Job that ingests and embeds wiki data into Qdrant |
| **Ingress** | Optional ingress for the MCP server |

## Prerequisites

- Kubernetes 1.24+
- Helm 3
- An OpenAI API key (for embeddings)
- Container images pushed to a registry:
  - `ghcr.io/wbattles/waivatar-data` — data pipeline image
  - `ghcr.io/wbattles/waivatar-mcp` — MCP server image

## Install

```bash
helm install waivatar charts/waivatar \
  --set secrets.openaiApiKey="YOUR_OPENAI_KEY"
```

Or via OCI registry:

```bash
helm install waivatar oci://ghcr.io/wbattles/waivatar --version 0.1.0 \
  --set secrets.openaiApiKey="YOUR_OPENAI_KEY"
```

## Values

| Key | Default | Description |
|---|---|---|
| `image.data.repository` | `ghcr.io/wbattles/waivatar-data` | Data pipeline image |
| `image.data.tag` | `latest` | Data pipeline image tag |
| `image.mcp.repository` | `ghcr.io/wbattles/waivatar-mcp` | MCP server image |
| `image.mcp.tag` | `latest` | MCP server image tag |
| `qdrant.enabled` | `true` | Deploy Qdrant |
| `qdrant.port` | `6333` | Qdrant service port |
| `qdrant.persistence.enabled` | `true` | Enable persistent storage for Qdrant |
| `qdrant.persistence.size` | `5Gi` | PVC size |
| `mcp.replicas` | `1` | MCP server replicas |
| `mcp.port` | `8080` | MCP server port |
| `mcp.openai.model` | `text-embedding-3-small` | OpenAI embedding model |
| `ingress.enabled` | `false` | Enable ingress |
| `ingress.host` | `mcp.example.com` | Ingress hostname |
| `secrets.openaiApiKey` | `""` | OpenAI API key |
| `secrets.qdrantApiKey` | `""` | Qdrant API key (optional) |
| `job.backoffLimit` | `4` | Data pipeline job retry limit |

## Notes

- The data pipeline Job runs as a `post-install` Helm hook. It ingests and embeds Avatar wiki content into Qdrant automatically on first install.
- The MCP server includes readiness and liveness probes on the `/mcp` endpoint.
- To enable ingress with TLS, set `ingress.enabled=true`, `ingress.host`, and `ingress.tls.secretName`.
