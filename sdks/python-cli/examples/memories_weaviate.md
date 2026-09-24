# Import Omi memories into Weaviate vector database

Use this recipe to export Omi memories, facts, and learnings into [Weaviate](https://weaviate.io/),
an open-source vector database. It reads JSON exports from `omi-cli`, makes no
network calls during conversion, and produces a batch payload matching Weaviate's
official REST Batch API (`POST /v1/batch/objects`).

The companion script [`memories_to_weaviate.py`](memories_to_weaviate.py) runs on Python
3.10+ using only standard library modules (`json`, `uuid`, `argparse`).

## 1. Export memories from Omi

Export memories using the JSON output format:

```sh
omi --json memory list --limit 200 > memories.json
```

For large memory collections across multiple pages, paginate with `--offset`:

```sh
omi --json memory list --limit 200 --offset 0 > page1.json
omi --json memory list --limit 200 --offset 200 > page2.json
```

## 2. Convert to Weaviate batch format

Run the converter to merge and format into Weaviate batch objects:

```sh
python memories_to_weaviate.py memories.json -o weaviate_batch.json
```

Or pipe directly from `omi-cli`:

```sh
omi --json memory list --limit 200 | python memories_to_weaviate.py - -o weaviate_batch.json
```

### Merging multiple pages

To merge multiple paginated exports with automatic deduplication by memory ID:

```sh
python memories_to_weaviate.py page1.json page2.json -o weaviate_batch.json
```

## 3. Ingest into Weaviate

Submit the generated batch payload to your local Weaviate instance or Weaviate Cloud (WCD):

```sh
# Local Weaviate instance
curl -X POST -H "Content-Type: application/json" \
     -d @weaviate_batch.json \
     http://localhost:8080/v1/batch/objects

# Weaviate Cloud with API key
curl -X POST -H "Content-Type: application/json" \
     -H "Authorization: Bearer $WEAVIATE_API_KEY" \
     -d @weaviate_batch.json \
     https://your-cluster-url.weaviate.network/v1/batch/objects
```

## Converter options

| Option | Description | Default |
| :--- | :--- | :--- |
| `inputs` | One or more JSON files, or `-` for stdin | `-` |
| `-o`, `--output` | Destination output file path | stdout |
| `-c`, `--collection` | Weaviate class/collection name | `OmiMemory` |
| `-f`, `--force` | Overwrite existing output file | `false` |
| `--category` | Filter memories by category (case-insensitive) | all |
| `--min-date` | Filter memories created on or after ISO timestamp | all |
| `--indent` | Number of spaces for JSON indentation (0 for compact) | `2` |

## Payload structure & vectorization

Each object in the generated payload follows the Weaviate REST batch specification:

```json
{
  "objects": [
    {
      "class": "OmiMemory",
      "id": "e4eaaaf2-d142-51a4-9226-490367253597",
      "properties": {
        "content": "Prefers asynchronous standup notes over morning calls",
        "category": "work",
        "created_at": "2026-09-24T12:00:00Z",
        "memory_id": "mem_001",
        "tags": ["remote", "communication"]
      }
    }
  ]
}
```

* **Deterministic UUIDs**: Weaviate requires valid RFC 4122 UUIDs for object IDs. Non-UUID IDs are deterministically mapped to UUIDv5 so subsequent imports update rather than duplicate records.
* **Automatic Vectorization**: By omitting the raw `vector` array, Weaviate's configured vectorizer module (such as `text2vec-openai`, `text2vec-transformers`, or `text2vec-ollama`) computes embeddings automatically upon ingestion.
