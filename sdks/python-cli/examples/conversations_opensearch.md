# Export conversations to OpenSearch / Elasticsearch

Use this recipe to export Omi conversations into the standard newline-delimited JSON
(`_bulk` ndjson) format for high-throughput batch indexing into
[OpenSearch](https://opensearch.org/) or [Elasticsearch](https://www.elastic.co/).

It structures titles, overviews, categories, action items, speaker labels, and
full transcripts for full-text search, BM25 keyword matching, and dashboard analytics.

The companion script [`conversations_to_opensearch.py`](conversations_to_opensearch.py)
runs on Python 3.10+ using only standard library modules (`argparse`, `json`, `sys`, `pathlib`).

## 1. Export conversations from Omi

Export conversations from your device:

```sh
omi --json conversation list --limit 100 > conversations.json
```

Or pipe directly from `omi-cli`:

```sh
omi --json conversation list --limit 100 | python conversations_to_opensearch.py - -o bulk.ndjson
```

## 2. Convert to OpenSearch bulk ndjson

Run the converter script:

```sh
python conversations_to_opensearch.py conversations.json -o bulk.ndjson
```

### Custom target index name

By default, the action headers target the `omi_conversations` index. To index into a custom or date-stamped index:

```sh
python conversations_to_opensearch.py conversations.json -o bulk.ndjson --index-name omi_logs_2026
```

### Combining multiple exports

Merge multiple export files with automatic deduplication by conversation ID:

```sh
python conversations_to_opensearch.py day1.json day2.json -o bulk.ndjson --force
```

## 3. Ingest into OpenSearch

Ingest the generated `bulk.ndjson` file using `curl`:

```sh
curl -X POST "http://localhost:9200/_bulk" \
  -H "Content-Type: application/x-ndjson" \
  --data-binary @bulk.ndjson
```

Or using the official `opensearch-py` client:

```python
from opensearchpy import OpenSearch

client = OpenSearch(hosts=[{"host": "localhost", "port": 9200}])

with open("bulk.ndjson", "r", encoding="utf-8") as f:
    bulk_data = f.read()

response = client.bulk(body=bulk_data)
print(f"Indexed items: {len(response.get('items', []))}")
```

## Converter options

| Option | Description | Default |
| :--- | :--- | :--- |
| `INPUT ...` | One or more JSON files, or `-` for stdin | *(required)* |
| `-o`, `--output` | Destination `.ndjson` file | *(required)* |
| `--index-name` | OpenSearch target index name | `omi_conversations` |
| `-f`, `--force` | Overwrite destination file if it exists | `False` |

## Verification

Run the automated test suite:

```sh
python sdks/python-cli/tests/test_conversations_to_opensearch.py
```
