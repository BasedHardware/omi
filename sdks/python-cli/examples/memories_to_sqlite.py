#!/usr/bin/env python3
"""
Convert Omi memories JSON export to a SQLite database.

Usage:
    python memories_to_sqlite.py memories.json [memories2.json ...] -o memories.db
    omi --json memory list | python memories_to_sqlite.py - -o memories.db

Each run is idempotent: re-importing the same memory updates existing rows
(INSERT OR REPLACE keyed on id) and never duplicates them. The output path
must not contain '..', and an existing non-SQLite file is never overwritten.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

SCHEMA: str = """
CREATE TABLE IF NOT EXISTS memories (
    id            TEXT PRIMARY KEY,
    content       TEXT,
    category      TEXT,
    visibility    TEXT,
    tags          TEXT,
    created_at    TEXT,
    updated_at    TEXT,
    raw_json      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at);
"""


def utc_stamp(value: Optional[str]) -> Optional[str]:
    """Normalise an ISO-8601 timestamp to UTC 'YYYY-MM-DD HH:MM:SS' text.

    Returns None for None/empty so SQLite NULL is used instead of a string,
    keeping date functions (strftime, julianday) working without coercion.
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        return str(value)


def parse_tags(tags: Any) -> Optional[str]:
    """Serialize tags list or set to comma-separated string, or return as string."""
    if not tags:
        return None
    if isinstance(tags, (list, tuple, set)):
        return ",".join(str(t).strip() for t in tags if t)
    return str(tags)


def rows_from(pages: Sequence[str]) -> List[Tuple]:
    """Parse one or more exported JSON pages and return rows ready for INSERT."""
    rows: List[Tuple] = []
    for path in pages:
        if path == "-":
            raw = sys.stdin.read().lstrip("\ufeff")
            path_label = "<stdin>"
        else:
            raw = Path(path).read_text(encoding="utf-8").lstrip("\ufeff")
            path_label = path

        items = json.loads(raw)
        # Support both bare array and wrapped {"memories": [...]} shape
        if isinstance(items, dict):
            for key in ("memories", "items", "data"):
                if isinstance(items.get(key), list):
                    items = items[key]
                    break
        if not isinstance(items, list):
            raise ValueError(f"{path_label}: expected a JSON array or wrapped object")

        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"{path_label}: each memory must be a JSON object")
            mem_id = item.get("id")
            if not mem_id:
                raise ValueError(f"{path_label}: memory missing required 'id' field")

            content = item.get("content") or item.get("description") or ""
            category = item.get("category")
            visibility = item.get("visibility")
            tags = parse_tags(item.get("tags"))
            created_at = utc_stamp(item.get("created_at"))
            updated_at = utc_stamp(item.get("updated_at"))
            raw_json = json.dumps(item, ensure_ascii=False)

            rows.append((
                str(mem_id),
                content,
                category,
                visibility,
                tags,
                created_at,
                updated_at,
                raw_json,
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
    """Load memory pages into *db_path*; return (loaded, added, total).

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
        conn.executescript(SCHEMA)
        before = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        conn.executemany(
            "INSERT OR REPLACE INTO memories "
            "(id, content, category, visibility, tags, created_at, updated_at, raw_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
        after = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        added = after - before
        return loaded, added, after
    finally:
        conn.close()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi memories JSON exports into a SQLite database."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        metavar="JSON_FILE",
        help="One or more JSON files (or '-' for stdin) containing memory records.",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        metavar="DB_FILE",
        help="Path to the output SQLite database file.",
    )

    args = parser.parse_args(argv)
    try:
        loaded, added, total = load(args.output, args.inputs)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Imported {loaded} memories into {args.output} (total rows: {total}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
