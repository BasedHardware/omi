import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    category TEXT,
    tags TEXT,
    visibility TEXT,
    created_at TEXT,
    updated_at TEXT,
    is_user_created INTEGER,
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
    """Normalize boolean flag to integer 0 or 1 for SQLite."""
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return 1 if value else 0
    if isinstance(value, str):
        return 1 if value.strip().lower() in ("true", "1", "yes") else 0
    return 0


def format_tags(value):
    """Format tags as comma-separated text for simple LIKE querying while keeping raw in raw_json."""
    if value is None:
        return None
    if isinstance(value, list):
        return ", ".join(str(v).strip() for v in value if str(v).strip())
    if isinstance(value, str):
        return value.strip()
    return str(value)


def rows_from(source):
    content = Path(source).read_bytes().decode("utf-8-sig")
    items = json.loads(content)
    if isinstance(items, dict):
        for key in ("memories", "items", "data"):
            if key in items:
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
            raise ValueError(f"{source}: memory is missing an id")
        content_val = item.get("content") or item.get("title") or item.get("text") or ""
        category_val = item.get("category")
        if category_val is not None:
            category_val = str(category_val).strip().lower()

        rows.append(
            (
                str(item_id),
                text(content_val),
                text(category_val),
                format_tags(item.get("tags")),
                text(item.get("visibility")),
                utc_stamp(item.get("created_at")),
                utc_stamp(item.get("updated_at")),
                boolean_to_int(item.get("is_user_created")),
                json.dumps(item, ensure_ascii=False),
            )
        )
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
