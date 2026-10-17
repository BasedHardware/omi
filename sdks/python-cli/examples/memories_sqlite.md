# Convert a memories export to a SQLite database

Use this recipe when you want to query your Omi memories with SQL — filter
by category, search keywords, or join against conversations and action items. It reads
one or more saved JSON exports, makes no network requests, and complements
[`memories_markdown.md`](memories_markdown.md).

You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export your memories:

```sh
omi --json memory list --limit 200 --offset 0 > memories.json
```

Check that the command succeeded before importing.

Run the importer:

```sh
python sdks/python-cli/examples/memories_to_sqlite.py memories.json -o memories.db
```

Or pipe directly from standard input:

```sh
omi --json memory list | python sdks/python-cli/examples/memories_to_sqlite.py - -o memories.db
```

Multiple files can be merged in a single run:

```sh
python sdks/python-cli/examples/memories_to_sqlite.py \
  batch1.json batch2.json -o memories.db
```

Re-running with the same or updated exports is safe: the importer uses
`INSERT OR REPLACE` keyed on `id`, so rows are updated rather than duplicated.
The output path (`-o` or `--output`) must not contain `..`. If the file already
exists it must be a SQLite database; a non-SQLite file is refused rather than
overwritten.

## Schema

```sql
CREATE TABLE IF NOT EXISTS memories (
    id            TEXT PRIMARY KEY,
    content       TEXT NOT NULL,
    category      TEXT,
    visibility    TEXT,
    tags          TEXT,
    created_at    TEXT,   -- UTC 'YYYY-MM-DD HH:MM:SS'
    updated_at    TEXT,   -- UTC 'YYYY-MM-DD HH:MM:SS'
    raw_json      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS memories_category ON memories (category);
CREATE INDEX IF NOT EXISTS memories_created_at ON memories (created_at);
```

All timestamps are normalised to UTC `YYYY-MM-DD HH:MM:SS` text so SQLite date
and time functions (`strftime`, `julianday`, `date`) work without coercion.
The original record is kept verbatim in `raw_json` for `json_extract` queries.
