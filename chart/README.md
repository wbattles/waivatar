Helm chart: ragmcp

This chart deploys a Qdrant instance and two Kubernetes Jobs:
- ingest: run your ingest pipeline (e.g., `ingest_wiki.py`)
- embed: run your embedding pipeline (e.g., `embed_data.py`)

Prerequisites
- Build container images for the ingest and embed workers and push them to a registry. Set their locations in `values.yaml` under `image.ingest` and `image.embed`.

Install

1. (Optional) provide a Qdrant API key via values or Helm `--set`:

   helm install ragmcp charts/ragmcp --set env.qdrant_api_key="YOUR_API_KEY" \
     --set image.ingest.repository=registry/ingest --set image.embed.repository=registry/embed

2. To run the jobs once, you can `helm template` and `kubectl apply -f -`, or install the chart and then `kubectl create job` from templates. The Job objects created by the chart will run once (OnFailure restart).

Notes
- This chart expects your ingest/embed images to include the code and entrypoints to run the pipelines (e.g., entrypoint executes `python ingest_wiki.py`).
- For production, enable persistence for Qdrant and tune resources in `values.yaml`.
