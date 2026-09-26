# Ingest and query memories with SurrealDB (multi-model database)

Use this recipe to export Omi memories into a [SurrealDB](https://surrealdb.com/) SurrealQL ingestion script for local or cloud multi-model analytics (document, graph, and vector).

SurrealDB is a modern multi-model database that combines the simplicity of document stores with relational tables, graph traversals, and full-text search. This recipe generates idempotent schema definitions, prepends `OPTION IMPORT;` for SurrealDB 3.x compliance, and outputs `UPSERT` statements that seamlessly handle nested metadata, arrays, and native `d'...'` datetime literals.

The companion script [`memories_to_surrealdb.py`](memories_to_surrealdb.py) runs on Python 3.10+ using only standard library modules (`argparse`, `json`, `sys`, `pathlib`, `datetime`).

## 1. Export memories from Omi

Export memories from your device or account:

```sh
omi --json memory list --limit 100 > memories.json
```

Or pipe directly from `omi-cli`:

```sh
omi --json memory list --limit 100 | python memories_to_surrealdb.py - -o memories.surql
```

## 2. Convert to SurrealQL script

Run the converter script:

```sh
python memories_to_surrealdb.py memories.json -o memories.surql
```

### Custom table name

Specify a custom table name if you are segregating datasets:

```sh
python memories_to_surrealdb.py memories.json -o memories.surql --table-name omi_memory
```

### Combining multiple exports

Merge multiple export files into one script with deduplication by memory ID:

```sh
python memories_to_surrealdb.py day1.json day2.json -o memories.surql --force
```

## 3. Load and query in SurrealDB

### Start a local SurrealDB instance

```sh
surreal start --user root --pass root memory
```

### Import the script

Use the SurrealDB CLI to import the generated script:

```sh
surreal import --endpoint http://localhost:8000 --user root --pass root --ns omi --db ai memories.surql
```

> **Note**: SurrealDB 3.x uses `--endpoint` (or `-e`); legacy SurrealDB 2.x used `--conn`. The script automatically emits `OPTION IMPORT;` as the initial statement required by SurrealDB 3.x.

### Analytical SurrealQL queries

Run queries using the SurrealDB CLI or web UI (Surrealist):

#### 1. Memory volume by category:

```sql
SELECT category, count() AS total
FROM memory
GROUP BY category
ORDER BY total DESC;
```

#### 2. Filter memories with specific tags:

```sql
SELECT * FROM memory WHERE tags CONTAINS 'project';
```

#### 3. Recent memories ordered by timestamp:

```sql
SELECT id, content, created_at
FROM memory
WHERE created_at > d'2026-01-01T00:00:00Z'
ORDER BY created_at DESC
LIMIT 10;
```

## Converter options

| Option | Description | Default |
| :--- | :--- | :--- |
| `INPUT ...` | One or more JSON files, or `-` for stdin | *(required)* |
| `-o`, `--output` | Destination `.surql` file | *(required)* |
| `--table-name` | Target SurrealDB table name | `memory` |
| `-f`, `--force` | Overwrite destination file if it exists | `False` |

## Verification

Run the automated test suite (10 unit tests):

```sh
python sdks/python-cli/tests/test_memories_to_surrealdb.py
```
