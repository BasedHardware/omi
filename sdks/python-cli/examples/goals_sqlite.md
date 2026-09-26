# Convert a goal export to SQLite

Use this recipe to store, query, and track your Omi goals in a local SQLite
database. It reads saved JSON exports, makes no network requests, and normalises
timestamps to UTC text so SQLite date and time functions work seamlessly.
You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export up to 200 goals:

```sh
omi --json goal list --limit 200 --offset 0 > goals_0.json
```

Check that the command succeeded before converting the file. This is one page,
not a complete-account backup. To retrieve another page, increase `--offset`
by 200 and use a different filename. Changes to the account between requests
can affect offset pagination; this recipe does not promise a consistent
snapshot.

Save the following as `goals_to_sqlite.py`:

```python
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    goal_type TEXT NOT NULL,
    target_value REAL NOT NULL,
    current_value REAL NOT NULL,
    min_value REAL NOT NULL,
    max_value REAL NOT NULL,
    unit TEXT,
    is_active INTEGER NOT NULL,
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


def boolean_to_int(value, default=1):
    """Normalize boolean status to integer 0 or 1 for SQLite."""
    if value is None:
        return default
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return 1 if value else 0
    if isinstance(value, str):
        return 1 if value.strip().lower() in ("true", "1", "yes") else 0
    return default


def float_val(value, default=0.0):
    """Safely coerce numeric value to float for SQLite REAL column."""
    if value is None:
        return float(default)
    try:
        return float(value)
    except (ValueError, TypeError):
        return float(default)


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
        title = item.get("title") or item.get("name") or ""
        goal_type = item.get("goal_type") or "scale"
        target_val = float_val(item.get("target_value"), default=10.0)
        current_val = float_val(item.get("current_value"), default=0.0)
        min_val = float_val(item.get("min_value"), default=0.0)
        max_val = float_val(item.get("max_value"), default=10.0)
        unit = text(item.get("unit"))
        is_active = boolean_to_int(item.get("is_active"), default=1)
        created_at = utc_stamp(item.get("created_at"))
        updated_at = utc_stamp(item.get("updated_at"))
        raw_json = json.dumps(item, ensure_ascii=False)

        rows.append((
            str(item_id),
            text(title),
            text(goal_type),
            target_val,
            current_val,
            min_val,
            max_val,
            unit,
            is_active,
            created_at,
            updated_at,
            raw_json,
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
                "INSERT OR REPLACE INTO goals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
```

Load the exported pages (repeat with new exports at any time):

```sh
python goals_to_sqlite.py goals.sqlite goals_0.json goals_200.json
```

Query the database. List active goals and their progress percentage:

```sh
python -m sqlite3 goals.sqlite "SELECT title, goal_type, current_value, target_value, unit, CASE WHEN target_value = min_value THEN 100.0 ELSE ROUND(((current_value - min_value) / (target_value - min_value)) * 100.0, 1) END AS progress_pct FROM goals WHERE is_active = 1 ORDER BY created_at DESC"
```

Count active vs archived goals by goal type:

```sh
python -m sqlite3 goals.sqlite "SELECT goal_type, CASE is_active WHEN 1 THEN 'active' ELSE 'archived' END AS status, COUNT(*) AS count FROM goals GROUP BY goal_type, is_active"
```

Find completed goals where current value meets or exceeds target value:

```sh
python -m sqlite3 goals.sqlite "SELECT id, title, current_value, target_value, unit FROM goals WHERE current_value >= target_value AND is_active = 1"
```

`created_at` and `updated_at` are stored as UTC `YYYY-MM-DD HH:MM:SS` text, so they
sort chronologically and work with SQLite's `date()`, `datetime()`, and `strftime()`.
`is_active` and `goal_type` are indexed for fast filtering. Every original object is
preserved verbatim in `raw_json` for `json_extract`. The loader validates every input
file before writing, applies each run as a single transaction, and replaces rows that
share an `id`, so loading the same page twice leaves exactly one row per goal.
