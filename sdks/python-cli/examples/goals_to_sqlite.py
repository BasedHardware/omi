import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    goal_type TEXT,
    current_value REAL,
    target_value REAL,
    progress_pct REAL,
    unit TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT,
    updated_at TEXT,
    raw_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS goals_is_active ON goals (is_active);
CREATE INDEX IF NOT EXISTS goals_goal_type ON goals (goal_type);
CREATE INDEX IF NOT EXISTS goals_created_at ON goals (created_at);
"""


def text(value):
    """Store loosely typed API fields as text; anything non-null is coerced, not rejected."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)


def float_val(value):
    """Safely convert numeric fields to float, returning None if unparseable."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


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
    """Normalize active/boolean status to integer 0 or 1 for SQLite."""
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return 1 if value else 0
    if isinstance(value, str):
        return 1 if value.strip().lower() in ("true", "1", "yes", "active") else 0
    return 1  # default to active


def compute_progress_pct(current, target):
    """Calculate progress percentage safely, capped at 100% or unbounded as float."""
    if current is None or target is None:
        return 0.0
    try:
        c = float(current)
        t = float(target)
        if t <= 0:
            return 0.0
        return round((c / t) * 100.0, 2)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0.0


def rows_from(source):
    content = Path(source).read_bytes().decode("utf-8-sig")
    items = json.loads(content)
    if isinstance(items, dict):
        items = (
            items.get("goals")
            or items.get("items")
            or items.get("data")
            or [items]
        )
    if not isinstance(items, list):
        raise ValueError(f"{source}: expected a JSON array or object containing goals")
    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source}: each goal must be an object")
        item_id = item.get("id")
        if item_id is None or str(item_id).strip() == "":
            raise ValueError(f"{source}: goal is missing an id")

        title = item.get("title") or item.get("name") or item.get("description") or ""
        curr = float_val(item.get("current_value"))
        target = float_val(item.get("target_value"))
        pct = compute_progress_pct(curr, target)

        rows.append((
            str(item_id),
            text(title),
            text(item.get("goal_type")),
            curr,
            target,
            pct,
            text(item.get("unit")),
            boolean_to_int(item.get("is_active")),
            utc_stamp(item.get("created_at")),
            utc_stamp(item.get("updated_at")),
            json.dumps(item, ensure_ascii=False)
        ))
    return rows


def load(database, sources):
    """Load goals from one or more JSON exports into a SQLite database."""
    # Parse every file before opening the database, so a bad export changes nothing.
    rows = [row for source in sources for row in rows_from(source)]
    connection = sqlite3.connect(database)
    try:
        connection.executescript(SCHEMA)
        before = connection.execute("SELECT COUNT(*) FROM goals").fetchone()[0]
        with connection:  # one transaction: all rows land, or none do
            connection.executemany(
                "INSERT OR REPLACE INTO goals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        after = connection.execute("SELECT COUNT(*) FROM goals").fetchone()[0]
    finally:
        connection.close()
    return len(rows), after - before, after


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("Usage: python goals_to_sqlite.py DATABASE.sqlite INPUT.json [INPUT.json ...]")
    try:
        loaded, added, total = load(sys.argv[1], sys.argv[2:])
    except (OSError, ValueError, sqlite3.Error) as exc:
        sys.exit(f"SQLite load failed: {exc}")
    print(f"{loaded} row(s) loaded, {added} new, {loaded - added} updated, {total} goal(s) in database")
