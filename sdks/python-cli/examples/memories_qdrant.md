# Export memories to Qdrant vector database (payload-first format)

Use this recipe to export Omi memories into structured point records (with deterministic
UUIDs, normalized text, categories, tags, and timestamps) ready for payload indexing,
metadata filtering, and vector enrichment in the [Qdrant](https://qdrant.tech/) vector
search engine.

The companion script [`memories_to_qdrant.py`](memories_to_qdrant.py) runs on Python
3.10+ using only standard library modules (`argparse`, `json`, `uuid`, `pathlib`). It
delivers an offline, dependency-free payload converter suitable for piping into your
embedding generation pipeline or Qdrant collection.

## 1. Export memories from Omi

Export memories from your device or account:

```sh
omi --json memory list --limit 100 > memories.json
```

Or pipe directly from `omi-cli`:

```sh
omi --json memory list --limit 100 | python memories_to_qdrant.py - -o points.json
```

## 2. Convert to Qdrant points payload

Run the converter script (by default, produces payload-first point records with `id` and `payload`):

```sh
python memories_to_qdrant.py memories.json -o points.json
```

### Schema validation with placeholder vectors

If testing collection creation, schema verification, or upsert plumbing before wiring
external embedding models, specify `--vector-dim` (e.g. 384, 768, 1536) to generate
placeholder zero-vectors matching your collection dimension:

```sh
python memories_to_qdrant.py memories.json -o points.json --vector-dim 384
```

> **Note**: Placeholder vectors contain zero-valued floats for schema and transport testing.
> For semantic search and RAG similarity retrieval, attach real vector embeddings as shown in Step 3.

### Deduplication across multiple exports

Combine multiple export files into a single batch without duplicate memory IDs:

```sh
python memories_to_qdrant.py day1.json day2.json -o points.json --force
```

## 3. Ingest into Qdrant

### Option A: Enrich with embeddings and upsert (Recommended for Semantic Search / RAG)

Qdrant's `/collections/{collection_name}/points` API requires a vector for every point.
You can compute embeddings using `fastembed` (Qdrant's recommended lightweight library)
or any embedding model before upserting:

```python
import json
from qdrant_client import QdrantClient
from fastembed import TextEmbedding

client = QdrantClient(url="http://localhost:6333")
model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

with open("points.json", encoding="utf-8") as f:
    points = json.load(f)["points"]

# Compute embeddings from memory content
texts = [p["payload"]["content"] for p in points]
embeddings = list(model.embed(texts))
for point, emb in zip(points, embeddings):
    point["vector"] = emb.tolist()

client.upsert(
    collection_name="omi_memories",
    points=points,
)
print(f"Successfully upserted {len(points)} memories with embeddings into Qdrant.")
```

### Option B: Upsert test points via REST API (with `--vector-dim`)

If points were exported with `--vector-dim` for plumbing validation, upsert them directly via curl:

```sh
curl -X PUT "http://localhost:6333/collections/omi_memories/points" \
  -H "Content-Type: application/json" \
  -d @points.json
```

## Converter options

| Option | Description | Default |
| :--- | :--- | :--- |
| `INPUT ...` | One or more JSON files, or `-` for stdin | *(required)* |
| `-o`, `--output` | Destination JSON file | *(required)* |
| `--vector-dim` | Placeholder vector dimension for schema testing (e.g. 384, 768) | `None` |
| `-f`, `--force` | Overwrite destination file if it exists | `False` |

## Verification

Run the automated test suite:

```sh
python sdks/python-cli/tests/test_memories_to_qdrant.py
```
