#!/usr/bin/env python3
"""Convert Omi memories JSON export to a SQLite database.

Usage:
    python memories_to_sqlite.py memories.json [memories2.json ...] -o memories.db
    omi --json memory list | python memories_to_sqlite.py - -o memories.db

Each run is idempotent: re-importing updates existing rows (INSERT OR REPLACE
keyed on id) and never duplicates them. The output path must not contain '..',
and an existing non-SQLite file is never overwritten.
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

_SQLITE_MAGIC = b"SQLite format 3\x00"

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id            TEXT PRIMARY KEY,
    content       TEXT NOT NULL,
    category      TEXT,
    visibility    TEXT,
    tags          TEXT,
    created_at    TEXT,
    updated_at    TEXT,
    raw_json      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS memories_category ON memories (category);
CREATE INDEX IF NOT EXISTS memories_created_at ON memories (created_at);
"""


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


def strip_surrogates(value: str) -> str:
    """Drop unpaired surrogate code points that cannot be encoded as UTF-8."""
    return value.encode("utf-8", "ignore").decode("utf-8")


def text(value: Optional[Any]) -> Optional[str]:
    """Coerce a loosely typed API field to storable text."""
    if value is None:
        return None
    if isinstance(value, str):
        return strip_surrogates(value)
    if isinstance(value, (dict, list)):
        return strip_surrogates(json.dumps(value, ensure_ascii=False))
    return strip_surrogates(str(value))


def format_tags(tags: Any) -> Optional[str]:
    """Format tags as comma-separated text or None."""
    if tags is None:
        return None
    if isinstance(tags, list):
        clean_tags = [str(t).strip() for t in tags if t]
        return ", ".join(clean_tags) if clean_tags else None
    return text(tags)


def utc_stamp(value: Any) -> Optional[str]:
    """Normalise an ISO-8601 timestamp to UTC 'YYYY-MM-DD HH:MM:SS' text."""
    if value is None or value == "":
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError, TypeError):
        return text(value)


def parse_memory(item: dict) -> Tuple[str, str, Optional[str], Optional[str], Optional[str], Optional[str], Optional[str], str]:
    """Extract and validate row values for a single memory item."""
    if not isinstance(item, dict):
        raise ValueError("Each memory item must be an object")

    raw_id = item.get("id")
    if not raw_id:
        raise ValueError("Memory item missing required 'id' field")
    mem_id = strip_surrogates(str(raw_id))

    content = item.get("content") or item.get("text") or ""
    content_str = strip_surrogates(str(content).strip())
    if not content_str:
        content_str = "(empty memory)"

    category = text(item.get("category"))
    visibility = text(item.get("visibility"))
    tags = format_tags(item.get("tags"))
    created_at = utc_stamp(item.get("created_at"))
    updated_at = utc_stamp(item.get("updated_at"))
    raw_json = strip_surrogates(json.dumps(item, ensure_ascii=False))

    return (mem_id, content_str, category, visibility, tags, created_at, updated_at, raw_json)


def load_input_data(source: str) -> List[dict]:
    """Load JSON from a file path or stdin ('-')."""
    if source == "-":
        raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
    else:
        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError(f"Input file not found: {source}")
        raw = path.read_bytes().decode("utf-8-sig", errors="replace")

    data = json.loads(raw)
    if isinstance(data, dict):
        for key in ("memories", "data", "items"):
            if isinstance(data.get(key), list):
                return data[key]
        raise ValueError("Expected a list of memories or an object with 'memories'/'data' array")
    if isinstance(data, list):
        return data
    raise ValueError("Expected a JSON array of memories")


def import_memories(sources: Sequence[str], db_path: str) -> int:
    """Import memories from one or more JSON sources into a SQLite database."""
    validate_db_path(db_path)

    all_items: List[dict] = []
    for src in sources:
        all_items.extend(load_input_data(src))

    rows = [parse_memory(item) for item in all_items]

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.executemany(
            """
            INSERT OR REPLACE INTO memories (
                id, content, category, visibility, tags, created_at, updated_at, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()

    return len(rows)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi memories JSON export to a SQLite database."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="One or more JSON input files, or '-' for stdin",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Path to output SQLite database (.db)",
    )

    args = parser.parse_args(argv)

    try:
        count = import_memories(args.inputs, args.output)
        print(f"Imported {count} memor{'y' if count == 1 else 'ies'} into {args.output}")
    except (ValueError, FileNotFoundError, OSError) as exc:
        sys.exit(f"Error: {exc}")


if __name__ == "__main__":
    main()
