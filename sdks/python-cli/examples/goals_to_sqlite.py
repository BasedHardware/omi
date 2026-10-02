#!/usr/bin/env python3
"""Convert Omi goal JSON exports into a structured SQLite database."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple
import uuid

_SQLITE_MAGIC = b"SQLite format 3\x00"

SCHEMA = """
CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    goal_type TEXT,
    current_value REAL,
    target_value REAL,
    min_value REAL,
    max_value REAL,
    unit TEXT,
    is_active INTEGER NOT NULL,
    is_completed INTEGER NOT NULL,
    progress_pct REAL,
    created_at TEXT,
    updated_at TEXT,
    raw_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS goals_is_active ON goals (is_active);
CREATE INDEX IF NOT EXISTS goals_is_completed ON goals (is_completed);
CREATE INDEX IF NOT EXISTS goals_goal_type ON goals (goal_type);
CREATE INDEX IF NOT EXISTS goals_created_at ON goals (created_at);
"""


def validate_db_path(db_path: str) -> None:
    """Raise ValueError if db_path is unsafe, a symlink, or points at a non-SQLite file."""
    p = Path(db_path)
    if ".." in p.parts:
        raise ValueError(
            f"Output path {db_path!r} contains '..'; refusing to write outside the intended directory."
        )
    if p.is_symlink():
        raise ValueError(
            f"Output path {db_path!r} is a symlink; refusing to write through symlinks."
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


def text(value: Any) -> Optional[str]:
    """Store loosely typed API fields as clean safe text; non-null is coerced."""
    if value is None:
        return None
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    collapsed = " ".join(value.split())
    clean = "".join(
        ch for ch in collapsed
        if (ch >= " " or ch in "\n\t") and not ("\ud800" <= ch <= "\udfff") and ch not in ("\ufffe", "\uffff")
    )
    return clean if clean else None


def utc_stamp(value: Any) -> Optional[str]:
    """Normalize an ISO-8601 timestamp to UTC 'YYYY-MM-DD HH:MM:SS' for SQLite."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    else:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def parse_float(value: Any) -> Optional[float]:
    """Parse a float value safely, rejecting non-finite numbers and handling overflow."""
    if value is None:
        return None
    try:
        val = float(value)
        if not math.isfinite(val):
            return None
        return val
    except (ValueError, TypeError, OverflowError):
        return None


