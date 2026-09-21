# Convert a memory export to SQLite

Use this recipe to store, query, and search your Omi memories, facts, and learnings in
a local SQLite database. It reads saved JSON exports, makes no network
requests, and normalises timestamps to UTC text so SQLite date and time functions
work seamlessly. You need Python 3.10+ and an authenticated `omi-cli` for the
initial export.

Export up to 200 memories:

```sh
omi --json memory list --limit 200 --offset 0 > memories_0.json
```

Check that the command succeeded before converting the file. This is one page,
not a complete-account backup. To retrieve another page, increase `--offset`
by 200 and use a different filename. Changes to the account between requests
can affect offset pagination; this recipe does not promise a consistent
snapshot.

Save the following as `memories_to_sqlite.py`:

```python
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    category TEXT NOT NULL,
    visibility TEXT,
    tags TEXT,
    created_at TEXT,
    updated_at TEXT,
    manually_added INTEGER NOT NULL DEFAULT 0,
    reviewed INTEGER NOT NULL DEFAULT 0,
    edited INTEGER NOT NULL DEFAULT 0,
    raw_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS memories_category ON memories (category);
CREATE INDEX IF NOT EXISTS memories_created_at ON memories (created_at);
CREATE INDEX IF NOT EXISTS memories_visibility ON memories (visibility);
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


def boolean_to_int(value):
    """Normalize boolean or truthy/falsy status to integer 0 or 1 for SQLite."""
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return 1 if value else 0
    if isinstance(value, str):
        return 1 if value.strip().lower() in ("true", "1", "yes") else 0
    return 0


def tags_to_text(value):
    """Normalize tags into a JSON array string for JSON1 extension and text search."""
    if value is None:
        return "[]"
    if isinstance(value, list):
        return json.dumps([str(t) for t in value], ensure_ascii=False)
    if isinstance(value, str):
        val = value.strip()
        if val.startswith("[") and val.endswith("]"):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    return json.dumps([str(t) for t in parsed], ensure_ascii=False)
            except json.JSONDecodeError:
                pass
        parts = [p.strip() for p in val.split(",") if p.strip()]
        return json.dumps(parts, ensure_ascii=False)
    return "[]"


def rows_from(source):
    content = Path(source).read_bytes().decode("utf-8-sig")
    items = json.loads(content)
    if isinstance(items, dict):
        items = (
            items.get("memories")
            or items.get("items")
            or items.get("data")
            or [items]
        )
    if not isinstance(items, list):
        raise ValueError(f"{source}: expected a JSON array or object containing memories")
    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source}: each memory must be an object")
        item_id = item.get("id")
        if item_id is None or str(item_id).strip() == "":
            raise ValueError(f"{source}: memory is missing an id")
        content_val = item.get("content") or item.get("text") or ""
        category_val = item.get("category") or "other"
        visibility_val = item.get("visibility") or "private"
        rows.append((
            str(item_id),
            text(content_val),
            text(category_val),
            text(visibility_val),
            tags_to_text(item.get("tags")),
            utc_stamp(item.get("created_at")),
            utc_stamp(item.get("updated_at")),
            boolean_to_int(item.get("manually_added")),
            boolean_to_int(item.get("reviewed")),
            boolean_to_int(item.get("edited")),
            json.dumps(item, ensure_ascii=False)
        ))
    return rows


def load(database, sources):
    """Load memories from one or more JSON exports into a SQLite database."""
    # Parse every file before opening the database, so a bad export changes nothing.
    rows = [row for source in sources for row in rows_from(source)]
    connection = sqlite3.connect(database)
    try:
        connection.executescript(SCHEMA)
        before = connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        with connection:  # one transaction: all rows land, or none do
            connection.executemany(
                "INSERT OR REPLACE INTO memories VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
    print(f"{loaded} row(s) loaded, {added} new, {loaded - added} updated, {total} memory/memories in database")
```

Load the exported pages (repeat with new exports at any time):

```sh
python memories_to_sqlite.py memories.sqlite memories_0.json memories_200.json
```

Query the database. Count memories by category:

```sh
python -m sqlite3 memories.sqlite "SELECT category, COUNT(*) AS count FROM memories GROUP BY category ORDER BY count DESC"
```

Find recent memories, newest first:

```sh
python -m sqlite3 memories.sqlite "SELECT id, category, content, created_at FROM memories ORDER BY created_at DESC LIMIT 10"
```

Search memories by keyword:

```sh
python -m sqlite3 memories.sqlite "SELECT category, content FROM memories WHERE content LIKE '%python%' ORDER BY created_at DESC"
```

Query memories containing a specific tag:

```sh
python -m sqlite3 memories.sqlite "SELECT m.category, m.content, tag.value AS tag FROM memories m, json_each(m.tags) tag WHERE tag.value = 'workflow'"
```

Check reviewed vs unreviewed memories:

```sh
python -m sqlite3 memories.sqlite "SELECT CASE reviewed WHEN 1 THEN 'reviewed' ELSE 'unreviewed' END AS status, COUNT(*) AS count FROM memories GROUP BY reviewed"
```

`created_at` and `updated_at` are stored as UTC `YYYY-MM-DD HH:MM:SS` text,
so they sort chronologically and work with SQLite's `date()`, `datetime()`, and
`strftime()`. `category`, `created_at`, and `visibility` are indexed for fast
filtering. `tags` are stored as a JSON array string enabling both `LIKE` pattern matching
and SQLite `json_each()` expansion. Every original object is preserved verbatim in `raw_json`
for `json_extract`. The loader validates every input file before writing, applies each run
as a single transaction, and replaces rows that share an `id`, so loading the same page
twice leaves exactly one row per memory.
