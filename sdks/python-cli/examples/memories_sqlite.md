# Convert a memory-list export to SQLite with FTS5 search

Use this recipe to convert captured Omi memories, facts, learnings, and user
preferences into a local SQLite database (`memories.db`). It automatically
configures B-tree category/date indexes and an `FTS5` virtual table with triggers
for instant, sub-millisecond local full-text search across your second brain.

It reads a saved JSON export or standard input (`-`), makes no network requests,
and requires no external packages. You need Python 3.10+ and an authenticated
`omi-cli` for the initial export.

---

## Quickstart

### 1. Direct Pipeline Export (Stdout to SQLite)

Stream up to 200 memories directly into an SQLite database:

```sh
omi --json memory list --limit 200 | python memories_to_sqlite.py - memories.db
```

### 2. Export from a Saved JSON File

If you have already saved an export:

```sh
omi --json memory list --limit 200 --offset 0 > memories.json
python memories_to_sqlite.py memories.json memories.db
```

Check that the command succeeded before converting the file. This is one page,
not a complete-account backup. To retrieve another page, increase `--offset`
by 200 and re-run. The script uses idempotent `INSERT OR REPLACE`, so re-running
or appending pages safely updates existing rows without duplication.

### 3. Filter by Category

Export only specific categories of memories into a specialized database:

```sh
python memories_to_sqlite.py memories.json work_memories.db --category work,learnings
```

---

## Converter Script

Save the following as `memories_to_sqlite.py`:

```python
import argparse
import json
import sqlite3
import sys
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    source TEXT,
    tags TEXT,
    raw_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_memories_category ON memories (category);
CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories (created_at);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content,
    category,
    tags,
    content=memories,
    content_rowid=rowid
);

-- Triggers to keep FTS index synchronized with the main memories table
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content, category, tags)
    VALUES (new.rowid, new.content, new.category, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, category, tags)
    VALUES('delete', old.rowid, old.content, old.category, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, category, tags)
    VALUES('delete', old.rowid, old.content, old.category, old.tags);
    INSERT INTO memories_fts(rowid, content, category, tags)
    VALUES (new.rowid, new.content, new.category, new.tags);
END;
"""


def init_db(conn: sqlite3.Connection):
    """Initialize database schema with tables, indexes, and full-text search triggers."""
    conn.executescript(SCHEMA_SQL)


def insert_memory(cursor: sqlite3.Cursor, item: dict):
    """Insert or update a single memory record in the database."""
    item_id = item.get("id")
    if not item_id:
        return False

    category = item.get("category") or "general"
    content = item.get("content") or item.get("text") or item.get("memory") or ""
    created_at = item.get("created_at") or ""
    updated_at = item.get("updated_at")
    source = item.get("source") or "unknown"
    tags_raw = item.get("tags") or []
    tags_str = json.dumps(tags_raw, ensure_ascii=False) if isinstance(tags_raw, list) else str(tags_raw)
    raw_json = json.dumps(item, ensure_ascii=False)

    cursor.execute(
        """
        INSERT OR REPLACE INTO memories (id, category, content, created_at, updated_at, source, tags, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (item_id, category, content, created_at, updated_at, source, tags_str, raw_json)
    )
    return True


def convert(source: str, destination: str, categories=None):
    """Convert JSON memories from stdin or a file into an SQLite database."""
    if source == "-":
        content = sys.stdin.read()
    else:
        content = Path(source).read_text(encoding="utf-8")

    data = json.loads(content)
    if isinstance(data, dict) and "memories" in data:
        data = data["memories"]
    if not isinstance(data, list):
        raise ValueError("Expected a JSON array of memories from 'omi --json memory list'")

    cat_filter = set(categories) if categories else None

    db_path = Path(destination)
    conn = sqlite3.connect(db_path)
    init_db(conn)

    count = 0
    with conn:
        cursor = conn.cursor()
        for item in data:
            if not isinstance(item, dict):
                continue
            cat = item.get("category") or "general"
            if cat_filter and cat not in cat_filter:
                continue
            if insert_memory(cursor, item):
                count += 1

    conn.close()
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert Omi memory list JSON export to SQLite with FTS5 search.")
    parser.add_argument("source", help="Path to input JSON file or '-' for stdin.")
    parser.add_argument("destination", help="Path to output SQLite database file.")
    parser.add_argument(
        "--category",
        help="Optional comma-separated categories to include (e.g. 'work,learnings')."
    )

    args = parser.parse_args()
    cats = [c.strip() for c in args.category.split(",") if c.strip()] if args.category else None

    try:
        count = convert(args.source, args.destination, categories=cats)
    except (ValueError, OSError) as exc:
        sys.exit(f"Conversion failed: {exc}")

    print(f"Successfully stored {count} memor{'ies' if count != 1 else 'y'} in {args.destination}")
```

---

## Query Recipes

Once exported, you can query your memories via the `sqlite3` CLI or any programming language:

### 1. Instant Full-Text Search via FTS5

```sql
SELECT memories.id, memories.category, memories.content
FROM memories
JOIN memories_fts ON memories.rowid = memories_fts.rowid
WHERE memories_fts MATCH 'python OR fastapi'
ORDER BY rank;
```

### 2. Count Memories by Category

```sql
SELECT category, COUNT(*) as count
FROM memories
GROUP BY category
ORDER BY count DESC;
```

### 3. Retrieve Latest Knowledge Entries

```sql
SELECT content, created_at
FROM memories
WHERE category = 'learnings'
ORDER BY created_at DESC
LIMIT 10;
```
