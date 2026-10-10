#!/usr/bin/env python3
"""
Convert Omi memories JSON exports to a SQLite database.

Usage:
    python memories_to_sqlite.py memories.sqlite memories.json [memories2.json ...]

Each run is idempotent: re-importing the same memory updates existing rows
(INSERT OR REPLACE keyed on id) and never duplicates them. The output path
must not contain '..', and an existing non-SQLite file is never overwritten.
"""

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

_SQLITE_MAGIC = b"SQLite format 3\x00"

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id              TEXT PRIMARY KEY,
    content         TEXT NOT NULL,
    category        TEXT,
    created_at      TEXT,
    updated_at      TEXT,
    manually_added  INTEGER NOT NULL DEFAULT 0,
    source          TEXT,
    conversation_id TEXT,
    raw_json        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS memories_category ON memories (category);
CREATE INDEX IF NOT EXISTS memories_created_at ON memories (created_at);
CREATE INDEX IF NOT EXISTS memories_manually_added ON memories (manually_added);
CREATE INDEX IF NOT EXISTS memories_conversation_id ON memories (conversation_id);
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


def text(value: Any) -> Optional[str]:
    """Store loosely typed API fields as text; anything non-null is coerced, not rejected."""
    if value is None:
        return None
    if isinstance(value, str):
        return strip_surrogates(value)
    if isinstance(value, (dict, list)):
        return strip_surrogates(json.dumps(value, ensure_ascii=False))
    return strip_surrogates(str(value))


def utc_stamp(value: Any) -> Optional[str]:
    """Normalise an ISO-8601 timestamp to UTC 'YYYY-MM-DD HH:MM:SS' so SQLite date functions work."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


TRUE_VALUES = {"true", "1", "yes", "t", "y"}


def boolean_to_int(value: Any) -> int:
    """Normalize boolean or truthy/falsy status to integer 0 or 1 for SQLite."""
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return 1 if value else 0
    if isinstance(value, str):
        return 1 if value.strip().lower() in TRUE_VALUES else 0
    return 0


def rows_from(source: str) -> List[Tuple]:
    """Parse one exported JSON file and return rows ready for INSERT."""
    content = Path(source).read_bytes().decode("utf-8-sig")
    items = json.loads(content)

    if isinstance(items, dict):
        # Match wrapper keys in documented precedence order
        for key in ("memories", "items", "data"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError(f"{source}: expected a JSON array or object containing memories")

    rows: List[Tuple] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source}: each memory must be an object")

        item_id = item.get("id")
        if item_id is None or str(item_id).strip() == "":
            raise ValueError(f"{source}: memory item is missing an id")

        content_val = item.get("content") or item.get("title") or item.get("text") or ""
        content_text = text(content_val) or ""

        category_val = item.get("category")
        created_at_val = item.get("created_at")
        updated_at_val = item.get("updated_at")
        manually_added_val = item.get("manually_added")
        source_val = item.get("source")
        conversation_id_val = item.get("conversation_id")

        rows.append((
            str(item_id),
            content_text,
            text(category_val),
            utc_stamp(created_at_val),
            utc_stamp(updated_at_val),
            boolean_to_int(manually_added_val),
            text(source_val),
            text(conversation_id_val),
            json.dumps(item, ensure_ascii=False),
        ))
    return rows


def load(database: str, sources: Sequence[str]) -> Tuple[int, int, int]:
    """Load memories from one or more JSON exports into a SQLite database."""
    validate_db_path(database)
    # Parse every file before opening the database, so a bad export changes nothing.
    rows: List[Tuple] = [row for source in sources for row in rows_from(source)]
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
    if len(sys.argv) < 3:
        sys.exit("Usage: python memories_to_sqlite.py DATABASE.sqlite INPUT.json [INPUT.json ...]")
    try:
        loaded, added, total = load(sys.argv[1], sys.argv[2:])
    except (OSError, ValueError, sqlite3.Error) as exc:
        sys.exit(f"SQLite load failed: {exc}")
    print(f"{loaded} row(s) loaded, {added} new, {loaded - added} updated, {total} memory item(s) in database")
