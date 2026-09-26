# Convert a memory and knowledge export to SQLite

Use this recipe to store, query, and search your Omi memories, facts, and knowledge items in
a local SQLite database. It reads saved JSON exports or piped CLI output, makes no network
requests, and normalises timestamps to UTC text so SQLite date and time functions
work seamlessly. You need Python 3.10+ and an authenticated `omi-cli` for the initial export.

Export up to 200 memories:

```sh
omi --json memory list --limit 200 --offset 0 > memories_0.json
```

Check that the command succeeded before converting the file. This is one page,
not a complete-account backup. To retrieve another page, increase `--offset`
by 200 and use a different filename. Changes to the account between requests
can affect offset pagination; this recipe does not promise a consistent snapshot.

Save the following as `memories_to_sqlite.py`:

```python
#!/usr/bin/env python3
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    category TEXT,
    visibility TEXT,
    created_at TEXT,
    updated_at TEXT,
    tags TEXT,
    conversation_id TEXT,
    raw_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS memories_category ON memories (category);
CREATE INDEX IF NOT EXISTS memories_created_at ON memories (created_at);
CREATE INDEX IF NOT EXISTS memories_visibility ON memories (visibility);
CREATE INDEX IF NOT EXISTS memories_conversation_id ON memories (conversation_id);
"""

_SQLITE_MAGIC = b"SQLite format 3\x00"


def text(value: Any) -> Optional[str]:
    """Store loosely typed API fields as text; anything non-null is coerced, not rejected."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)


def utc_stamp(value: Optional[str]) -> Optional[str]:
    """Normalise an ISO-8601 timestamp to UTC 'YYYY-MM-DD HH:MM:SS' text.

    Returns None for None/empty so SQLite NULL is used instead of a string,
    keeping date functions (strftime, julianday) working without coercion.
    """
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        return value


def format_tags(tags: Any) -> Optional[str]:
    """Normalize tags into a JSON array string for storage and JSON1 indexing."""
    if tags is None:
        return None
    if isinstance(tags, list):
        clean_tags = [str(t).strip() for t in tags if str(t).strip()]
        return json.dumps(clean_tags, ensure_ascii=False) if clean_tags else None
    if isinstance(tags, str):
        tag_str = tags.strip()
        if not tag_str:
            return None
        if tag_str.startswith("["):
            try:
                parsed = json.loads(tag_str)
                if isinstance(parsed, list):
                    return json.dumps([str(t).strip() for t in parsed if str(t).strip()], ensure_ascii=False)
            except Exception:
                pass
        return json.dumps([t.strip() for t in tag_str.split(",") if t.strip()], ensure_ascii=False)
    return None


def validate_db_path(db_path: str) -> None:
    """Raise ValueError if *db_path* is unsafe or points at a non-SQLite file."""
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


def rows_from(source: str) -> List[Tuple]:
    """Parse one JSON source (file path or '-' for stdin) and return rows ready for INSERT."""
    if source == "-":
        content = sys.stdin.read()
    else:
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
        mem_id = item.get("id")
        if mem_id is None or str(mem_id).strip() == "":
            raise ValueError(f"{source}: memory item is missing an id")

        content_val = item.get("content") or item.get("text") or item.get("description") or ""
        cat_val = item.get("category")
        vis_val = item.get("visibility")
        tags_val = item.get("tags")
        conv_val = item.get("conversation_id")

        rows.append((
            str(mem_id),
            str(content_val),
            text(cat_val),
            text(vis_val),
            utc_stamp(item.get("created_at")),
            utc_stamp(item.get("updated_at")),
            format_tags(tags_val),
            text(conv_val),
            json.dumps(item, ensure_ascii=False)
        ))
    return rows


def load(database: str, sources: Sequence[str]) -> Tuple[int, int, int]:
    """Load memories from one or more JSON exports into a SQLite database."""
    validate_db_path(database)
    rows = [row for src in sources for row in rows_from(src)]
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
    args = sys.argv[1:]
    if "-o" in args:
        idx = args.index("-o")
        if idx + 1 >= len(args):
            sys.exit("Error: -o requires a database file path")
        db_path = args[idx + 1]
        json_sources = args[:idx] + args[idx + 2:]
    elif len(args) >= 2:
        if args[0].endswith(".db") or args[0].endswith(".sqlite") or args[0].endswith(".sqlite3"):
            db_path = args[0]
            json_sources = args[1:]
        else:
            db_path = args[-1]
            json_sources = args[:-1]
    else:
        sys.exit(
            "Usage: python memories_to_sqlite.py DATABASE.sqlite INPUT.json [INPUT.json ...]\n"
            "   or: python memories_to_sqlite.py INPUT.json [INPUT.json ...] -o DATABASE.sqlite\n"
            "   or: omi --json memory list | python memories_to_sqlite.py DATABASE.sqlite -"
        )

    try:
        loaded, added, total = load(db_path, json_sources)
        print(f"{loaded} row(s) loaded, {added} new, {loaded - added} updated, {total} memory item(s) in database")
    except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        sys.exit(f"SQLite load failed: {exc}")
```

