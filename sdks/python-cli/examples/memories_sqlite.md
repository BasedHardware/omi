# Convert a memory export to SQLite

Use this recipe to store, query, and search your Omi memories, facts, learnings,
and personal knowledge in a local SQLite database. It reads saved JSON exports,
makes no network requests, and normalises timestamps to UTC text so SQLite date
and time functions work seamlessly. You need Python 3.10+ and an authenticated
`omi-cli` for the initial export. The `python -m sqlite3` interactive shell examples below require Python 3.12+.

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
    category TEXT,
    visibility TEXT,
    created_at TEXT,
    updated_at TEXT,
    tags TEXT,
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
        return value.strip()
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value).strip()


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


def normalize_tags(value):
    """Normalize tags into a compact JSON array string for json_each() queries."""
    if value is None:
        return "[]"
    if isinstance(value, list):
        clean_tags = [str(t).strip() for t in value if str(t).strip()]
        return json.dumps(clean_tags, ensure_ascii=False)
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",") if p.strip()]
        return json.dumps(parts, ensure_ascii=False)
    return "[]"


def rows_from(source):
    """Extract validated tuples from an open file-like object containing an omi export."""
    payload = json.load(source)
    if isinstance(payload, dict):
        items = payload.get("memories") or payload.get("items") or payload.get("data")
        if items is None:
            items = [payload]
    elif isinstance(payload, list):
        items = payload
    else:
        raise ValueError(f"expected JSON array or object, got {type(payload).__name__}")

    rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        mem_id = text(item.get("id"))
        if not mem_id:
            continue
        content = text(item.get("content") or item.get("text") or item.get("description") or item.get("fact"))
        if not content:
            continue
        category = text(item.get("category"))
        visibility = text(item.get("visibility") or item.get("type"))
        created_at = utc_stamp(item.get("created_at") or item.get("createdAt"))
        updated_at = utc_stamp(item.get("updated_at") or item.get("updatedAt"))
        tags = normalize_tags(item.get("tags"))
        raw_json = json.dumps(item, ensure_ascii=False, sort_keys=True)
        rows.append((mem_id, content, category, visibility, created_at, updated_at, tags, raw_json))
    return rows


def load(db_path, input_paths):
    """Validate all inputs first, then insert or replace rows into the database."""
    inputs = [Path(p) for p in input_paths]
    for p in inputs:
        if not p.is_file():
            raise FileNotFoundError(f"input file not found: {p}")

    all_rows = {}
    for p in inputs:
        with p.open("r", encoding="utf-8") as handle:
            for row in rows_from(handle):
                all_rows[row[0]] = row  # later pages/files win on duplicate id

    rows = list(all_rows.values())
    destination = Path(db_path)
    connection = sqlite3.connect(destination)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript(SCHEMA)
        before = connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        with connection:  # one transaction: all rows land, or none do
            connection.executemany(
                "INSERT OR REPLACE INTO memories VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
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
python memories_to_sqlite.py memories.sqlite memories_0.json memories_200.json
```

Query the database. Count memories by category:

```sh
python -m sqlite3 memories.sqlite "SELECT category, COUNT(*) AS count FROM memories GROUP BY category ORDER BY count DESC"
```

Find recent learnings and insights, newest first:

```sh
python -m sqlite3 memories.sqlite "SELECT id, content, created_at FROM memories WHERE category = 'learnings' ORDER BY created_at DESC"
```

Search memory contents by keyword:

```sh
python -m sqlite3 memories.sqlite "SELECT id, category, content FROM memories WHERE content LIKE '%architecture%' ORDER BY created_at DESC"
```

Inspect stored tags with SQLite's `json_each`:

```sh
python -m sqlite3 memories.sqlite "SELECT m.category, t.value AS tag, COUNT(*) FROM memories m, json_each(m.tags) t GROUP BY m.category, tag"
```

Filter by private or sensitive visibility:

```sh
python -m sqlite3 memories.sqlite "SELECT id, content, visibility FROM memories WHERE visibility = 'private'"
```

`created_at` and `updated_at` are stored as UTC `YYYY-MM-DD HH:MM:SS` text, so they sort chronologically and work with SQLite's `date()`, `datetime()`, and `strftime()`. `category` and `visibility` have indexes for fast filtering. Every original object is preserved verbatim in `raw_json` for `json_extract`. The loader validates every input file before writing, applies each run as a single transaction, and replaces rows that share an `id`, so loading the same page twice leaves exactly one row per memory item.
