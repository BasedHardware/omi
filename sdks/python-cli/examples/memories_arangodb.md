# Ingest and query memories with ArangoDB (native multi-model database)

Use this recipe to export Omi memories into an [ArangoDB](https://www.arangodb.com/) AQL ingestion script for graph traversals, document storage, and full-text search.

ArangoDB is a native multi-model database that unifies graph, document, and search queries in a single core engine using AQL (ArangoDB Query Language). This recipe generates idempotent `UPSERT` statements that seamlessly handle nested metadata, tags arrays, and timestamps.

The companion script [`memories_to_arangodb.py`](memories_to_arangodb.py) runs on Python 3.10+ using only standard library modules (`argparse`, `json`, `sys`, `pathlib`).

## 1. Export memories from Omi

Export memories from your device or account:

```sh
omi --json memory list --limit 100 > memories.json
```

Or pipe directly from `omi-cli`:

```sh
omi --json memory list --limit 100 | python memories_to_arangodb.py - -o memories.aql
```

## 2. Convert to ArangoDB AQL script

Run the converter script:

```sh
python memories_to_arangodb.py memories.json -o memories.aql
```

### Custom collection name

Specify a custom collection name if you are maintaining multiple datasets:

```sh
python memories_to_arangodb.py memories.json -o memories.aql --collection omi_memories
```

### Combining multiple exports

Merge multiple export files into one script with deduplication by memory ID:

```sh
python memories_to_arangodb.py day1.json day2.json -o memories.aql --force
```

## 3. Load and query in ArangoDB

### Start a local ArangoDB instance

Run ArangoDB with Docker:

```sh
docker run -d --name arangodb -p 8529:8529 -e ARANGO_NO_AUTH=1 arangodb/arangodb:latest
```

### Execute the script via ArangoShell (`arangosh`)

```sh
arangosh --server.endpoint tcp://127.0.0.1:8529 --javascript.execute-string "
const fs = require('fs');
const aql = fs.read('memories.aql');
db._query(aql);
"
```

Or execute queries directly in the ArangoDB Web Interface (Query editor).

### Analytical AQL queries

#### 1. Most frequent tags (unnested aggregation):

```aql
FOR m IN memories
  FOR t IN m.tags
    COLLECT tag = t WITH COUNT INTO total
    SORT total DESC
    LIMIT 10
    RETURN { tag, total }
```

#### 2. Count memories by category:

```aql
FOR m IN memories
  COLLECT category = m.category WITH COUNT INTO count
  SORT count DESC
  RETURN { category, count }
```

#### 3. Search memories by content substring:

```aql
FOR m IN memories
  FILTER CONTAINS(LOWER(m.content), 'meeting')
  SORT m.created_at DESC
  RETURN m
```

## Converter options

| Option | Description | Default |
| :--- | :--- | :--- |
| `INPUT ...` | One or more JSON files, or `-` for stdin | *(required)* |
| `-o`, `--output` | Destination `.aql` file | *(required)* |
| `--collection` | Target ArangoDB collection name | `memories` |
| `-f`, `--force` | Overwrite destination file if it exists | `False` |

## Verification

Run the automated test suite:

```sh
python sdks/python-cli/tests/test_memories_to_arangodb.py
```
