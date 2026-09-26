# Export Omi memories into a ClickHouse analytical table

Use this recipe when you want SQL, time-series rollups, and full-text style search over the facts and memories Omi has captured, instead of a flat note or spreadsheet. It reads a saved JSON export (or stdin), makes no network requests from the Python script, and writes either a ClickHouse `CREATE TABLE` + `INSERT` script or a `JSONEachRow` stream that `clickhouse-client` and the HTTP interface can ingest directly.

The script uses only the Python standard library (`argparse`, `json`, `sys`, `pathlib`, `datetime`). Pair it with a local or cloud ClickHouse server.

---

## Prerequisites

1. An authenticated `omi` CLI that can list memories.
2. ClickHouse server and either `clickhouse-client` or the HTTP interface on `localhost:8123`.
3. Python 3.10+.

```sh
pip install omi-cli
omi auth login
omi memory list
```

---

## Table schema

The script emits this table. `ReplacingMergeTree(updated_at)` keeps the newest row per key when you re-import edited memories.

```sql
CREATE TABLE IF NOT EXISTS omi_memories
(
    id String,
    content String,
    category LowCardinality(String),
    visibility LowCardinality(String),
    created_at DateTime64(3, 'UTC'),
    updated_at DateTime64(3, 'UTC'),
    manually_added UInt8,
    tags Array(String),
    metadata_json String
) ENGINE = ReplacingMergeTree(updated_at)
PRIMARY KEY (id)
ORDER BY (id, category)
PARTITION BY toYYYYMM(created_at);
```

`PRIMARY KEY (id)` is an exact prefix of `ORDER BY (id, category)`, which ClickHouse requires.

---

## Quickstart

`omi memory list` defaults to `--limit 25` and accepts at most `--limit 200`. The commands below use that maximum. For libraries larger than 200 memories, paginate with `--offset` (for example `--limit 200 --offset 200`) and combine the pages before ingest.

### 1. Create the table, then stream rows over HTTP (JSONEachRow)

```sh
# Create the table (multi-statement stdin needs -n)
python memories_to_clickhouse.py --schema-only | clickhouse-client -n

# Stream one page of memories as JSONEachRow
omi --json memory list --limit 200 | python memories_to_clickhouse.py --format jsonl \
  | clickhouse-client -q "INSERT INTO omi_memories FORMAT JSONEachRow"
```

If you prefer the HTTP interface on a local server that accepts your user:

```sh
python memories_to_clickhouse.py --schema-only | curl -sS "http://localhost:8123/" --data-binary @-

omi --json memory list --limit 200 | python memories_to_clickhouse.py --format jsonl \
  | curl -sS "http://localhost:8123/?query=INSERT+INTO+omi_memories+FORMAT+JSONEachRow" --data-binary @-
```

### 2. Build a standalone SQL script and execute it

```sh
omi --json memory list --limit 200 > memories.json
python memories_to_clickhouse.py memories.json --no-schema -o memories_inserts.sql
clickhouse-client -n < memories_inserts.sql
```

Drop `--no-schema` when the destination table does not exist yet. To emit only DDL:

```sh
python memories_to_clickhouse.py --schema-only > memories_clickhouse.sql
clickhouse-client -n < memories_clickhouse.sql
```

### 3. Analytical queries

Monthly memory volume by category:

```sql
SELECT
    toStartOfMonth(created_at) AS month,
    category,
    count() AS new_memories
FROM omi_memories
GROUP BY month, category
ORDER BY month DESC, new_memories DESC;
```

Category coverage with latest activity (deduplicated):

```sql
SELECT
    category,
    count() AS total_items,
    max(created_at) AS latest_activity
FROM omi_memories
FINAL
GROUP BY category
ORDER BY total_items DESC;
```

Token search over content:

```sql
SELECT
    id,
    category,
    content,
    created_at
FROM omi_memories
WHERE hasTokenCaseInsensitive(content, 'project')
ORDER BY created_at DESC
LIMIT 50;
```

---

## Field mapping

| omi memory field | ClickHouse column | Notes |
| --- | --- | --- |
| `id` | `id String` | Required. Missing or empty `id` aborts the export. |
| `content` | `content String` | Non-strings are JSON-encoded. |
| `category` | `category LowCardinality(String)` | Defaults to `uncategorized`. |
| `visibility` | `visibility LowCardinality(String)` | Defaults to `private`. |
| `created_at` | `created_at DateTime64(3, 'UTC')` | ISO-8601 input, stored in UTC. |
| `updated_at` | `updated_at DateTime64(3, 'UTC')` | Falls back to `created_at`. |
| `manually_added` | `manually_added UInt8` | Coerced from bool / int / `true`/`yes`/`1`. |
| `tags` | `tags Array(String)` | Non-list values become a one-element array. |
| `metadata` / `metadata_json` | `metadata_json String` | Compact JSON text. |

---

## Notes

- Unparseable or missing `created_at` / `updated_at` values become `1970-01-01 00:00:00.000` (Unix epoch) so a bad export row still loads. Check the table if you see a cluster of epoch timestamps.

- String literals and array elements are escaped for ClickHouse SQL. Prefer `--format jsonl` for bulk load; it avoids SQL quoting entirely.
- The Python script reads local JSON only and writes SQL or JSONEachRow to stdout (or `--output`). Keep exports private.
- After repeated imports, use `FINAL` (or `OPTIMIZE TABLE omi_memories FINAL`) when you need one row per memory id.