def normalize_bool_flag(value: Any) -> Optional[bool]:
    """Normalize boolean flags, integer flags, and string aliases safely."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    s = str(value).strip().lower()
    if s in ("true", "1", "yes"):
        return True
    if s in ("false", "0", "no"):
        return False
    return None


def derive_status(goal: Dict[str, Any]) -> Tuple[int, int]:
    """Derive (is_active_int, is_completed_int) with strict inactive precedence."""
    active_flag = normalize_bool_flag(goal.get("is_active"))
    if active_flag is False:
        return 0, 0

    achieved_flag = normalize_bool_flag(goal.get("is_achieved"))
    completed_flag = normalize_bool_flag(goal.get("is_completed"))
    if achieved_flag is True or completed_flag is True:
        return 1, 1
    if achieved_flag is False or completed_flag is False:
        return 1, 0

    # For goals with no explicit achievement flag, derive completion from target or boolean state
    goal_type = str(goal.get("goal_type") or "").strip().lower()
    if goal_type == "boolean":
        c = parse_float(goal.get("current_value"))
        if c is not None and c >= 1.0:
            return 1, 1
        return 1, 0

    curr = parse_float(goal.get("current_value"))
    target = parse_float(goal.get("target_value"))
    min_v = parse_float(goal.get("min_value"))
    max_v = parse_float(goal.get("max_value"))
    base = min_v if min_v is not None else 0.0
    denom = None
    if target is not None and target != base:
        denom = target - base
    elif max_v is not None and max_v != base:
        denom = max_v - base

    if curr is not None and denom is not None and denom > 0:
        if (curr - base) >= denom:
            return 1, 1

    if target == 0.0 and curr == 0.0:
        return 1, 1

    return 1, 0


def calc_progress_pct(goal: Dict[str, Any], is_completed: int) -> Optional[float]:
    """Calculate progress percentage (0.0 to 100.0+) or None if qualitative and uncompleted."""
    if is_completed == 1:
        return 100.0

    goal_type = str(goal.get("goal_type") or "").strip().lower()
    if goal_type == "boolean":
        c = parse_float(goal.get("current_value"))
        return 100.0 if (c is not None and c >= 1.0) else 0.0

    curr = parse_float(goal.get("current_value"))
    target = parse_float(goal.get("target_value"))
    min_v = parse_float(goal.get("min_value"))
    max_v = parse_float(goal.get("max_value"))

    if curr is None:
        return None

    base = min_v if min_v is not None else 0.0
    denom = None
    if target is not None and target != base:
        denom = target - base
    elif max_v is not None and max_v != base:
        denom = max_v - base

    if denom is not None and denom > 0:
        pct = round(((curr - base) / denom) * 100.0, 2)
        return pct

    if target == 0.0 and curr == 0.0:
        return 100.0

    return None


def rows_from(source: str) -> List[Tuple[Any, ...]]:
    """Parse goal items from a JSON file or stdin ('-') into SQLite row tuples."""
    source_label = "stdin" if source == "-" else source
    if source == "-":
        content = sys.stdin.buffer.read()
    else:
        path = Path(source)
        if not path.is_file():
            raise FileNotFoundError(f"Input file not found: {source}")
        content = path.read_bytes()

    if not content.strip():
        return []

    raw = json.loads(content.decode("utf-8-sig"))
    if isinstance(raw, dict):
        for key in ("goals", "items", "data", "results"):
            candidate = raw.get(key)
            if isinstance(candidate, list):
                raw = candidate
                break
        else:
            raw = [raw]

    if not isinstance(raw, list):
        raise ValueError(f"{source_label}: expected a JSON array or object containing goals")

    rows: List[Tuple[Any, ...]] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"{source_label} item {idx}: each goal must be an object")

        raw_id = item.get("id")
        clean_id = text(raw_id)
        if clean_id is None:
            stable_sig = hashlib.sha256(
                json.dumps(item, sort_keys=True, ensure_ascii=True).encode("utf-8")
            ).hexdigest()[:16]
            clean_id = f"gen_{stable_sig}"

        raw_title = item.get("title")
        clean_title = text(raw_title)
        if clean_title is None:
            clean_title = "(untitled goal)"

        goal_type = text(item.get("goal_type"))
        current_v = parse_float(item.get("current_value"))
        target_v = parse_float(item.get("target_value"))
        min_v = parse_float(item.get("min_value"))
        max_v = parse_float(item.get("max_value"))
        unit_val = text(item.get("unit"))

        is_act, is_comp = derive_status(item)
        progress = calc_progress_pct(item, is_comp)

        created = utc_stamp(item.get("created_at"))
        updated = utc_stamp(item.get("updated_at"))
        raw_json_str = json.dumps(item, ensure_ascii=True)

        rows.append((
            clean_id,
            clean_title,
            goal_type,
            current_v,
            target_v,
            min_v,
            max_v,
            unit_val,
            is_act,
            is_comp,
            progress,
            created,
            updated,
            raw_json_str,
        ))
    return rows


def load(database: str, sources: Sequence[str]) -> Tuple[int, int, int]:
    """Load goals from one or more JSON exports into a SQLite database."""
    validate_db_path(database)
    rows = [row for source in sources for row in rows_from(source)]

    dest_path = Path(database)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database)
    try:
        connection.executescript(SCHEMA)
        before = connection.execute("SELECT COUNT(*) FROM goals").fetchone()[0]
        with connection:
            connection.executemany(
                "INSERT OR REPLACE INTO goals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
        after = connection.execute("SELECT COUNT(*) FROM goals").fetchone()[0]
    finally:
        connection.close()

    return len(rows), after - before, after


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if len(argv) < 2:
        print("Usage: python goals_to_sqlite.py DATABASE.sqlite INPUT.json [INPUT.json ...]", file=sys.stderr)
        return 1

    database = argv[0]
    sources = argv[1:]

    try:
        loaded, added, total = load(database, sources)
    except (OSError, ValueError, sqlite3.Error) as exc:
        sys.exit(f"SQLite load failed: {exc}")

    print(f"{loaded} row(s) loaded, {added} new, {loaded - added} updated, {total} goal(s) in database")
    return 0


if __name__ == "__main__":
    sys.exit(main())
