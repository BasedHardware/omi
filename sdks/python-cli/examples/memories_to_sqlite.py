#!/usr/bin/env python3
"""
Convert Omi memory-list JSON export to a SQLite database.

Complements memories_to_csv.py and memories_to_markdown.py with a queryable
SQLite export. Each run is idempotent: re-importing the same page updates
existing rows (INSERT OR REPLACE keyed on id) and never duplicates them. The
output path must not contain '..', and an existing non-SQLite file is never
overwritten.
"""

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

SCHEMA: str = """
CREATE TABLE IF NOT EXISTS memories (
    id         TEXT PRIMARY KEY,
    content    TEXT,
    category   TEXT,
    visibility TEXT,
    tags       TEXT,
    created_at TEXT,
    raw_json   TEXT NOT NULL
);
"""


def utc_stamp(value: Any) -> Optional[str]:
    """Normalise an ISO-8601 timestamp to UTC 'YYYY-MM-DD HH:MM:SS' text.

    Returns None for None/empty so SQLite NULL is used instead of a string,
    keeping date functions (strftime, julianday) working without coercion.
    A non-string or unparseable value is stored as text rather than dropped, so
    the original value stays queryable.
    """
    if value is None or value == "":
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError, TypeError):
        return text(value)


def strip_surrogates(value: str) -> str:
    """Drop unpaired surrogate code points that cannot be encoded as UTF-8.

    json.loads accepts lone surrogates (e.g. "\\ud800") from a malformed export,
    but both sqlite3 and file writes raise UnicodeEncodeError on them. Dropping
    them keeps the remaining text and lets the row import.
    """
    return value.encode("utf-8", "ignore").decode("utf-8")


def text(value: Optional[Any]) -> Optional[str]:
    """Coerce a loosely typed API field to storable text.

    The dev API is loosely typed, so content/category/visibility can arrive as a
    dict or list. sqlite3 refuses to bind those ("type 'dict' is not supported"),
    which would abort the whole import over one bad field, so anything non-null
    is coerced rather than rejected. Returns None for None so SQLite NULL is
    used.
    """
    if value is None:
        return None
    if isinstance(value, dict) or isinstance(value, list):
        value = json.dumps(value, ensure_ascii=False)
    elif not isinstance(value, str):
        value = str(value)
    return strip_surrogates(value)


def tags_str(item: dict) -> str:
    """Render the tags field as a semicolon-joined string for storage.

    The tags field is a list in the API; a semicolon-joined string keeps it
    searchable with LIKE while remaining simple to split on read.
    """
    tags = item.get("tags")
    if isinstance(tags, list):
        return ";".join(str(t) for t in tags if t)
    return ""


def extract_items(data: Any) -> List[dict]:
    """Unwrap memory records from bare arrays, wrapped envelopes, or single objects."""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("memories", "items", "data"):
            val = data.get(key)
            if isinstance(val, list):
                return [item for item in val if isinstance(item, dict)]
        if any(key in data for key in ("content", "category", "id", "created_at")):
            return [data]
        return []
    return []


def rows_from(pages: Sequence[str]) -> List[Tuple]:
    """Parse one or more exported JSON pages and return rows ready for INSERT."""
    rows: List[Tuple] = []
    for path in pages:
        raw = Path(path).read_text(encoding="utf-8").lstrip("\ufeff")
        items = extract_items(json.loads(raw))
        for item in items:
            mem_id = item.get("id")
            if not mem_id:
                raise ValueError(f"{path}: memory missing required 'id' field")
            rows.append(
                (
                    strip_surrogates(str(mem_id)),
                    text(item.get("content")),
                    text(item.get("category")),
                    text(item.get("visibility")),
                    strip_surrogates(tags_str(item)),
                    utc_stamp(item.get("created_at")),
                    strip_surrogates(json.dumps(item, ensure_ascii=False)),
                )
            )
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
        conn.execute(SCHEMA)
        before = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        conn.executemany(
            "INSERT OR REPLACE INTO memories "
            "(id, content, category, visibility, tags, created_at, raw_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
        after = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    finally:
        conn.close()

    new_rows = after - before
    return loaded, new_rows, after


if __name__ == "__main__":
    args = sys.argv[1:]
    if "-o" in args:
        idx = args.index("-o")
        db_path = args[idx + 1]
        json_paths = args[:idx] + args[idx + 2 :]
    elif len(args) >= 2:
        db_path = args[-1]
        json_paths = args[:-1]
    else:
        sys.exit(
            "Usage: python memories_to_sqlite.py memories.json [more.json ...] -o memories.db\n"
            "   or: python memories_to_sqlite.py memories.json memories.db"
        )

    try:
        loaded, added, total = load(db_path, json_paths)
        print(f"Loaded {loaded} rows | New/updated: {added} | Total in DB: {total}")
    except (OSError, ValueError, json.JSONDecodeError):
        sys.exit("SQLite export failed")