## Running the conversion

Load a single page of memories into `memories.sqlite`:

```sh
python memories_to_sqlite.py memories.sqlite memories_0.json
```

Merge multiple pages in a single call (idempotent; duplicate items update in place):

```sh
python memories_to_sqlite.py memories.sqlite memories_0.json memories_200.json
```

Or stream directly from the `omi` CLI without creating intermediate JSON files:

```sh
omi --json memory list --limit 200 | python memories_to_sqlite.py memories.sqlite -
```

## Schema

| Column | Type | Notes |
| :--- | :--- | :--- |
| `id` | `TEXT PRIMARY KEY` | Omi unique memory ID |
| `content` | `TEXT NOT NULL` | Text of the memory, fact, or learning |
| `category` | `TEXT` | Category classification (`work`, `learnings`, `skills`, etc.) |
| `visibility` | `TEXT` | `private`, `public`, or null |
| `created_at` | `TEXT` | Normalised UTC timestamp: `YYYY-MM-DD HH:MM:SS` |
| `updated_at` | `TEXT` | Normalised UTC timestamp: `YYYY-MM-DD HH:MM:SS` |
| `tags` | `TEXT` | JSON array string of tags (e.g. `["work", "devtools"]`) |
| `conversation_id` | `TEXT` | ID of the source conversation if captured from a session |
| `raw_json` | `TEXT NOT NULL` | Full original JSON object for lossless queries via `json_extract()` |

## Useful queries

Open the database using the standard SQLite shell:

```sh
sqlite3 memories.sqlite
```

### 1. Count memories by category

```sql
SELECT
    COALESCE(category, 'uncategorized') AS category,
    COUNT(*) AS count
FROM memories
GROUP BY category
ORDER BY count DESC;
```

### 2. Search memories by keyword

```sql
SELECT
    created_at,
    category,
    content
FROM memories
WHERE content LIKE '%python%' OR content LIKE '%architecture%'
ORDER BY created_at DESC;
```

### 3. List recent memories from the last 7 days

```sql
SELECT
    datetime(created_at) AS created,
    category,
    content
FROM memories
WHERE datetime(created_at) >= datetime('now', '-7 days')
ORDER BY created_at DESC;
```

### 4. Query JSON attributes using SQLite JSON1

```sql
SELECT
    id,
    content,
    json_extract(raw_json, '$.category') AS raw_category
FROM memories
WHERE json_extract(raw_json, '$.visibility') = 'private';
```

### 5. Filter memories containing specific tags

```sql
SELECT
    content,
    tags
FROM memories
WHERE tags LIKE '%"work"%'
ORDER BY created_at DESC;
```
