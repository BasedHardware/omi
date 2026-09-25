#!/usr/bin/env python3
"""Convert Omi Desktop local tasks JSON or search exports into a relational SQLite database.

Usage:
    # From direct Desktop SQL export:
    omi --json local sql "SELECT id, title, description, completed, created_at, updated_at, due_at, category FROM tasks" | python local_tasks_to_sqlite.py - -o tasks.db

    # From semantic task search export (up to 10 top results):
    omi --json local task search "meeting" --include-completed | python local_tasks_to_sqlite.py - -o tasks.db

    # From a saved tasks JSON or search text export:
    python local_tasks_to_sqlite.py tasks.json -o tasks.db

    # Re-running updates or merges new tasks without duplicating existing IDs:
    python local_tasks_to_sqlite.py day1.json day2.json -o tasks.db

Converts local task exports into indexed SQLite tables:
    - local_tasks: structured columns (id, title, description, completed, created_at, updated_at, due_at, category, raw_json)
    - Indexes on completed status, due_at date, and category for fast SQL queries.

Key features:
    - Pure Python 3.10+ standard library (zero external dependencies).
    - Multi-format ingestion: parses structured JSON arrays, SQL rows, and CLI prose checklist search outputs.
    - Idempotent upsert: merges multiple runs or exports using primary key (id).
    - Stable hash ID fallback for exports lacking explicit IDs to prevent collision across imports.
    - Streaming standard input (-) for seamless UNIX CLI piping.
    - Safe overwrite guard (--force required to overwrite existing DB).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


SCHEMA = """
CREATE TABLE IF NOT EXISTS local_tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    completed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT,
    updated_at TEXT,
    due_at TEXT,
    category TEXT,
    raw_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_local_tasks_completed ON local_tasks(completed);
