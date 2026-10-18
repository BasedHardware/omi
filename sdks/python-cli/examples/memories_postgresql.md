# Load memories into PostgreSQL

Use this recipe to own your memories in PostgreSQL — the most widely adopted
open-source relational DB — and wire them into RAG pipelines, full-text
search, and `pgvector` semantic retrieval. It emits *SQL* (DDL + upserts) —
the script never connects; you pipe it to `psql`. Stdlib only. You need
Python 3.9+ and an authenticated `omi-cli` for the initial export.

## Emit the SQL

```sh
omi --json memory list > memories.json
python memories_to_postgresql.py memories.json -o memories.sql
```

## Apply it

```sh
psql -d omi -f memories.sql
```

## Schema

```sql
memories(id PRIMARY KEY, content, category, tags text[], visibility,
         manually_added bool, reviewed bool, app_id,
         created_at timestamptz, updated_at timestamptz,
         search_vector tsvector GENERATED ALWAYS AS (...))
```

Indexed on `category`, `created_at`, `manually_added` + a **GIN index on
`search_vector`** for `to_tsvector` full-text queries.

* **Idempotent** — every insert is `ON CONFLICT (id) DO UPDATE`; re-running
  a page never duplicates rows.
* **`--with-pgvector`** adds `embedding vector(1536)` + an `ivfflat` cosine
  index (requires `CREATE EXTENSION vector;`).

## Example queries

```sql
-- Full-text search
SELECT id, content FROM memories
 WHERE search_vector @@ to_tsquery('english', 'standup & meeting');

-- Category trend
SELECT category, COUNT(*) FROM memories GROUP BY 1 ORDER BY 2 DESC;

-- Nearest neighbours (with pgvector + populated embeddings)
SELECT id, content FROM memories
 ORDER BY embedding <=> $1 LIMIT 10;
```

## Automation

```sh
# cron: daily incremental pull + apply
0 3 * * *  omi --json memory list > /tmp/m.json \
        && python memories_to_postgresql.py /tmp/m.json -o /tmp/m.sql \
        && psql -d omi -f /tmp/m.sql
```

## Safety

* `..` in the `-o` path is refused.
* Exclusive `x` create — never overwrites an existing `.sql`.
* All literals single-quote-escaped — memory content can't inject SQL.
* Malformed JSON or a missing input exits `2`.
