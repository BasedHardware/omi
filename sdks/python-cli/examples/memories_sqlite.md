# Convert a memory export to SQLite

Use this recipe to store, query, and search your Omi memories, facts, and learnings in
a local SQLite database. It reads saved JSON exports, makes no network
requests, and normalises timestamps to UTC text so SQLite date and time functions
work seamlessly. You need Python 3.10+ and an authenticated `omi-cli` for the
initial export.

Export memories:

```sh
omi --json memory list --limit 200 --offset 0 > memories_0.json
```

Check that the command succeeded before converting the file. This is one page,
not a complete-account backup. To retrieve another page, increase `--offset`
by 200 and use a different filename.

Save the following as `memories_to_sqlite.py`:

```python
#!/usr/bin/env python3
"""Convert Omi memories JSON exports to a SQLite database."""

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_SQLITE_MAGIC = b"SQLite format 3\x00"

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id              TEXT PRIMARY KEY,
    content         TEXT NOT NULL,
    category        TEXT,
    created_at      TEXT,
    updated_at      TEXT,
    manually_added  INTEGER NOT NULL DEFAULT 0,
    source          TEXT,
    conversation_id TEXT,
    raw_json        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS memories_category ON memories (category);
CREATE INDEX IF NOT EXISTS memories_created_at ON memories (created_at);
CREATE INDEX IF NOT EXISTS memories_manually_added ON memories (manually_added);
CREATE INDEX IF NOT EXISTS memories_conversation_id ON memories (conversation_id);
"""


def validate_db_path(db_path: str) -> None:
    p = Path(db_path)
    if ".." in p.parts:
        raise ValueError(
            f"Output path {db_path!r} contains '..'; refusing to write outside the intended directory."
        )
    if p.exists():
        try:
            with p.open("rb") as fh:
                header = fh.read(len(_SQLITE_MAGIC))
        except OSError as exc:
            raise ValueError(f"Cannot read existing file {db_path!r}") from exc
        if header != _SQLITE_MAGIC:
            raise ValueError(
                f"{db_path!r} already exists but is not a SQLite database; refusing to overwrite it."
            )


def strip_surrogates(value: str) -> str:
    return value.encode("utf-8", "ignore").decode("utf-8")


def text(value):
    if value is None:
        return None
    if isinstance(value, str):
        return strip_surrogates(value)
    if isinstance(value, (dict, list)):
        return strip_surrogates(json.dumps(value, ensure_ascii=False))
    return strip_surrogates(str(value))


def utc_stamp(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


TRUE_VALUES = {"true", "1", "yes", "t", "y"}


def boolean_to_int(value):
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return 1 if value else 0
    if isinstance(value, str):
        return 1 if value.strip().lower() in TRUE_VALUES else 0
    return 0


def rows_from(source):
    content = Path(source).read_bytes().decode("utf-8-sig")
    items = json.loads(content)
    if isinstance(items, dict):
        for key in ("memories", "items", "data"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]
    if not isinstance(items, list):
        raise ValueError(f"{source}: expected a JSON array or object containing memories")
    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source}: each memory must be an object")
        item_id = item.get("id")
        if item_id is None or str(item_id).strip() == "":
            raise ValueError(f"{source}: memory item is missing an id")
        content_val = item.get("content") or item.get("title") or item.get("text") or ""
        rows.append((
            str(item_id),
            text(content_val) or "",
            text(item.get("category")),
            utc_stamp(item.get("created_at")),
            utc_stamp(item.get("updated_at")),
            boolean_to_int(item.get("manually_added")),
            text(item.get("source")),
            text(item.get("conversation_id")),
            json.dumps(item, ensure_ascii=False),
        ))
    return rows


def load(database, sources):
    validate_db_path(database)
    rows = [row for source in sources for row in rows_from(source)]
    connection = sqlite3.connect(database)
    try:
        connection.executescript(SCHEMA)
        before = connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        with connection:
            connection.executemany(
                "INSERT OR REPLACE INTO memories VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
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

Import into a database:

```sh
python memories_to_sqlite.py memories.sqlite memories_0.json
```

You can pass several JSON files in one run. `INSERT OR REPLACE` uses the `id`
column as the primary key, so importing the same page twice updates existing
rows without creating duplicates.

## Useful queries

Open the database in `sqlite3`:

```sh
sqlite3 memories.sqlite
```

Count memories by category:

```sql
SELECT category, COUNT(*) AS total
FROM memories
GROUP BY category
ORDER BY total DESC;
```

Find recently captured learnings or facts:

```sql
SELECT id, category, content, created_at
FROM memories
WHERE category IN ('learnings', 'work', 'skills')
ORDER BY created_at DESC
LIMIT 10;
```

Search memory contents for keywords:

```sql
SELECT id, category, content
FROM memories
WHERE content LIKE '%project%'
ORDER BY created_at DESC;
```
