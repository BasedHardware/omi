# Export Memories to PostgreSQL

This recipe demonstrates how to export Omi memories into an idempotent PostgreSQL database using the standard library converter script [`memories_to_postgresql.py`](memories_to_postgresql.py).

The generated SQL script includes:
- Idempotent schema definition (`CREATE TABLE IF NOT EXISTS memories`).
- Full-text search column (`tsvector`) with GIN indexing for high-speed keyword search and ranking.
- Flexible JSONB metadata indexing.
- `ON CONFLICT (id) DO UPDATE` upsert semantics so repeated imports safely refresh existing records.
- Transaction wrapping (`BEGIN;` ... `COMMIT;`).

## Quickstart

### 1. Export memories from Omi CLI

Export your captured memories to a JSON file:

```bash
# Export the latest 200 memories (maximum per request is 200)
omi --json memory list --limit 200 > memories.json
```

> **Note on Pagination**: The `omi memory list` command supports `--limit` up to 200. To export larger archives, paginate using `--offset`:
> ```bash
> omi --json memory list --limit 200 --offset 0 > page1.json
> omi --json memory list --limit 200 --offset 200 > page2.json
> ```

### 2. Convert to PostgreSQL SQL

Convert the JSON export into a PostgreSQL script:

```bash
# Convert to a SQL file
python memories_to_postgresql.py memories.json -o memories.sql

# Or overwrite an existing output file
python memories_to_postgresql.py memories.json -o memories.sql --overwrite
```

### 3. Stream directly into PostgreSQL via pipeline

You can pipe data directly from the CLI into `psql` without writing intermediate files:

```bash
omi --json memory list --limit 200 | python memories_to_postgresql.py - | psql -d omi_db
```

### 4. Execute the SQL script in PostgreSQL

Load the generated SQL file into your PostgreSQL database:

```bash
psql -U postgres -d omi_db -f memories.sql
```

---

## Schema Overview

The converter provisions the following table and indexes:

```sql
CREATE TABLE IF NOT EXISTS memories (
    id VARCHAR(255) PRIMARY KEY,
    content TEXT NOT NULL,
    category VARCHAR(100),
    tags TEXT,
    visibility VARCHAR(50) DEFAULT 'private',
    source VARCHAR(100),
    conversation_id VARCHAR(255),
    created_at TIMESTAMP WITHOUT TIME ZONE,
    updated_at TIMESTAMP WITHOUT TIME ZONE,
    raw_json JSONB NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(content, '') || ' ' || coalesce(category, '') || ' ' || coalesce(tags, ''))
    ) STORED
);

CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memories_category ON memories (category);
CREATE INDEX IF NOT EXISTS idx_memories_search ON memories USING gin (search_vector);
CREATE INDEX IF NOT EXISTS idx_memories_raw_json ON memories USING gin (raw_json);
```

---

## Useful PostgreSQL Queries

### 1. Full-Text Search with Relevance Ranking

Search for memories matching keywords with ranking via `ts_rank`:

```sql
SELECT
    id,
    category,
    content,
    ts_rank(search_vector, query) AS rank
FROM memories, to_tsquery('english', 'python & postgresql') query
WHERE search_vector @@ query
ORDER BY rank DESC;
```

### 2. Breakdown by Category

Count memories across all categories:

```sql
SELECT
    category,
    COUNT(*) AS total_memories,
    MAX(created_at) AS latest_entry
FROM memories
GROUP BY category
ORDER BY total_memories DESC;
```

### 3. Querying Recent Memories

Retrieve memories created in the last 7 days:

```sql
SELECT
    id,
    category,
    content,
    created_at
FROM memories
WHERE created_at >= NOW() - INTERVAL '7 days'
ORDER BY created_at DESC;
```

### 4. Inspecting JSONB Metadata

Query memories containing custom tags or structured attributes:

```sql
SELECT
    id,
    content,
    raw_json->>'visibility' AS visibility
FROM memories
WHERE raw_json ? 'tags';
```

---

## Script Options

```text
usage: memories_to_postgresql.py [-h] [-i INPUT_OPT] [-o OUTPUT] [--no-schema] [-f] [input]

Convert Omi memories JSON export into an idempotent PostgreSQL SQL script.

positional arguments:
  input                 Path to JSON file (or '-' / omit for stdin)

options:
  -h, --help            show this help message and exit
  -i, --input INPUT_OPT Path to JSON file (or '-' for stdin)
  -o, --output OUTPUT   Target SQL file (default: stdout)
  --no-schema           Omit DDL schema generation (only generate INSERT statements)
  -f, --overwrite       Overwrite target output file if it already exists
```
