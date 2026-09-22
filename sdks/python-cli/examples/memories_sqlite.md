# Convert a memory and facts export to SQLite

Use this recipe when you want to query, search, and organize your Omi memories and facts with
SQL — filter by category, run full-text search over insights, or join against conversations and action items.
It reads one or more saved JSON exports, makes no network requests, and complements [`memories_csv.md`](memories_csv.md)
and [`memories_markdown.md`](memories_markdown.md).

You need Python 3.10+ and an authenticated `omi-cli` for the initial export.
The `python -m sqlite3` interactive shell examples below require Python 3.12+.

Export up to 200 memories:

```sh
omi --json memory list --limit 200 --offset 0 > memories_0.json
```

Check that the command succeeded before importing. This is one page, not a
complete-account backup. To retrieve another page, increase `--offset` by 200
and use a different filename. Changes to the account between requests can affect
offset pagination; this recipe does not promise a consistent snapshot.

Save the following as `memories_to_sqlite.py`:

```python
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id          TEXT PRIMARY KEY,
    content     TEXT NOT NULL,
    category    TEXT,
    visibility  TEXT,
    created_at  TEXT,   -- UTC 'YYYY-MM-DD HH:MM:SS'
    tags        TEXT,   -- semicolon-separated tags
    raw_json    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS memories_category ON memories (category);
CREATE INDEX IF NOT EXISTS memories_created_at ON memories (created_at);
CREATE INDEX IF NOT EXISTS memories_visibility ON memories (visibility);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    id UNINDEXED,
    content,
    category,
    tags,
    content='memories',
    content_rowid='rowid'
);

-- Triggers to keep FTS index synchronized with the main table
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, id, content, category, tags)
    VALUES (new.rowid, new.id, new.content, new.category, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, id, content, category, tags)
    VALUES('delete', old.rowid, old.id, old.content, old.category, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, id, content, category, tags)
    VALUES('delete', old.rowid, old.id, old.content, old.category, old.tags);
    INSERT INTO memories_fts(rowid, id, content, category, tags)
    VALUES (new.rowid, new.id, new.content, new.category, new.tags);
END;
"""


def text(value):
    """Store loosely typed API fields as text; anything non-null is coerced, not rejected."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)


def utc_stamp(value):
    """Normalise an ISO-8601 timestamp to UTC 'YYYY-MM-DD HH:MM:SS' so SQLite date functions work."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def format_tags(tags):
    """Normalize tags list to semicolon-separated string."""
    if isinstance(tags, list):
        return "; ".join(str(t) for t in tags)
    return text(tags)


def rows_from(source):
    content = Path(source).read_bytes().decode("utf-8-sig")
    items = json.loads(content)
    if isinstance(items, dict):
        items = items.get("memories") or items.get("items") or items.get("data") or [items]
    if not isinstance(items, list):
        raise ValueError(f"{source}: expected a JSON array or object containing memories")
    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source}: each memory must be an object")
        item_id = item.get("id")
        if item_id is None or str(item_id).strip() == "":
            raise ValueError(f"{source}: memory item is missing an id")
        raw_content = item.get("content") or item.get("text") or item.get("title") or ""
        visibility = item.get("visibility") or ("private" if item.get("is_private") else "public")
        created_at = item.get("created_at") or item.get("createdAt")
        tags = item.get("tags") or []
        rows.append((
            str(item_id),
            text(raw_content),
            text(item.get("category")),
            text(visibility),
            utc_stamp(created_at),
            format_tags(tags),
            json.dumps(item, ensure_ascii=False),
        ))
    return rows


def load(database, sources):
    """Load memories from one or more JSON exports into a SQLite database."""
    rows = [row for source in sources for row in rows_from(source)]
    connection = sqlite3.connect(database)
    try:
        connection.executescript(SCHEMA)
        before = connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        with connection:
            connection.executemany(
                "INSERT OR REPLACE INTO memories VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        after = connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    finally:
        connection.close()
    return len(rows), after - before, after


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("Usage: python memories_to_sqlite.py DATABASE.sqlite INPUT.json [INPUT.json ...]")
    try:
        loaded, added, total = load(sys.argv[1], sys.argv[2:])
    except (OSError, ValueError, sqlite3.Error) as exc:
        sys.exit(f"SQLite load failed: {exc}")
    print(f"{loaded} row(s) loaded, {added} new, {loaded - added} updated, {total} memory item(s) in database")
```

Load the exported pages (repeat with new exports at any time):

```sh
python memories_to_sqlite.py memories.sqlite memories_0.json
```

Multiple pages can be merged in a single run:

```sh
python memories_to_sqlite.py memories.sqlite page1.json page2.json page3.json
```

## Example queries

```sh
python -m sqlite3 memories.sqlite
```

Count memories by category:

```sql
SELECT category, COUNT(*) AS total
FROM memories
GROUP BY category
ORDER BY total DESC;
```

Full-text search across all memories using FTS5:

```sql
SELECT id, category, content
FROM memories_fts
WHERE memories_fts MATCH 'python OR fastapi'
LIMIT 10;
```

Find memories recorded in the last 14 days:

```sql
SELECT category, content, created_at
FROM memories
WHERE created_at >= date('now', '-14 days')
ORDER BY created_at DESC;
```

List private memories:

```sql
SELECT id, category, content
FROM memories
WHERE visibility = 'private'
ORDER BY created_at DESC;
```

`created_at` timestamps are stored as UTC `YYYY-MM-DD HH:MM:SS` text, so they sort
chronologically and work with SQLite's `date()`, `datetime()`, and `strftime()`.
The original record is kept verbatim in `raw_json` for `json_extract` queries.
Treat the exported database as private knowledge data.
