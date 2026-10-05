#!/usr/bin/env python3
"""Import Omi memories JSON exports into a SQLite database.

Creates a structured schema with full-text search (FTS5) support,
indexes by category and timestamp, handles multi-page merges idempotently,
and protects against lone surrogate crashes and directory traversal.
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SQLITE_MAGIC = b"SQLite format 3\x00"

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    category TEXT,
    tags TEXT,
    visibility TEXT,
    source TEXT,
    conversation_id TEXT,
    created_at TEXT,
    updated_at TEXT,
    raw_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS memories_category ON memories (category);
CREATE INDEX IF NOT EXISTS memories_created_at ON memories (created_at);
CREATE INDEX IF NOT EXISTS memories_source ON memories (source);
"""

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content,
    category,
    tags,
    content='memories',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content, category, tags) VALUES (new.rowid, new.content, new.category, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, category, tags) VALUES('delete', old.rowid, old.content, old.category, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, category, tags) VALUES('delete', old.rowid, old.content, old.category, old.tags);
    INSERT INTO memories_fts(rowid, content, category, tags) VALUES (new.rowid, new.content, new.category, new.tags);
END;
"""


def strip_surrogates(text: Optional[str]) -> Optional[str]:
    """Remove lone surrogates which trigger UnicodeEncodeError in SQLite."""
    if text is None:
        return None
    return text.encode("utf-8", "ignore").decode("utf-8")


def normalize_utc_timestamp(value: Any) -> Optional[str]:
    """Convert ISO timestamp to UTC 'YYYY-MM-DD HH:MM:SS' string."""
    if not value or not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def serialize_tags(tags: Any) -> Optional[str]:
    """Serialize tags array or string into comma-separated text."""
    if tags is None:
        return None
    if isinstance(tags, list):
        cleaned = [strip_surrogates(str(t).strip()) for t in tags if str(t).strip()]
        return ", ".join(cleaned) if cleaned else None
    s = strip_surrogates(str(tags).strip())
    return s if s else None


def validate_db_path(db_path: str) -> Path:
    """Validate output path for security and SQLite file integrity."""
    p = Path(db_path)
    if ".." in p.parts:
        raise ValueError(f"Output path {db_path!r} contains '..'; refusing relative traversal.")
    if p.exists() and p.is_file():
        if p.stat().st_size < 16:
            raise ValueError(f"Existing file {db_path!r} is too small to be a valid SQLite database.")
        with open(p, "rb") as f:
            header = f.read(16)
        if header != _SQLITE_MAGIC:
            raise ValueError(f"Existing file {db_path!r} is not a valid SQLite database.")
    return p


def prepare_memory_record(item: Dict[str, Any]) -> Tuple[Any, ...]:
    """Prepare a sanitized tuple for parameterized SQLite insertion."""
    mem_id = strip_surrogates(str(item.get("id") or "").strip())
    content = strip_surrogates(str(item.get("content") or "").strip())
    category = strip_surrogates(item.get("category"))
    if category is not None:
        category = str(category).strip().lower()

    tags = serialize_tags(item.get("tags"))
    visibility = strip_surrogates(item.get("visibility"))
    source = strip_surrogates(item.get("source"))
    conversation_id = strip_surrogates(item.get("conversation_id"))
    created_at = normalize_utc_timestamp(item.get("created_at"))
    updated_at = normalize_utc_timestamp(item.get("updated_at"))

    raw_json = json.dumps(item, ensure_ascii=False)
    raw_json = strip_surrogates(raw_json) or "{}"

    return (
        mem_id,
        content,
        category,
        tags,
        visibility,
        source,
        conversation_id,
        created_at,
        updated_at,
        raw_json,
    )


def import_memories_to_sqlite(items: List[Dict[str, Any]], db_path: str) -> int:
    """Import an array of memory objects into a SQLite database atomically."""
    path = validate_db_path(db_path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    try:
        cursor = conn.cursor()
        cursor.executescript(SCHEMA)

        # Attempt FTS5 index setup
        try:
            cursor.executescript(FTS_SCHEMA)
        except sqlite3.OperationalError:
            # FTS5 might not be compiled in rare non-standard builds; fallback gracefully
            pass

        records = [prepare_memory_record(it) for it in items if isinstance(it, dict) and it.get("id")]

        cursor.executemany(
            """
            INSERT INTO memories (
                id, content, category, tags, visibility, source,
                conversation_id, created_at, updated_at, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                content=excluded.content,
                category=excluded.category,
                tags=excluded.tags,
                visibility=excluded.visibility,
                source=excluded.source,
                conversation_id=excluded.conversation_id,
                created_at=excluded.created_at,
                updated_at=excluded.updated_at,
                raw_json=excluded.raw_json
            """,
            records,
        )

        conn.commit()
        return len(records)
    finally:
        conn.close()


def load_input_json(source: Optional[str]) -> List[Dict[str, Any]]:
    """Load JSON from standard input or file path."""
    if source is None or source == "-":
        raw = sys.stdin.read()
    else:
        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError(f"Input file not found: {source}")
        raw = path.read_text(encoding="utf-8")

    data = json.loads(raw)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("memories", "data", "items"):
            if key in data and isinstance(data[key], list):
                return data[key]
        return [data]
    raise ValueError("Input JSON must be an array or object containing memories.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import Omi memories JSON export into a local SQLite database.",
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="-",
        help="Path to JSON file (or '-' / omit for stdin)",
    )
    parser.add_argument(
        "-d",
        "--db",
        default="memories.sqlite",
        help="Target SQLite database file (default: memories.sqlite)",
    )

    args = parser.parse_args()

    try:
        items = load_input_json(args.input)
        count = import_memories_to_sqlite(items=items, db_path=args.db)
        print(f"Successfully imported {count} memories into {args.db}")
    except Exception as err:
        sys.stderr.write(f"Error: {err}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
