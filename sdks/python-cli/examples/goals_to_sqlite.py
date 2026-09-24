#!/usr/bin/env python3
"""
Convert Omi goal-list JSON exports to a SQLite database.

Usage:
    # From saved JSON files
    python goals_to_sqlite.py goals.sqlite goals_0.json [goals_1.json ...]

    # From stdin pipeline
    omi --json goal list --limit 200 | python goals_to_sqlite.py goals.sqlite -

Each run is idempotent: re-importing the same page updates existing rows
(INSERT OR REPLACE keyed on id) and never duplicates them.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA = """
CREATE TABLE IF NOT EXISTS goals (
    id                  TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    status              TEXT NOT NULL,
    goal_type           TEXT NOT NULL,
    current_value       REAL,
    target_value        REAL,
    min_value           REAL,
    unit                TEXT,
    progress_percentage REAL,
    created_at          TEXT,
    updated_at          TEXT,
    raw_json            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_goals_status ON goals (status);
CREATE INDEX IF NOT EXISTS idx_goals_type ON goals (goal_type);
CREATE INDEX IF NOT EXISTS idx_goals_created_at ON goals (created_at);
"""


def text(value: Any) -> Optional[str]:
    """Store loosely typed API fields as text; anything non-null is coerced, not rejected."""
    if value is None:
        return None
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def utc_stamp(value: Any) -> Optional[str]:
    """Normalise an ISO-8601 timestamp to UTC 'YYYY-MM-DD HH:MM:SS' text.

    Returns None for None/empty so SQLite NULL is used instead of a string,
    keeping date functions (strftime, julianday) working without coercion.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def normalize_status(item: Dict[str, Any]) -> str:
    """Normalize goal status to 'active', 'completed', or custom string."""
    raw_status = item.get("status")
    if isinstance(raw_status, str) and raw_status.strip():
        return raw_status.strip().lower()

    is_active = item.get("is_active")
    if is_active is not None:
        return "active" if bool(is_active) else "completed"

    return "active"


def compute_progress(item: Dict[str, Any], status: str) -> Optional[float]:
    """Compute normalized progress percentage (0.0 to 100.0) or None for qualitative goals."""
    goal_type = str(item.get("goal_type") or item.get("type") or "qualitative").lower()

    if status in ("completed", "archived", "done"):
        return 100.0

    if goal_type == "qualitative":
        return None

    if goal_type == "boolean":
        cur = float(item.get("current_value") or 0.0)
        target = float(item.get("target_value") or 1.0)
        return 100.0 if cur >= target else 0.0

    target = item.get("target_value")
    if target is None:
        target = item.get("max_value")

    if target is not None:
        try:
            target_f = float(target)
            cur_f = float(item.get("current_value") or 0.0)
            min_f = float(item.get("min_value") or 0.0)
            if target_f == min_f:
                return 100.0
            pct = ((cur_f - min_f) / (target_f - min_f)) * 100.0
            return max(0.0, min(100.0, round(pct, 2)))
        except (ValueError, TypeError, ZeroDivisionError):
            return None

    return None


def rows_from(source: str) -> List[Tuple[Any, ...]]:
    """Parse one input source (file path or '-' for stdin) into a list of tuples."""
    if source == "-":
        content = sys.stdin.read()
        display_name = "<stdin>"
    else:
        p = Path(source)
        if not p.is_file():
            raise FileNotFoundError(f"Input file not found: {source}")
        content = p.read_bytes().decode("utf-8-sig")
        display_name = source

    try:
        items = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{display_name}: invalid JSON ({exc})") from exc

    if isinstance(items, dict):
        items = (
            items.get("goals")
            or items.get("items")
            or items.get("data")
            or [items]
        )

    if not isinstance(items, list):
        raise ValueError(f"{display_name}: expected a JSON array or object containing goals")

    rows: List[Tuple[Any, ...]] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"{display_name}[{idx}]: each goal must be a JSON object")
        item_id = item.get("id")
        if item_id is None or str(item_id).strip() == "":
            raise ValueError(f"{display_name}[{idx}]: goal is missing an id")

        title = text(item.get("title") or item.get("text") or item.get("description") or "(untitled goal)")
        status = normalize_status(item)
        goal_type = text(item.get("goal_type") or item.get("type") or "qualitative") or "qualitative"

        def to_float(val: Any) -> Optional[float]:
            if val is None:
                return None
            try:
                return float(val)
            except (ValueError, TypeError):
                return None

        current_val = to_float(item.get("current_value"))
        target_val = to_float(item.get("target_value") if item.get("target_value") is not None else item.get("max_value"))
        min_val = to_float(item.get("min_value"))
        unit = text(item.get("unit"))
        progress_pct = compute_progress(item, status)

        created_at = utc_stamp(item.get("created_at"))
        updated_at = utc_stamp(item.get("updated_at"))
        raw_json = json.dumps(item, ensure_ascii=False)

        rows.append((
            str(item_id),
            title,
            status,
            goal_type,
            current_val,
            target_val,
            min_val,
            unit,
            progress_pct,
            created_at,
            updated_at,
            raw_json,
        ))

    return rows


def load(database: str, sources: List[str]) -> Tuple[int, int, int]:
    """Load goals from one or more JSON exports into a SQLite database.

    Returns:
        (loaded_count, added_count, total_count)
    """
    # Parse every file before touching the database so corrupt exports leave DB intact.
    rows: List[Tuple[Any, ...]] = []
    for src in sources:
        rows.extend(rows_from(src))

    conn = sqlite3.connect(database)
    try:
        conn.executescript(SCHEMA)
        before = conn.execute("SELECT COUNT(*) FROM goals").fetchone()[0]
        with conn:
            conn.executemany(
                "INSERT OR REPLACE INTO goals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        after = conn.execute("SELECT COUNT(*) FROM goals").fetchone()[0]
    finally:
        conn.close()

    return len(rows), after - before, after


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit("Usage: python goals_to_sqlite.py DATABASE.sqlite INPUT.json [INPUT.json ...]")

    db_path = sys.argv[1]
    sources = sys.argv[2:]

    try:
        loaded, added, total = load(db_path, sources)
    except (OSError, ValueError, sqlite3.Error) as exc:
        sys.exit(f"SQLite load failed: {exc}")

    print(f"{loaded} row(s) loaded, {added} new, {loaded - added} updated, {total} goal(s) in database")


if __name__ == "__main__":
    main()
