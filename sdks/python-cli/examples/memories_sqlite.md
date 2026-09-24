# Convert a memory export to SQLite with FTS5 search

Use this recipe to store, query, and search your personal Omi memories, learnings, and second-brain facts in a local SQLite database. It reads saved JSON exports or piped input via `stdin`, normalises timestamps to UTC text so SQLite date and time functions work seamlessly, extracts knowledge tags into a relational lookup table, and automatically maintains an **FTS5 full-text search index** for instantaneous keyword, phrase, and Boolean queries. You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

## 1. Export your memories

Export your captured memories (up to 200 per page):

```sh
omi --json memory list --limit 200 --offset 0 > memories_0.json
```

Check that the command succeeded before converting the file. If you have more than 200 memories, retrieve subsequent pages into separate files:

```sh
omi --json memory list --limit 200 --offset 200 > memories_200.json
```

## 2. Load into SQLite

Run the companion script [`memories_to_sqlite.py`](memories_to_sqlite.py):

```sh
# Load one or more exported JSON files
python sdks/python-cli/examples/memories_to_sqlite.py memories.sqlite memories_0.json memories_200.json

# Or stream directly via stdin pipeline
omi --json memory list --limit 200 | python sdks/python-cli/examples/memories_to_sqlite.py memories.sqlite -
```

Each run is idempotent: re-importing the same files updates existing rows (`INSERT OR REPLACE` keyed on `id`), refreshes tags, and keeps the FTS5 full-text search table synchronized without duplicate records.

## 3. Query the database

Query the database using Python's built-in `sqlite3` CLI or any SQLite GUI tool.

### Lightning-fast full-text search (BM25 ranked)

Search memories across content, category, and tags using native FTS5 matching:

```sh
python -m sqlite3 memories.sqlite "SELECT m.id, m.category, m.content FROM memories m JOIN memories_fts f ON m.id = f.id WHERE memories_fts MATCH 'python OR rust' ORDER BY rank;"
```

### Prefix search and phrase queries

Match word prefixes (e.g. `micro*` for microservices) or exact phrases:

```sh
python -m sqlite3 memories.sqlite "SELECT content FROM memories_fts WHERE memories_fts MATCH '\"dark mode\"';"
```

### Knowledge tags frequency ranking

Find your most common knowledge tags and topics across your entire memory archive:

```sh
python -m sqlite3 memories.sqlite "SELECT tag, COUNT(*) AS count FROM memory_tags GROUP BY tag ORDER BY count DESC LIMIT 10;"
```

### Find all memories with a specific tag

Relational query joining memories with normalized tags:

```sh
python -m sqlite3 memories.sqlite "SELECT m.content, m.created_at FROM memories m JOIN memory_tags t ON m.id = t.memory_id WHERE t.tag = 'database' ORDER BY m.created_at DESC;"
```

### Breakdown by category

```sh
python -m sqlite3 memories.sqlite "SELECT COALESCE(category, '(uncategorized)') AS category, COUNT(*) AS total FROM memories GROUP BY category ORDER BY total DESC;"
```

## 4. Database Schema

The database tables, relations, and full-text indexes are automatically provisioned:

```sql
CREATE TABLE IF NOT EXISTS memories (
    id          TEXT PRIMARY KEY,
    content     TEXT NOT NULL,
    category    TEXT,
    created_at  TEXT,
    updated_at  TEXT,
    raw_json    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_category ON memories (category);
CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories (created_at);

CREATE TABLE IF NOT EXISTS memory_tags (
    memory_id   TEXT NOT NULL,
    tag         TEXT NOT NULL,
    PRIMARY KEY (memory_id, tag),
    FOREIGN KEY (memory_id) REFERENCES memories (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_memory_tags_tag ON memory_tags (tag);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    id UNINDEXED,
    content,
    category,
    tags
);
```

- `created_at` and `updated_at` are stored as UTC `YYYY-MM-DD HH:MM:SS` text for chronological ordering and compatibility with SQLite's `date()` and `datetime()` functions.
- `memories_fts` enables BM25 ranking (`ORDER BY rank`), phrase proximity queries, and boolean expressions (`AND`, `OR`, `NOT`).
- `raw_json` retains the original unmodified JSON object for `json_extract`.

## 5. Automated Verification

Run the automated unit test suite with:

```sh
python sdks/python-cli/tests/test_memories_to_sqlite.py
```
