# Ingest Omi memories into Pinecone vector database

Use this recipe to format Omi memories into Pinecone vector upsert JSON payloads. This facilitates ingesting your personal knowledge base into Pinecone serverless or pod-based indexes for semantic search and cloud RAG pipelines.

## Prerequisites

- Python 3.10+ (standard library only)
- An authenticated `omi-cli` installation
- Optional: Pinecone API key and index host

## Usage

Generate a Pinecone upsert payload directly from the CLI:

```sh
omi --json memory list --limit 100 | python memories_to_pinecone.py - --namespace omi-memories -o pinecone_batch.json
```

Or convert a local export:

```sh
python memories_to_pinecone.py memories.json --namespace user-knowledge -o pinecone_batch.json
```

Output:
```
Generated Pinecone upsert payload with 42 vectors at pinecone_batch.json
```

## Upserting via Pinecone REST API or Python SDK

Using Python with the official `pinecone` client:

```python
import json
from pinecone import Pinecone

pc = Pinecone(api_key="YOUR_PINECONE_API_KEY")
index = pc.Index("my-omi-index")

data = json.loads(open("pinecone_batch.json").read())
# Add embeddings to vector objects prior to upsert, or use integrated inference models:
index.upsert(vectors=data["vectors"], namespace=data.get("namespace"))
print("Upserted memories to Pinecone!")
```

## Features

- **Standard Pinecone Schema**: Emits standard `vectors` array with `id` and `metadata`.
- **Namespace Support**: Isolates memories into dedicated namespaces (`--namespace`).
- **Metadata Filtering**: Preserves categories, timestamps, and manual tags for server-side metadata filtering (e.g. `$eq: {"category": "work"}`).
- **Pure Standard Library**: Zero external dependencies required.
