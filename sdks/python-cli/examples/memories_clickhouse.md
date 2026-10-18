# Stream memories into ClickHouse

Use this recipe for high-performance temporal analytics on memories —
category trends, capture-rate curves, large columnar scans. It emits a
`ReplacingMergeTree` schema plus either SQL `INSERT`s or streaming
`JSONEachRow` — the script never connects; you pipe it to
`clickhouse-client` or `curl`. Stdlib only. You need Python 3.9+ and an
authenticated `omi-cli` for the initial export.

## Emit + load (SQL mode)

```sh
omi --json memory list > memories.json
python memories_to_clickhouse.py memories.json -o memories.sql
clickhouse-client --multiquery < memories.sql
```

## Emit + stream (JSONEachRow mode)

```sh
python memories_to_clickhouse.py memories.json --format jsoneachrow -o memories.jsonl
curl -sS 'http://localhost:8123/?query=INSERT%20INTO%20memories%20FORMAT%20JSONEachRow' \
    --data-binary @memories.jsonl
```

## Schema

```sql
memories(id String, content String,
         category LowCardinality(String),      -- dictionary-encoded
         tags Array(String),
         visibility LowCardinality(String),
         manually_added UInt8, reviewed UInt8,
         app_id LowCardinality(String),
         created_at DateTime64(3, 'UTC'),
         updated_at DateTime64(3, 'UTC'))
ENGINE = ReplacingMergeTree(updated_at)   -- re-inserts overwrite by id
PARTITION BY toYYYYMM(created_at)         -- monthly partitions
ORDER BY id
```

`ReplacingMergeTree` means re-importing an updated page collapses to the
newest row per `id` — no duplicates to dedupe in queries.

## Example queries

```sql
-- capture rate per month
SELECT toStartOfMonth(created_at) AS m, COUNT(*)
FROM memories GROUP BY m ORDER BY m;

-- category trend
SELECT category, COUNT(*) FROM memories GROUP BY category ORDER BY 2 DESC;

-- full-text-ish scan (ClickHouse string search)
SELECT id, content FROM memories WHERE content ILIKE '%standup%';
```

## Safety

* `..` in the `-o` path is refused.
* Exclusive `x` create — never overwrites.
* SQL literals backslash-escaped (`'` → `\'`, `\` → `\\`).
* Malformed JSON or missing input exits `2`.
