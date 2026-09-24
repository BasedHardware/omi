# Import Omi conversations into Meilisearch search engine

Use this recipe to index Omi conversations, meeting notes, transcripts, and speaker
dialogues into [Meilisearch](https://www.meilisearch.com/), a lightning-fast,
typo-tolerant search engine. It reads JSON exports from `omi-cli`, makes no
network requests during conversion, and formats data into a clean document batch
ready for Meilisearch's document addition endpoint (`POST /indexes/{index_uid}/documents`).

The companion script [`conversations_to_meilisearch.py`](conversations_to_meilisearch.py)
runs on Python 3.10+ using only standard library modules (`json`, `re`, `argparse`).

## 1. Export conversations from Omi

Export conversations using the JSON output format:

```sh
omi --json conversation list --limit 200 > conversations.json
```

For large histories across multiple pages, paginate with `--offset`:

```sh
omi --json conversation list --limit 200 --offset 0 > page1.json
omi --json conversation list --limit 200 --offset 200 > page2.json
```

## 2. Convert to Meilisearch documents

Run the converter to merge and structure conversations:

```sh
python conversations_to_meilisearch.py conversations.json -o meili_docs.json
```

Or pipe directly from `omi-cli`:

```sh
omi --json conversation list --limit 200 | python conversations_to_meilisearch.py - -o meili_docs.json
```

### Merging multiple pages

To merge multiple paginated exports with automatic deduplication by conversation ID:

```sh
python conversations_to_meilisearch.py page1.json page2.json -o meili_docs.json
```

## 3. Ingest into Meilisearch

Send the formatted documents to your Meilisearch instance:

```sh
# Local Meilisearch instance
curl -X POST -H "Content-Type: application/json" \
     -H "Authorization: Bearer $MEILI_MASTER_KEY" \
     -d @meili_docs.json \
     http://localhost:7700/indexes/omi_conversations/documents

# Search queries via curl
curl -X POST -H "Content-Type: application/json" \
     -H "Authorization: Bearer $MEILI_MASTER_KEY" \
     -d '{"q": "project roadmap sprint"}' \
     http://localhost:7700/indexes/omi_conversations/search
```

## Converter options

| Option | Description | Default |
| :--- | :--- | :--- |
| `inputs` | One or more JSON files, or `-` for stdin | `-` |
| `-o`, `--output` | Destination output file path | stdout |
| `-f`, `--force` | Overwrite existing output file | `false` |
| `--category` | Filter conversations by category | all |
| `--min-date` | Filter conversations created on or after ISO timestamp | all |
| `--min-duration` | Filter conversations by minimum duration in seconds | all |
| `--indent` | Number of spaces for JSON indentation (0 for compact) | `2` |

## Document schema & primary key

Each record in the exported array satisfies Meilisearch's document guidelines:

```json
[
  {
    "id": "conv_12345",
    "title": "Sprint Planning Meeting",
    "category": "work",
    "duration_seconds": 1800,
    "created_at": "2026-09-24T10:00:00Z",
    "summary": "Discussed roadmap and assigned milestones.",
    "speakers": ["Alice", "Bob"],
    "transcript": "Alice: Welcome everyone.\nBob: Ready."
  }
]
```

* **Primary Key Sanitization**: Meilisearch requires primary keys to match `^[a-zA-Z0-9_-]+$`. Unsupported characters are converted to hyphens and consecutive delimiters are collapsed.
* **Transcript Aggregation**: Flattens nested transcript turns into searchable text with speaker attribution.
