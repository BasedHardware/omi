# Import memories export to SQLite

Use this recipe to store, index, and query your Omi memories, facts, and learnings
in a local SQLite database with Full-Text Search (FTS5). It reads saved JSON exports,
makes no network requests, normalises timestamps to UTC, and supports multi-page
merges idempotently. You need Python 3.10+ and an authenticated `omi-cli` for the
initial export.

## Step 1: Export memories

Export up to 200 memories to a JSON file:

```sh
omi --json memory list --limit 200 --offset 0 > memories_0.json
```

To export another page, increase `--offset` by 200:

```sh
omi --json memory list --limit 200 --offset 200 > memories_1.json
```

## Step 2: Import into SQLite

Run the script against your exported files:

```sh
python memories_to_sqlite.py memories_0.json --db memories.sqlite
python memories_to_sqlite.py memories_1.json --db memories.sqlite
```

Or pipe directly from `omi-cli`:

```sh
omi --json memory list --limit 200 | python memories_to_sqlite.py - --db memories.sqlite
```

## Useful SQL Queries

### 1. Full-Text Search (FTS5) for keywords

Search across all memories matching "project" or "deploy":

```sql
SELECT m.id, m.category, m.content, m.created_at
FROM memories m
JOIN memories_fts f ON m.rowid = f.rowid
WHERE memories_fts MATCH 'project OR deploy'
ORDER BY m.created_at DESC;
```

### 2. Breakdown by category

```sql
SELECT category, count(*) AS count
FROM memories
GROUP BY category
ORDER BY count DESC;
```

### 3. Recent learnings or facts

```sql
SELECT content, tags, created_at
FROM memories
WHERE category IN ('learnings', 'skills')
ORDER BY created_at DESC
LIMIT 10;
```

## Security & Reliability Invariants

- **Full-Text Search Indexing**: Automated FTS5 virtual table with triggers for sync on insert, update, or delete.
- **Idempotent Multi-Page Merges**: Uses `ON CONFLICT(id) DO UPDATE` so re-importing updated memories triggers `memories_au` to keep full-text indexes synchronized.
- **Surrogate Pair Defense**: Strips unpaired UTF-16 surrogates to prevent `sqlite3.UnicodeEncodeError` exceptions.
- **Path Traversal Protection**: Rejects paths containing `..` components.
- **File Integrity Validation**: Confirms SQLite 3 magic byte header on pre-existing files (rejecting partial or non-SQLite files) to avoid corrupting unrelated data.
