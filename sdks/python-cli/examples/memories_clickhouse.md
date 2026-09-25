# Export Omi Memories to ClickHouse (High-Performance Analytical Data Warehouse)

Use this recipe to stream and import your captured Omi memories, facts, preferences, and knowledge into a local or cloud **ClickHouse** analytical database.

ClickHouse is optimized for real-time aggregation, pattern extraction, and large-scale trend analysis across millions of temporal events with columnar compression.

The generated schema includes:
- **`ReplacingMergeTree(updated_at)` Engine** to automatically deduplicate records when memories are edited or re-synced
- **Primary & Sorting Key** (`PRIMARY KEY (id) ORDER BY (id, category)`) ensuring strict prefix alignment and instant sparse indexing
- **Monthly Partitioning** (`PARTITION BY toYYYYMM(created_at)`) for rapid pruning of temporal memory ranges
- **LowCardinality Strings** on categories and visibility for compact dictionary-encoded memory layouts
- **Native Array Storage** for memory tags (`tags Array(String)`)
- **Two Ingestion Modes**: Standard SQL `INSERT` script or high-throughput streaming `JSONEachRow` format
- **Zero External Python Dependencies** (uses standard library `json`, `sys`, `pathlib`, `datetime`, `argparse`)

---

## Prerequisites

1. Ensure the `omi` CLI is installed and authenticated:
   ```sh
   pip install omi-cli
   omi auth login
   ```
2. A running ClickHouse instance (Local Docker container, native server, or ClickHouse Cloud).

To start a lightweight local ClickHouse instance via Docker:
```sh
docker run -d --name omi-clickhouse -p 8123:8123 -p 9000:9000 clickhouse/clickhouse-server
```

---

## Quickstart

### 1. High-Throughput HTTP Stream (JSONEachRow)

Initialize the schema and stream memories directly from the Omi CLI into ClickHouse via its native HTTP interface:

```sh
# 1. Initialize schema first
python memories_to_clickhouse.py --schema-only | clickhouse-client -n
# (Or initialize via HTTP: python memories_to_clickhouse.py --schema-only | curl -sS "http://localhost:8123/" --data-binary @-)

# 2. Stream memories in JSONEachRow format directly via HTTP POST (up to CLI limit of 200)
omi --json memory list --limit 200 | python memories_to_clickhouse.py --format jsonl | \
  curl -sS "http://localhost:8123/?query=INSERT+INTO+omi_memories+FORMAT+JSONEachRow" --data-binary @-
```

### 2. Export Standalone SQL Script

Generate a standalone SQL script containing table definitions and batch insert statements:

```sh
# Fetch memories to JSON (up to CLI limit of 200)
omi --json memory list --limit 200 > memories.json

# Generate ClickHouse SQL script
python memories_to_clickhouse.py -i memories.json -o memories_clickhouse.sql

# Execute with clickhouse-client (multi-query mode)
clickhouse-client -n < memories_clickhouse.sql
```

> **Note on Pagination:** `omi memory list` defaults to `--limit 25` and accepts up to `--limit 200`. For libraries with more than 200 memories, paginate with `--offset` batches (e.g., `--limit 200 --offset 200`) and pipe or combine the outputs.

---

## ClickHouse Table Schema

The generated schema creates the `omi_memories` table:

```sql
CREATE TABLE IF NOT EXISTS omi_memories (
    id String,
    content String,
    category LowCardinality(String),
    visibility LowCardinality(String) DEFAULT 'private',
    created_at DateTime64(3, 'UTC'),
    updated_at DateTime64(3, 'UTC'),
    manually_added UInt8 DEFAULT 0,
    tags Array(String),
    metadata_json String
) ENGINE = ReplacingMergeTree(updated_at)
PRIMARY KEY (id)
ORDER BY (id, category)
PARTITION BY toYYYYMM(created_at);
```

---

## Example Analytical Queries

### 1. Memory Velocity & Growth Over Time

Calculate monthly memory creation velocity and active categories:

```sql
SELECT
    toStartOfMonth(created_at) AS month,
    category,
    count(*) AS new_memories,
    countIf(manually_added = 1) AS user_curated
FROM omi_memories FINAL
GROUP BY month, category
ORDER BY month DESC, new_memories DESC;
```

### 2. Category Distribution & Tag Aggregation

Break down memories by classification with activity metrics:

```sql
SELECT
    category,
    count(*) AS total_items,
    max(created_at) AS latest_activity
FROM omi_memories FINAL
GROUP BY category
ORDER BY total_items DESC;
```

### 3. Full-Text Token Search

Search memory contents using ClickHouse case-insensitive token search:

```sql
SELECT
    id,
    category,
    content,
    created_at
FROM omi_memories FINAL
WHERE hasTokenCaseInsensitive(content, 'project')
ORDER BY created_at DESC
LIMIT 10;
```
