# Load conversation-list exports into SQLite and query them

Use this recipe when one page of `conversation list` is not enough: load every
exported page into a single SQLite file, then search, count and group
conversations with plain SQL. Re-running the loader on a fresh export updates
existing rows by conversation ID instead of duplicating them. It reads saved
JSON exports, makes no network requests, and does not export transcripts. You
need Python 3.10+ and an authenticated `omi-cli` for the initial export (the
query examples use `python -m sqlite3`, which needs Python 3.12+; any other
SQLite shell works too).

This is separate from `omi local sql`, which queries the Omi Desktop app's own
database on the same machine. This recipe works from the dev API export on any
machine, with no desktop app installed.

Export as many pages as you need, one file per page:

```sh
omi --json conversation list --limit 200 --offset 0 > conversations_0.json
omi --json conversation list --limit 200 --offset 200 > conversations_200.json
```

Check that each command succeeded before loading the files. Changes to the
account between requests can affect offset pagination; this recipe does not
promise a consistent snapshot, but loading a later export again corrects the
rows it contains.

Save the following as `conversations_to_sqlite.py`:

```python
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT,
    category TEXT,
    started_at TEXT,
    finished_at TEXT,
    duration_seconds INTEGER,
    source TEXT,
    language TEXT,
    folder_name TEXT,
    raw_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS conversations_started_at ON conversations (started_at);
CREATE INDEX IF NOT EXISTS conversations_category ON conversations (category);
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
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def rows_from(source):
    items = json.loads(Path(source).read_bytes())
    if not isinstance(items, list):
        raise ValueError(f"{source}: expected the JSON array from omi --json conversation list")
    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source}: each conversation must be an object")
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            raise ValueError(f"{source}: each conversation needs a string id")
        structured = item.get("structured")
        if structured is None:
            structured = {}
        if not isinstance(structured, dict):
            raise ValueError(f"{source}: conversation structured field must be an object or null")
        started, finished = utc_stamp(item.get("started_at")), utc_stamp(item.get("finished_at"))
        duration = None
        if started and finished:
            delta = datetime.fromisoformat(finished) - datetime.fromisoformat(started)
            duration = int(delta.total_seconds()) if delta.total_seconds() >= 0 else None
        rows.append((item_id, text(structured.get("title")), text(structured.get("category")), started, finished,
                     duration, text(item.get("source")), text(item.get("language")), text(item.get("folder_name")),
                     json.dumps(item, ensure_ascii=False)))
    return rows


def load(database, sources):
    # Parse every file before opening the database, so a bad export changes nothing.
    rows = [row for source in sources for row in rows_from(source)]
    connection = sqlite3.connect(database)
    try:
        connection.executescript(SCHEMA)
        before = connection.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        with connection:  # one transaction: all rows land, or none do
            connection.executemany("INSERT OR REPLACE INTO conversations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        after = connection.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
    finally:
        connection.close()
    return len(rows), after - before, after


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("Usage: python conversations_to_sqlite.py DATABASE.sqlite INPUT.json [INPUT.json ...]")
    try:
        loaded, added, total = load(sys.argv[1], sys.argv[2:])
    except (OSError, ValueError, sqlite3.Error) as exc:
        sys.exit(f"SQLite load failed: {exc}")
    print(f"{loaded} row(s) loaded, {added} new, {loaded - added} updated, {total} conversation(s) in database")
```

Load the exported pages (repeat with new exports at any time):

```sh
python conversations_to_sqlite.py conversations.sqlite conversations_0.json conversations_200.json
```

Query the database. Conversations per category:

```sh
python -m sqlite3 conversations.sqlite "SELECT category, COUNT(*) AS n FROM conversations GROUP BY category ORDER BY n DESC"
```

Search titles, most recent first:

```sh
python -m sqlite3 conversations.sqlite "SELECT started_at, title FROM conversations WHERE title LIKE '%budget%' ORDER BY started_at DESC"
```

Total recorded hours per month:

```sh
python -m sqlite3 conversations.sqlite "SELECT substr(started_at, 1, 7) AS month, ROUND(SUM(duration_seconds) / 3600.0, 1) AS hours FROM conversations GROUP BY month ORDER BY month"
```

`started_at` and `finished_at` are stored as UTC `YYYY-MM-DD HH:MM:SS` text, so
they sort correctly and work with SQLite's `date()`, `datetime()` and
`strftime()`; `duration_seconds` is `NULL` when either timestamp is missing or
the end precedes the start. Every original object is kept verbatim in
`raw_json`, so fields this table does not flatten can still be read with
`json_extract(raw_json, '$.folder_id')`. The loader validates every input file
before it writes, applies each run as a single transaction, and replaces rows
that share an `id`, so loading the same page twice leaves one row per
conversation. Treat the database file as private conversation data.
