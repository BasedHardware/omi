# Convert a conversation-list export to a SQLite database

Use this recipe when you want to query your Omi conversations with SQL — filter
by category, search titles, or join against action-items. It reads
one or more saved JSON exports, makes no network requests, and complements
[`conversations_csv.md`](conversations_csv.md) and
[`conversations_xlsx.md`](conversations_xlsx.md).

You need Python 3.10+ and an authenticated `omi-cli` for the initial export.
The `python -m sqlite3` interactive shell examples below require Python 3.12+.

Export up to 200 conversations:

```sh
omi --json conversation list --limit 200 --offset 0 > conversations.json
```

Check that the command succeeded before importing. This is one page, not a
complete-account backup. To retrieve another page, increase `--offset` by 200
and use a different filename. Changes to the account between requests can affect
offset pagination; this recipe does not promise a consistent snapshot.

Run the importer:

```sh
python sdks/python-cli/examples/conversations_to_sqlite.py conversations.json -o conversations.db
```

Multiple pages can be merged in a single run:

```sh
python sdks/python-cli/examples/conversations_to_sqlite.py \
  page1.json page2.json page3.json -o conversations.db
```

Re-running with the same or updated exports is safe: the importer uses
`INSERT OR REPLACE` keyed on `id`, so rows are updated rather than duplicated.
The output path (`-o` or the positional fallback) must not contain `..`. If the
file already exists it must be a SQLite database; a non-SQLite file is refused
rather than overwritten.

## Schema

```sql
CREATE TABLE IF NOT EXISTS conversations (
    id            TEXT PRIMARY KEY,
    title         TEXT,
    category      TEXT,
    source        TEXT,
    started_at    TEXT,   -- UTC 'YYYY-MM-DD HH:MM:SS'
    created_at    TEXT,   -- UTC 'YYYY-MM-DD HH:MM:SS'
    updated_at    TEXT,   -- UTC 'YYYY-MM-DD HH:MM:SS'
    transcript    TEXT,
    raw_json      TEXT NOT NULL
);
```

All timestamps are normalised to UTC `YYYY-MM-DD HH:MM:SS` text so SQLite date
and time functions (`strftime`, `julianday`, `date`) work without coercion.
The original record is kept verbatim in `raw_json` for `json_extract` queries.

## Example queries

```sh
python -m sqlite3 conversations.db
```

Count conversations by category:

```sql
SELECT category, COUNT(*) AS n
FROM conversations
GROUP BY category
ORDER BY n DESC;
```

Find conversations from the last 7 days:

```sql
SELECT title, started_at
FROM conversations
WHERE started_at >= date('now', '-7 days')
ORDER BY started_at DESC;
```

Extract a nested field from raw JSON (e.g. emoji):

```sql
SELECT title, json_extract(raw_json, '$.structured.emoji') AS emoji
FROM conversations
LIMIT 10;
```

Search titles:

```sql
SELECT id, title, category, started_at
FROM conversations
WHERE title LIKE '%meeting%'
ORDER BY started_at DESC;
```

Treat the exported file as private conversation data. The SQLite database
contains the same information as the source JSON. For exact unmodified values,
retain the source JSON alongside the database.
