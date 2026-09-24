#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
Convert OMI memory JSON export to SQLite.

Reads one or more JSON exports from `omi --json memory list` and imports them
into a local SQLite database. Normalises timestamps to UTC text for date functions,
indexes category and created_at for fast queries, and preserves raw JSON.

Usage:
    python memories_to_sqlite.py memories.sqlite memories_0.json [memories_1.json ...]
"""

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
    created_at TEXT,
    updated_at TEXT,
    manually_added INTEGER NOT NULL,
    raw_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS memories_category ON memories (category);
CREATE INDEX IF NOT EXISTS memories_created_at ON memories (created_at);
CREATE INDEX IF NOT EXISTS memories_manually_added ON memories (manually_added);
"""


def text(value):
    """Store loosely typed API fields as text; anything non-null is coerced, not rejected."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)


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


def boolean_to_int(value):
    """Normalize boolean status to integer 0 or 1 for SQLite."""
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return 1 if value else 0
    if isinstance(value, str):
        return 1 if value.strip().lower() in ("true", "1", "yes") else 0
    return 0


def rows_from(source):
    """Read a JSON file or stdin and produce rows ready for INSERT."""
    if str(source) == "-":
        content = sys.stdin.read()
    else:
        content = Path(source).read_bytes().decode("utf-8-sig")

    if not content.strip():
        raise ValueError(f"{source}: empty JSON input")

    items = json.loads(content)
    if isinstance(items, dict):
        items = (
            items.get("memories")
            or items.get("items")
            or items.get("data")
            or [items]
        )
    if not isinstance(items, list):
        raise ValueError(f"{source}: expected a JSON array or object containing memories")

    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source}: each memory must be an object")
        item_id = item.get("id")
        if item_id is None or str(item_id).strip() == "":
            raise ValueError(f"{source}: memory item is missing an id")

        content_val = item.get("content") or item.get("text") or ""
        rows.append((
            str(item_id),
            text(content_val),
            text(item.get("category")),
            utc_stamp(item.get("created_at")),
            utc_stamp(item.get("updated_at")),
            boolean_to_int(item.get("manually_added")),
            json.dumps(item, ensure_ascii=False),
        ))
    return rows


def load(database, sources):
    """Load memories from one or more JSON exports into a SQLite database."""
    # Parse every file before opening the database, so a bad export changes nothing.
    rows = [row for source in sources for row in rows_from(source)]
    connection = sqlite3.connect(database)
    try:
        connection.executescript(SCHEMA)
        before = connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        with connection:  # one transaction: all rows land, or none do
            connection.executemany(
                "INSERT OR REPLACE INTO memories VALUES (?, ?, ?, ?, ?, ?, ?)",
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