CREATE INDEX IF NOT EXISTS idx_local_tasks_due_at ON local_tasks(due_at);
CREATE INDEX IF NOT EXISTS idx_local_tasks_category ON local_tasks(category);
"""

PROSE_TASK_RE = re.compile(r"^\s*(?:[-*]|\d+[\.\)])?\s*\[([ xX])\]\s*(.*?)(?:\s*\((.*?)\))?\s*$")


def parse_prose_line(line: str, idx: int) -> Optional[Dict[str, Any]]:
    """Parse a single prose task line (e.g. '1. [x] Task name (similarity: 0.9, id: abc)')."""
    line = line.strip()
    if not line:
        return None
    match = PROSE_TASK_RE.match(line)
    if not match:
        return None

    comp_char, text, meta_str = match.groups()
    completed = comp_char.lower() == "x"
    description = text.strip()

    meta_dict: Dict[str, str] = {}
    if meta_str:
        for part in meta_str.split(","):
            if ":" in part:
                k, v = part.split(":", 1)
                meta_dict[k.strip().lower()] = v.strip()

    task_id = meta_dict.get("id")
    if not task_id:
        h = hashlib.sha256((description or str(idx)).encode("utf-8")).hexdigest()[:12]
        task_id = f"task_{h}"

    category = meta_dict.get("source") or meta_dict.get("category") or "general"
    item: Dict[str, Any] = {
        "id": task_id,
        "title": description,
        "description": description,
        "completed": completed,
        "category": category,
    }

    similarity = meta_dict.get("similarity")
    if similarity:
        try:
            item["similarity"] = float(similarity)
        except ValueError:
            pass

    return item


def parse_tasks_data(data: Any) -> List[Dict[str, Any]]:
    """Parse raw JSON input or CLI prose string into a list of task dictionaries."""
    parsed = data
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            parsed = data

    # Handle string input (raw text or JSON-encoded prose string from omi local task search)
    if isinstance(parsed, str):
        tasks: List[Dict[str, Any]] = []
        for idx, line in enumerate(parsed.splitlines()):
            t = parse_prose_line(line, idx)
            if t:
                tasks.append(t)
        if not tasks:
            raise ValueError("No valid task entries found in text input")
        return tasks

    if isinstance(parsed, dict):
        if "tasks" in parsed and isinstance(parsed["tasks"], list):
            items = parsed["tasks"]
        elif "result" in parsed and isinstance(parsed["result"], list):
            items = parsed["result"]
        elif "rows" in parsed and isinstance(parsed["rows"], list):
            items = parsed["rows"]
        elif "data" in parsed and isinstance(parsed["data"], list):
            items = parsed["data"]
        elif "id" in parsed or "title" in parsed or "description" in parsed:
            items = [parsed]
        else:
            raise ValueError("Expected a JSON array or object containing 'tasks', 'result', 'rows', or 'data'")
    elif isinstance(parsed, list):
        items = parsed
    else:
        raise ValueError(f"Unexpected JSON root type: {type(parsed).__name__}")

    tasks = []
    for idx, item in enumerate(items):
        if isinstance(item, str):
            t = parse_prose_line(item, idx)
            if t:
                tasks.append(t)
        elif isinstance(item, dict):
            tasks.append(item)
        else:
            raise ValueError(f"Item at index {idx} is not a valid JSON object or task line")
    return tasks


def normalize_task_record(
    item: Dict[str, Any], idx: int
) -> Tuple[str, str, str, int, Optional[str], Optional[str], Optional[str], Optional[str], str]:
    """Normalize dictionary into a tuple suitable for SQLite insertion."""
    title = str(item.get("title") or item.get("description") or f"Untitled Task {idx}").strip()
    desc = str(item.get("description") or "").strip()

    raw_id = item.get("id") or item.get("task_id")
    if raw_id:
        task_id = str(raw_id).strip()
    else:
        h = hashlib.sha256((title or str(idx)).encode("utf-8")).hexdigest()[:12]
        task_id = f"task_{h}"

    # Handle completed boolean
    comp_val = item.get("completed")
    if isinstance(comp_val, bool):
        completed = 1 if comp_val else 0
    elif isinstance(comp_val, (int, float)):
        completed = 1 if comp_val != 0 else 0
    elif isinstance(comp_val, str):
        completed = 1 if comp_val.strip().lower() in ["true", "1", "yes", "completed"] else 0
    else:
        completed = 0

    created_at = str(item.get("created_at") or "").strip() or None
    updated_at = str(item.get("updated_at") or "").strip() or None
    due_at = str(item.get("due_at") or item.get("due_date") or "").strip() or None
    category = str(item.get("category") or item.get("source") or "general").strip() or None
    raw_json = json.dumps(item, ensure_ascii=False)

    return (task_id, title, desc, completed, created_at, updated_at, due_at, category, raw_json)


def import_tasks_to_db(db_path: Path, tasks: Sequence[Dict[str, Any]]) -> Tuple[int, int]:
    """Insert or update tasks in SQLite database.

    Returns:
        (total_tasks_processed, completed_tasks_count)
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.executescript(SCHEMA)
            records = [normalize_task_record(t, idx) for idx, t in enumerate(tasks)]
            conn.executemany(
                """
                INSERT INTO local_tasks (id, title, description, completed, created_at, updated_at, due_at, category, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    description = excluded.description,
                    completed = excluded.completed,
                    created_at = COALESCE(excluded.created_at, local_tasks.created_at),
                    updated_at = excluded.updated_at,
                    due_at = excluded.due_at,
                    category = excluded.category,
                    raw_json = excluded.raw_json
                """,
                records,
            )
            cursor = conn.execute("SELECT COUNT(*), SUM(completed) FROM local_tasks")
            row = cursor.fetchone()
            total_in_db = row[0] if row else 0
            completed_in_db = row[1] if row and row[1] is not None else 0
            return total_in_db, completed_in_db
    finally:
        conn.close()


def load_input_sources(inputs: Sequence[str]) -> List[Dict[str, Any]]:
    """Load tasks from files or stdin."""
    all_tasks: List[Dict[str, Any]] = []
    for src in inputs:
        if src == "-":
            raw = sys.stdin.read()
            if raw.strip():
                all_tasks.extend(parse_tasks_data(raw))
        else:
            path = Path(src)
            if not path.is_file():
                raise FileNotFoundError(f"Input file not found: {path}")
            raw = path.read_text(encoding="utf-8")
            if raw.strip():
                all_tasks.extend(parse_tasks_data(raw))
    return all_tasks


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Convert Omi Desktop local tasks JSON or search exports to SQLite database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        default=["-"],
        help="Input JSON or search text file path(s), or '-' to read from standard input (default: -).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output SQLite database destination path.",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing database file if it already exists.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.output.exists() and args.force:
        args.output.unlink()

    try:
        tasks = load_input_sources(args.inputs)
    except Exception as exc:
        sys.stderr.write(f"Error reading input: {exc}\n")
        return 1

    try:
        total, completed = import_tasks_to_db(args.output, tasks)
        open_tasks = total - completed
        print(f"Imported {len(tasks)} task(s) into '{args.output}'. Total in DB: {total} ({completed} completed, {open_tasks} open).")
    except Exception as exc:
        sys.stderr.write(f"Error writing to SQLite database: {exc}\n")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
