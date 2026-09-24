# Import Omi memories into Milvus / Zilliz vector database

Use this recipe to import Omi memories, facts, and learnings into [Milvus](https://milvus.io/)
or [Zilliz Cloud](https://zilliz.com/), an open-source enterprise vector database.
It reads JSON exports from `omi-cli`, makes no network requests during conversion,
and produces a batch payload matching the official Milvus REST v2 API specification
(`POST /v2/vectordb/entities/upsert`).

The companion script [`memories_to_milvus.py`](memories_to_milvus.py) runs on Python
3.10+ using only standard library modules (`json`, `argparse`, `datetime`).

## 1. Export memories from Omi

Export memories in JSON format:

```sh
omi --json memory list --limit 200 > memories.json
```

For large collections across multiple pages, paginate with `--offset`:

```sh
omi --json memory list --limit 200 --offset 0 > page1.json
omi --json memory list --limit 200 --offset 200 > page2.json
```

## 2. Convert to Milvus entity batch

Run the converter to merge and format into a Milvus entity batch:

```sh
python memories_to_milvus.py memories.json -o milvus_batch.json
```

Or pipe directly from `omi-cli`:

```sh
omi --json memory list --limit 200 | python memories_to_milvus.py - -o milvus_batch.json
```

### Merging multiple pages

To merge multiple paginated exports with automatic deduplication by memory ID:

```sh
python memories_to_milvus.py page1.json page2.json -o milvus_batch.json
```

## 3. Ingest into Milvus

Send the batch to your Milvus standalone instance or Zilliz Cloud endpoint:

```sh
# Local Milvus standalone / Docker
curl -X POST -H "Content-Type: application/json" \
     -H "Authorization: Bearer $MILVUS_TOKEN" \
     -d @milvus_batch.json \
     http://localhost:19530/v2/vectordb/entities/upsert

# Zilliz Cloud
curl -X POST -H "Content-Type: application/json" \
     -H "Authorization: Bearer $ZILLIZ_API_KEY" \
     -d @milvus_batch.json \
     https://your-cluster-endpoint.zillizcloud.com/v2/vectordb/entities/upsert
```

## Converter options

| Option | Description | Default |
| :--- | :--- | :--- |
| `inputs` | One or more JSON files, or `-` for stdin | `-` |
| `-o`, `--output` | Destination output file path | stdout |
| `-c`, `--collection` | Target Milvus collection name | `omi_memories` |
| `-f`, `--force` | Overwrite existing output file | `false` |
| `--category` | Filter memories by category (case-insensitive) | all |
| `--min-date` | Filter memories created on or after ISO timestamp | all |
| `--indent` | Number of spaces for JSON indentation (0 for compact) | `2` |

## Payload schema

The output JSON adheres to Milvus v2 REST entity definitions:

```json
{
  "collectionName": "omi_memories",
  "data": [
    {
      "id": "mem_001",
      "text": "User prefers asynchronous standup notes",
      "category": "work",
      "created_at": "2026-09-24T12:00:00Z",
      "tags": ["remote", "work"],
      "manually_added": false
    }
  ]
}
```

* **Deduplication**: Re-running exports merges records idempotently by ID.
* **Auto-Vectorization Compatibility**: Compatible with Milvus and Zilliz Cloud text-embedding model integrations.
