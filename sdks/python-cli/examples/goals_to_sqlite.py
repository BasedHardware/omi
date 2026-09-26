"""
Convert Omi goals JSON exports into a local SQLite database for analytics, queries, and archival.

Usage:
  python goals_to_sqlite.py goals.json goals.db
  omi --json goal list --limit 100 --include-inactive | python goals_to_sqlite.py - goals.db
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


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

CREATE INDEX IF NOT EXISTS idx_goals_is_active ON goals(is_active);
CREATE INDEX IF NOT EXISTS idx_goals_goal_type ON goals(goal_type);
"""


def parse_numeric(val: Any) -> Optional[float]:
    """Safely parse a numerical metric or return None."""
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def normalize_timestamp(val: Any) -> Optional[str]:
    """Normalize timestamp values to UTC YYYY-MM-DD HH:MM:SS string."""
    if not val:
        return None
    if isinstance(val, (int, float)):
        try:
            dt = datetime.fromtimestamp(val, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return None
    if isinstance(val, str):
        val = val.strip()
        # Handle ISO-8601 with trailing Z or timezone offsets
        try:
            clean_str = val.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return val
    return None


def init_db(conn: sqlite3.Connection) -> None:
    """Initialize SQLite database schema and enable WAL mode for performance."""
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript(SCHEMA)


def upsert_goals(conn: sqlite3.Connection, goals: List[Dict[str, Any]]) -> int:
    """Insert or update goal records atomically in a single transaction."""
    if not goals:
        return 0

    records = []
    for g in goals:
        if not isinstance(g, dict):
            continue
        goal_id = str(g.get("id") or "").strip()
        if not goal_id:
            continue

        title = str(g.get("title") or "Untitled Goal")
        goal_type = g.get("goal_type")
        target_value = parse_numeric(g.get("target_value"))
        current_value = parse_numeric(g.get("current_value"))
        min_value = parse_numeric(g.get("min_value"))
        max_value = parse_numeric(g.get("max_value"))
        unit = g.get("unit")
        is_active = 1 if g.get("is_active", True) else 0

        created_at = normalize_timestamp(g.get("created_at"))
        updated_at = normalize_timestamp(g.get("updated_at") or g.get("created_at"))
        raw_json = json.dumps(g, ensure_ascii=False)

        records.append(
            (
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
        )

    with conn:
        conn.executemany(
            """
            INSERT OR REPLACE INTO goals (
                id, title, goal_type, target_value, current_value,
                min_value, max_value, unit, is_active,
                created_at, updated_at, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            records,
        )

    return len(records)


def export_goals_to_sqlite(
    source: Union[str, Path, List[Dict[str, Any]]],
    db_path: Union[str, Path],
) -> int:
    """Read goals from a JSON file, stdin, or list of dicts, and write them into SQLite."""
    if isinstance(source, list):
        items = source
    elif str(source) == "-":
        raw_text = sys.stdin.read()
        items = json.loads(raw_text) if raw_text.strip() else []
    else:
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {path}")
        items = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(items, list):
        if isinstance(items, dict) and "goals" in items:
            items = items["goals"]
        elif isinstance(items, dict):
            items = [items]
        else:
            raise ValueError("Expected a JSON array of goal objects")

    conn = sqlite3.connect(str(db_path))
    try:
        init_db(conn)
        count = upsert_goals(conn, items)
        return count
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi goal exports to an indexed SQLite database."
    )
    parser.add_argument(
        "input",
        help="Path to JSON file containing goals, or '-' to read from stdin.",
    )
    parser.add_argument(
        "output",
        help="Path to the destination SQLite database (e.g., goals.db).",
    )

    args = parser.parse_args()

    try:
        count = export_goals_to_sqlite(args.input, args.output)
        print(f"Successfully exported {count} goal(s) to '{args.output}'.")
    except Exception as exc:
        sys.exit(f"Error: {exc}")


if __name__ == "__main__":
    main()
