# Convert a memories export to a SQLite database

Use this recipe when you want to query your Omi memories, facts, and learnings with SQL — filter by category, search content keywords, filter by visibility, or join against conversations and action items. It reads one or more saved JSON exports or accepts piped input from `omi-cli`, makes no network requests, and complements [`memories_markdown.md`](memories_markdown.md) and [`conversations_sqlite.md`](conversations_sqlite.md).

You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export memories to JSON:

```sh
omi --json memory list --limit 200 --offset 0 > memories.json
```

Or pipe directly from stdin:

```sh
omi --json memory list | python sdks/python-cli/examples/memories_to_sqlite.py - -o memories.db
```

Import one or more saved JSON files:

```sh
python sdks/python-cli/examples/memories_to_sqlite.py memories.json -o memories.db
```

Multiple pages can be merged in a single run:

```sh
python sdks/python-cli/examples/memories_to_sqlite.py \
  page1.json page2.json page3.json -o memories.db
```

Re-running with the same or updated exports is safe: the importer uses `INSERT OR REPLACE` keyed on `id`, so rows are updated rather than duplicated. The output path must not contain `..`. If the file already exists it must be a SQLite database; a non-SQLite file is refused rather than overwritten.

## Schema

```sql
CREATE TABLE IF NOT EXISTS memories (
    id            TEXT PRIMARY KEY,
    content       TEXT,
    category      TEXT,
    visibility    TEXT,
    tags          TEXT,   -- comma-separated tags
    created_at    TEXT,   -- UTC 'YYYY-MM-DD HH:MM:SS'
    updated_at    TEXT,   -- UTC 'YYYY-MM-DD HH:MM:SS'
    raw_json      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at);
```

All timestamps are normalised to UTC `YYYY-MM-DD HH:MM:SS` text so SQLite date and time functions (`strftime`, `julianday`, `date`) work without coercion. The original record is kept verbatim in `raw_json` for `json_extract` queries.

## Example queries

Search memories mentioning specific skills or topics:

```sql
SELECT id, category, content, created_at
FROM memories
WHERE content LIKE '%Python%' OR content LIKE '%SQLite%'
ORDER BY created_at DESC;
```

Count memories by category:

```sql
SELECT category, COUNT(*) AS total
FROM memories
GROUP BY category
ORDER BY total DESC;
```

Filter by visibility and extract fields from `raw_json`:

```sql
SELECT id, content, json_extract(raw_json, '$.manually_added') AS is_manual
FROM memories
WHERE visibility = 'private';
```
