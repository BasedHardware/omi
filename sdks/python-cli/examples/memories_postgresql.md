# Export Omi Memories to PostgreSQL (Relational + pgvector + Full-Text Search)

Use this recipe to stream and import your captured Omi memories, facts, preferences, and knowledge into a local or managed **PostgreSQL** database.

The generated schema includes:
- **Primary key and temporal indexing** (`created_at DESC`, `category`)
- **Native Full-Text Search** via PostgreSQL `tsvector` with GIN indexing for sub-millisecond lexical queries
- **Optional `pgvector` embedding support** (`vector(1536)` with IVFFlat indexing) for semantic similarity search
- **Idempotent UPSERT** (`ON CONFLICT (id) DO UPDATE`) to safely merge recurring syncs without duplication
- **Zero external Python dependencies** (uses standard library `json`, `sys`, `pathlib`, `datetime`, `argparse`)

---

## Prerequisites

1. Ensure the `omi` CLI is installed and authenticated:
   ```sh
   pip install omi-cli
   omi auth login
   ```
2. A running PostgreSQL instance (PostgreSQL 14+ recommended).
3. *(Optional)* For semantic vector similarity, enable the `pgvector` extension on your PostgreSQL database:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

---

## Quickstart

### 1. Pipe Directly to `psql`

Export your memories from Omi CLI and immediately execute the generated DDL and UPSERT statements into your target PostgreSQL database:

```sh
omi --json memory list --limit 500 | python memories_to_postgresql.py | psql -U postgres -d omi_db
```

### 2. Save to a `.sql` Migration File

Generate a standalone SQL script to inspect or execute later:

```sh
# Fetch memories to JSON
omi --json memory list --limit 500 > memories.json

# Generate PostgreSQL script
python memories_to_postgresql.py -i memories.json -o memories.sql

# Review and run with psql
psql -U postgres -d omi_db -f memories.sql
```

### 3. Enable `pgvector` Embeddings

If you store embedding vectors (such as OpenAI 1536-dimensional embeddings) alongside your memories:

```sh
python memories_to_postgresql.py -i memories.json -o memories_vector.sql --with-pgvector --vector-dim 1536
```

---

## PostgreSQL Database Schema

The generated schema creates the `omi_memories` table:

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS omi_memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    category TEXT,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ,
    manually_added BOOLEAN DEFAULT FALSE,
    deleted BOOLEAN DEFAULT FALSE,
    score INTEGER DEFAULT 0,
    metadata JSONB,
    search_vector tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED
);

CREATE INDEX IF NOT EXISTS idx_omi_memories_created_at ON omi_memories (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_omi_memories_category ON omi_memories (category);
CREATE INDEX IF NOT EXISTS idx_omi_memories_search ON omi_memories USING GIN (search_vector);
```

---

## Example Queries

### 1. Full-Text Search (Lexical Search)

Find memories containing specific terms using PostgreSQL's native lexical search engine:

```sql
SELECT
    id,
    category,
    content,
    created_at
FROM omi_memories
WHERE search_vector @@ to_tsquery('english', 'coffee | tea')
ORDER BY created_at DESC;
```

### 2. Category Aggregation & Counts

Group memories by category to audit your captured knowledge breakdown:

```sql
SELECT
    coalesce(category, 'uncategorized') AS category,
    count(*) AS total_count,
    max(created_at) AS latest_memory
FROM omi_memories
WHERE NOT deleted
GROUP BY 1
ORDER BY total_count DESC;
```

### 3. Semantic Vector Search (pgvector)

When `--with-pgvector` is enabled, run cosine similarity search against query embeddings:

```sql
-- Query top 5 most semantically relevant memories to a target embedding vector
SELECT
    id,
    content,
    1 - (embedding <=> '[0.012, -0.043, ...]'::vector) AS cosine_similarity
FROM omi_memories
WHERE embedding IS NOT NULL
ORDER BY embedding <=> '[0.012, -0.043, ...]'::vector
LIMIT 5;
```

---

## Automation: Periodic Sync Cron

Sync your memories nightly to your local PostgreSQL data warehouse:

```sh
# Crontab entry (every midnight)
0 0 * * * omi --json memory list --limit 1000 | python /path/to/memories_to_postgresql.py --no-schema | psql -U postgres -d omi_db -q
```
