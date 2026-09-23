# Convert an action-item export to SQLite

Use this recipe to store, query, and search your Omi tasks and action items in
a local SQLite database. It reads saved JSON exports, makes no network
requests, and normalises timestamps to UTC text so SQLite date and time functions
work seamlessly. You need Python 3.10+ and an authenticated `omi-cli` for the
initial export.

Export up to 200 action items:

```sh
omi --json action-item list --limit 200 --offset 0 > action_items_0.json
```

Check that the command succeeded before converting the file. This is one page,
not a complete-account backup. To retrieve another page, increase `--offset`
by 200 and use a different filename. Changes to the account between requests
can affect offset pagination; this recipe does not promise a consistent
snapshot.

Save the following as `action_items_to_sqlite.py`:

```python
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS action_items (
    id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    completed INTEGER NOT NULL,
    due_at TEXT,
    created_at TEXT,
    updated_at TEXT,
    conversation_id TEXT,
    raw_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS action_items_completed ON action_items (completed);
CREATE INDEX IF NOT EXISTS action_items_created_at ON action_items (created_at);
CREATE INDEX IF NOT EXISTS action_items_conversation_id ON action_items (conversation_id);
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
    """Normalize completed status to integer 0 or 1 for SQLite."""
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return 1 if value else 0
    if isinstance(value, str):
        return 1 if value.strip().lower() in ("true", "1", "yes") else 0
    return 0


def rows_from(source):
    content = Path(source).read_bytes().decode("utf-8-sig")
    items = json.loads(content)
    if isinstance(items, dict):
        items = (
            items.get("action_items")
            or items.get("items")
            or items.get("data")
            or [items]
        )
    if not isinstance(items, list):
        raise ValueError(f"{source}: expected a JSON array or object containing action items")
    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source}: each action item must be an object")
        item_id = item.get("id")
        if item_id is None or str(item_id).strip() == "":
            raise ValueError(f"{source}: action item is missing an id")
        description = item.get("description") or item.get("title") or ""
        rows.append((
            str(item_id),
            text(description),
            boolean_to_int(item.get("completed")),
            utc_stamp(item.get("due_at")),
            utc_stamp(item.get("created_at")),
            utc_stamp(item.get("updated_at")),
            text(item.get("conversation_id")),
            json.dumps(item, ensure_ascii=False)
        ))
    return rows


def load(database, sources):
    """Load action items from one or more JSON exports into a SQLite database."""
    # Parse every file before opening the database, so a bad export changes nothing.
    rows = [row for source in sources for row in rows_from(source)]
    connection = sqlite3.connect(database)
    try:
        connection.executescript(SCHEMA)
        before = connection.execute("SELECT COUNT(*) FROM action_items").fetchone()[0]
        with connection:  # one transaction: all rows land, or none do
            connection.executemany(
                "INSERT OR REPLACE INTO action_items VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        after = connection.execute("SELECT COUNT(*) FROM action_items").fetchone()[0]
    finally:
        connection.close()
    return len(rows), after - before, after


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("Usage: python action_items_to_sqlite.py DATABASE.sqlite INPUT.json [INPUT.json ...]")
    try:
        loaded, added, total = load(sys.argv[1], sys.argv[2:])
    except (OSError, ValueError, sqlite3.Error) as exc:
        sys.exit(f"SQLite load failed: {exc}")
    print(f"{loaded} row(s) loaded, {added} new, {loaded - added} updated, {total} action item(s) in database")
```

Load the exported pages (repeat with new exports at any time):

```sh
python action_items_to_sqlite.py tasks.sqlite action_items_0.json action_items_200.json
```

Query the database. Count open vs completed tasks:

```sh
python -m sqlite3 tasks.sqlite "SELECT CASE completed WHEN 1 THEN 'completed' ELSE 'open' END AS status, COUNT(*) AS count FROM action_items GROUP BY completed"
```

Find pending action items, newest first:

```sh
python -m sqlite3 tasks.sqlite "SELECT id, description, created_at FROM action_items WHERE completed = 0 ORDER BY created_at DESC"
```

Search tasks by keyword:

```sh
python -m sqlite3 tasks.sqlite "SELECT description, completed FROM action_items WHERE description LIKE '%review%' ORDER BY created_at DESC"
```

`created_at`, `updated_at`, and `due_at` are stored as UTC `YYYY-MM-DD HH:MM:SS` text,
so they sort chronologically and work with SQLite's `date()`, `datetime()`, and
`strftime()`. `completed` is stored as `0` or `1` with an index for fast status filtering.
Every original object is preserved verbatim in `raw_json` for `json_extract`. The loader
validates every input file before writing, applies each run as a single transaction, and
replaces rows that share an `id`, so loading the same page twice leaves exactly one row per
action item.
