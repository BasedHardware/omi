# Convert a memory-list export to a SQLite database

Use this recipe when you want to query your Omi memories with SQL — filter by
category or visibility, search content, or join against conversation exports.
It reads one or more saved JSON exports, makes no network requests, and
complements [`memories_csv.md`](memories_csv.md) and
[`memories_markdown.md`](memories_markdown.md).

You need Python 3.10+ and an authenticated `omi-cli` for the initial export.
The `python -m sqlite3` interactive shell examples below require Python 3.12+.

Export up to 200 memories:

```sh
omi --json memory list --limit 200 --offset 0 > memories.json
```

Check that the command succeeded before importing. This is one page, not a
complete-account backup. To retrieve another page, increase `--offset` by 200
and use a different filename. Changes to the account between requests can affect
offset pagination; this recipe does not promise a consistent snapshot.

Run the importer:

```sh
python sdks/python-cli/examples/memories_to_sqlite.py memories.json -o memories.db
```

Multiple pages can be merged in a single run:

```sh
python sdks/python-cli/examples/memories_to_sqlite.py \
  page1.json page2.json page3.json -o memories.db
```

Re-running with the same or updated exports is safe: the importer uses
`INSERT OR REPLACE` keyed on `id`, so rows are updated rather than duplicated.
The output path (`-o` or the positional fallback) must not contain `..`. If the
file already exists it must be a SQLite database; a non-SQLite file is refused
rather than overwritten.

## Schema

```sql
CREATE TABLE IF NOT EXISTS memories (
    id         TEXT PRIMARY KEY,
    content    TEXT,
    category   TEXT,
    visibility TEXT,
    tags       TEXT,   -- semicolon-joined
    created_at TEXT,   -- UTC 'YYYY-MM-DD HH:MM:SS'
    raw_json   TEXT NOT NULL
);
```

All timestamps are normalised to UTC `YYYY-MM-DD HH:MM:SS` text so SQLite date
and time functions (`strftime`, `julianday`, `date`) work without coercion.
The `tags` field is stored as a semicolon-joined string so it remains searchable
with `LIKE` while staying simple to split on read. The original record is kept
verbatim in `raw_json` for `json_extract` queries.

## Example queries

```sh
python -m sqlite3 memories.db
```

Count memories by category:

```sql
SELECT category, COUNT(*) AS n
FROM memories
GROUP BY category
ORDER BY n DESC;
```

Find memories created in the last 7 days:

```sql
SELECT id, content
FROM memories
WHERE created_at >= date('now', '-7 days')
ORDER BY created_at DESC;
```

Filter by visibility:

```sql
SELECT id, category, content
FROM memories
WHERE visibility = 'public'
ORDER BY created_at DESC;
```

Search content:

```sql
SELECT id, category, created_at
FROM memories
WHERE content LIKE '%architecture%'
ORDER BY created_at DESC;
```

Find memories with a specific tag:

```sql
SELECT id, content
FROM memories
WHERE tags LIKE '%workflow%';
```

Treat the exported file as private memory data. The SQLite database contains
the same information as the source JSON. For exact unmodified values, retain the
source JSON alongside the database.
