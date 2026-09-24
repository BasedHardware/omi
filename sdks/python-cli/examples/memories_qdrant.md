# Export memories to Qdrant vector database

Use this recipe to export Omi memories into a structured points payload ready for
batch ingestion into the [Qdrant](https://qdrant.tech/) vector search engine. It
enables fast semantic retrieval, payload filtering on memory categories/tags, and
integration with custom RAG pipelines.

The companion script [`memories_to_qdrant.py`](memories_to_qdrant.py) runs on Python
3.10+ using only standard library modules (`argparse`, `json`, `uuid`, `pathlib`).

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

Run the converter script:

```sh
python memories_to_qdrant.py memories.json -o points.json
```

### With vector dimension placeholder

If initializing a new Qdrant collection or testing schemas, specify `--vector-dim` to populate
placeholder embedding vectors (e.g. 768 or 1536 dimensions):

```sh
python memories_to_qdrant.py memories.json -o points.json --vector-dim 768
```

### Deduplication across multiple exports

Combine multiple export files into a single batch without duplicate memory IDs:

```sh
python memories_to_qdrant.py day1.json day2.json -o points.json --force
```

## 3. Ingest into Qdrant

Upsert points directly via Qdrant's REST API:

```sh
curl -X PUT "http://localhost:6333/collections/omi_memories/points" \
  -H "Content-Type: application/json" \
  -d @points.json
```

Or using the official `qdrant-client` in Python:

```python
import json
from qdrant_client import QdrantClient

client = QdrantClient(url="http://localhost:6333")

with open("points.json", encoding="utf-8") as f:
    data = json.load(f)

client.upsert(
    collection_name="omi_memories",
    points=data["points"],
)
```

## Converter options

| Option | Description | Default |
| :--- | :--- | :--- |
| `INPUT ...` | One or more JSON files, or `-` for stdin | *(required)* |
| `-o`, `--output` | Destination JSON file | *(required)* |
| `--vector-dim` | Dimension for placeholder vector embeddings (e.g. 768, 1536) | `None` |
| `-f`, `--force` | Overwrite destination file if it exists | `False` |

## Verification

Run the automated test suite:

```sh
python sdks/python-cli/tests/test_memories_to_qdrant.py
```
