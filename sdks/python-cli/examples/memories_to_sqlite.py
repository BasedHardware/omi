#!/usr/bin/env python3
"""
Convert Omi memories and facts JSON exports to a SQLite database.

Usage:
    python memories_to_sqlite.py DATABASE.sqlite INPUT.json [INPUT.json ...]
    # or
    python memories_to_sqlite.py INPUT.json [INPUT.json ...] -o DATABASE.sqlite
    # or pipe directly from omi-cli:
    omi --json memory list --limit 200 | python memories_to_sqlite.py memories.sqlite -

Each run is idempotent: re-importing updates existing rows (INSERT OR REPLACE keyed on id)
and never duplicates them. The output path must not contain '..', and an existing non-SQLite
file is never overwritten.
"""

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
    """Load memories from one or more JSON exports into a SQLite database.

    Returns (loaded, added, total).
    """
    validate_db_path(database)
    # Parse every source before opening the database, so a bad export changes nothing.
    rows = [row for src in sources for row in rows_from(src)]
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
    args = sys.argv[1:]
    if "-o" in args:
        idx = args.index("-o")
        if idx + 1 >= len(args):
            sys.exit("Error: -o requires a database file path")
        db_path = args[idx + 1]
        json_sources = args[:idx] + args[idx + 2:]
    elif len(args) >= 2:
        # Check whether first or last arg is the database file
        # Convention 1: DATABASE.sqlite INPUT.json ...
        # Convention 2: INPUT.json ... DATABASE.sqlite
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
