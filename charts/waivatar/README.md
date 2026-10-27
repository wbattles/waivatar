# waivatar

Helm chart for **waivatar** — an Avatar (James Cameron) wiki RAG MCP server backed by Qdrant.

## Components

| Resource | Description |
|---|---|
| **Qdrant** | Vector database (Deployment + Service + PVC) |
| **MCP server** | RAG-powered MCP server Deployment + Service |
| **Data pipeline** | Post-install/upgrade Job that loads the baked wiki snapshot into Qdrant, then syncs against the live wiki |
| **Sync CronJob** | Optional scheduled incremental sync against the live wiki (off by default) |
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
| `image.data.tag` | `latest` | Data pipeline image tag (`latest` or a `snapshot-YYYY-MM-DD` tag) |
| `image.mcp.repository` | `ghcr.io/wbattles/waivatar-mcp` | MCP server image |
| `image.mcp.tag` | `v0.1.0` | MCP server image tag |
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
| `job.backoffLimit` | `10` | Data pipeline job retry limit |
| `job.resetCollection` | `false` | Delete and recreate the Qdrant collection before embedding |
| `job.syncOnInstall` | `true` | After loading the snapshot, sync against the live wiki |
| `sync.enabled` | `false` | Deploy a CronJob that syncs the index against the live wiki |
| `sync.schedule` | `0 4 * * 0` | CronJob schedule (weekly) |

## Notes

- The data pipeline Job runs as a `post-install,post-upgrade` Helm hook. It loads the wiki snapshot baked into the data image, then runs an incremental sync so the index matches the live wiki.
- The data image is refreshed monthly by CI. Because the Job pulls with `imagePullPolicy: Always`, every install or upgrade starts from the newest snapshot. Restarting the MCP pod does not re-run the pipeline.
- Enable `sync.enabled` if you upgrade rarely and want the index to track wiki edits between upgrades. See the comments in `values.yaml` for guidance on frequency.
- The MCP server includes readiness and liveness probes on the `/mcp` endpoint.
- To enable ingress with TLS, set `ingress.enabled=true`, `ingress.host`, and `ingress.tls.secretName`.
