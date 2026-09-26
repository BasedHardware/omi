#!/usr/bin/env python3
"""Convert Omi goal JSON exports into a local SQLite database."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    goal_type TEXT,
    target_value REAL,
    current_value REAL,
    min_value REAL,
    max_value REAL,
    unit TEXT,
    is_active INTEGER NOT NULL,
    created_at TEXT,
    updated_at TEXT,
    raw_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS goals_goal_type ON goals (goal_type);
CREATE INDEX IF NOT EXISTS goals_is_active ON goals (is_active);
CREATE INDEX IF NOT EXISTS goals_created_at ON goals (created_at);
"""


def text(value: Any) -> str | None:
    """Store loosely typed API fields as stripped text; non-null coerced, not rejected."""
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value).strip()


def to_float(value: Any) -> float | None:
    """Safely coerce numerical metric fields to float, returning None for missing/invalid values."""
    if value is None:
        return None
    try:
        val = float(value)
        return val if sys.float_info.min <= abs(val) <= sys.float_info.max or val == 0.0 else None
    except (ValueError, TypeError, OverflowError):
        return None


def boolean_to_int(value: Any) -> int:
    """Normalize boolean or string flag to SQLite integer boolean (0 or 1)."""
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return 1 if bool(value) else 0
    if isinstance(value, str):
        return 1 if value.strip().lower() in ("true", "1", "yes", "active") else 0
    return 0


def utc_stamp(value: Any) -> str | None:
    """Normalize an ISO-8601 timestamp to UTC 'YYYY-MM-DD HH:MM:SS' for SQLite date functions."""
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def parse_datetime(value: Any) -> datetime | None:
    """Helper to parse timestamps for ordering and freshness comparison."""
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def row_from_goal(item: dict[str, Any]) -> tuple[Any, ...]:
    """Extract a typed database row from a goal dictionary."""
    goal_id = text(item.get("id"))
    title = text(item.get("title")) or "(untitled goal)"
    goal_type = text(item.get("goal_type"))
    target_value = to_float(item.get("target_value"))
    current_value = to_float(item.get("current_value"))
    min_value = to_float(item.get("min_value"))
    max_value = to_float(item.get("max_value"))
    unit = text(item.get("unit"))
    is_active = boolean_to_int(item.get("is_active", True))
    created_at = utc_stamp(item.get("created_at"))
    updated_at = utc_stamp(item.get("updated_at"))
    raw_json = json.dumps(item, ensure_ascii=False)

    return (
        goal_id,
        title,
        goal_type,
        target_value,
        current_value,
        min_value,
        max_value,
        unit,
        is_active,
        created_at,
        updated_at,
        raw_json,
    )


def rows_from(source_path: str | Path) -> list[dict[str, Any]]:
    """Read a JSON export file, validating array or wrapped object structure."""
    path = Path(source_path)
    content = path.read_bytes().decode("utf-8-sig")
    data = json.loads(content)
    if isinstance(data, dict):
        raw = data.get("goals") or data.get("items") or data.get("data") or [data]
    else:
        raw = data
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected JSON array or wrapped object containing goals")
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"{path}: each goal entry must be a JSON object")
        if not item.get("id"):
            raise ValueError(f"{path}: goal entry missing required 'id' attribute")
    return raw


def load(db_path: str | Path, sources: Iterable[str | Path]) -> tuple[int, int, int]:
    """Load goals from one or more export files into SQLite atomically.

    Returns:
        tuple of (total_rows_loaded, new_rows_inserted, total_rows_in_db)
    """
    items_by_id: dict[str, dict[str, Any]] = {}
    for source in sources:
        for item in rows_from(source):
            clean_id = str(item["id"]).strip()
            existing = items_by_id.get(clean_id)
            if existing is not None:
                new_updated = parse_datetime(item.get("updated_at") or item.get("created_at"))
                existing_updated = parse_datetime(existing.get("updated_at") or existing.get("created_at"))
                if new_updated and existing_updated:
                    if new_updated > existing_updated:
                        items_by_id[clean_id] = item
                elif new_updated and not existing_updated:
                    items_by_id[clean_id] = item
            else:
                items_by_id[clean_id] = item

    rows = [row_from_goal(item) for item in items_by_id.values()]

    connection = sqlite3.connect(str(db_path))
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript(SCHEMA)
        before = connection.execute("SELECT COUNT(*) FROM goals").fetchone()[0]
        with connection:  # One transaction: all rows commit, or none do
            connection.executemany(
                "INSERT OR REPLACE INTO goals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        after = connection.execute("SELECT COUNT(*) FROM goals").fetchone()[0]
    finally:
        connection.close()

    return len(rows), after - before, after


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("Usage: python goals_to_sqlite.py DATABASE.sqlite INPUT.json [INPUT.json ...]")
    try:
        loaded, added, total = load(sys.argv[1], sys.argv[2:])
    except (OSError, ValueError, sqlite3.Error) as exc:
        sys.exit(f"SQLite load failed: {exc}")
    print(f"{loaded} row(s) loaded, {added} new, {loaded - added} updated, {total} goal(s) in database")
