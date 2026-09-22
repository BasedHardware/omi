#!/usr/bin/env python3
"""
Convert Omi conversation-list JSON export to a SQLite database.

Usage:
    python conversations_to_sqlite.py conversations.json [conversations2.json ...] -o conversations.db

Each run is idempotent: re-importing the same page updates existing rows
(INSERT OR REPLACE keyed on id) and never duplicates them. The output path
must not contain '..', and an existing non-SQLite file is never overwritten.
"""

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

SCHEMA: str = """
CREATE TABLE IF NOT EXISTS conversations (
    id            TEXT PRIMARY KEY,
    title         TEXT,
    category      TEXT,
    source        TEXT,
    started_at    TEXT,
    created_at    TEXT,
    updated_at    TEXT,
    transcript    TEXT,
    raw_json      TEXT NOT NULL
);
"""


def utc_stamp(value: Optional[str]) -> Optional[str]:
    """Normalise an ISO-8601 timestamp to UTC 'YYYY-MM-DD HH:MM:SS' text.

    Returns None for None/empty so SQLite NULL is used instead of a string,
    keeping date functions (strftime, julianday) working without coercion.
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        return value


def rows_from(pages: Sequence[str]) -> List[Tuple]:
    """Parse one or more exported JSON pages and return rows ready for INSERT."""
    rows: List[Tuple] = []
    for path in pages:
        raw = Path(path).read_text(encoding="utf-8").lstrip("\ufeff")
        items = json.loads(raw)
        # Support both bare array and wrapped {"conversations": [...]} shape
        if isinstance(items, dict):
            for key in ("conversations", "items", "data"):
                if isinstance(items.get(key), list):
                    items = items[key]
                    break
        if not isinstance(items, list):
            raise ValueError(f"{path}: expected a JSON array or wrapped object")
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"{path}: each conversation must be a JSON object")
            conv_id = item.get("id")
            if not conv_id:
                raise ValueError(f"{path}: conversation missing required 'id' field")
            structured: Dict[str, Any] = item.get("structured") or {}
            rows.append((
                str(conv_id),
                structured.get("title"),
                structured.get("category"),
                item.get("source"),
                utc_stamp(item.get("started_at")),
                utc_stamp(item.get("created_at")),
                utc_stamp(item.get("updated_at")),
                item.get("transcript"),
                json.dumps(item, ensure_ascii=False),
            ))
    return rows


_SQLITE_MAGIC = b"SQLite format 3\x00"


def validate_db_path(db_path: str) -> None:
    """Raise ValueError if *db_path* is unsafe or points at a non-SQLite file.

    Rules enforced:
    - The path must not contain '..' components (prevents directory traversal).
    - If the file already exists it must be a valid SQLite database (magic-byte
      check), so we never silently corrupt an unrelated file.
    """
    p = Path(db_path)
    if ".." in p.parts:
        raise ValueError(
            f"Output path {db_path!r} contains '..'; refusing to write outside "
            "the intended directory."
        )
    if p.exists():
        try:
            with p.open("rb") as fh:
                header = fh.read(len(_SQLITE_MAGIC))
        except OSError as exc:
            raise ValueError(f"Cannot read existing file {db_path!r}") from exc
        if header != _SQLITE_MAGIC:
            raise ValueError(
                f"{db_path!r} already exists but is not a SQLite database; "
                "refusing to overwrite it."
            )


def load(db_path: str, json_paths: Sequence[str]) -> Tuple[int, int, int]:
    """Load conversation pages into *db_path*; return (loaded, added, total).

    *loaded*: rows parsed from the JSON files.
    *added*:  rows that were new or updated (INSERT OR REPLACE changed count).
    *total*:  rows in the table after the run.
    """
    validate_db_path(db_path)
    # Parse all input before touching the DB so a malformed file leaves it clean.
    rows = rows_from(json_paths)
    loaded = len(rows)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(SCHEMA)
        before = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
        conn.executemany(
            "INSERT OR REPLACE INTO conversations "
            "(id, title, category, source, started_at, created_at, updated_at, transcript, raw_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
        after = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
    finally:
        conn.close()

    new_rows = after - before
    return loaded, new_rows, after


if __name__ == "__main__":
    args = sys.argv[1:]
    if "-o" in args:
        idx = args.index("-o")
        db_path = args[idx + 1]
        json_paths = args[:idx] + args[idx + 2:]
    elif len(args) >= 2:
        db_path = args[-1]
        json_paths = args[:-1]
    else:
        sys.exit(
            "Usage: python conversations_to_sqlite.py conversations.json [more.json ...] -o conversations.db\n"
            "   or: python conversations_to_sqlite.py conversations.json conversations.db"
        )

    try:
        loaded, added, total = load(db_path, json_paths)
        print(f"Loaded {loaded} rows | New/updated: {added} | Total in DB: {total}")
    except (OSError, ValueError, json.JSONDecodeError):
        sys.exit("SQLite export failed")
