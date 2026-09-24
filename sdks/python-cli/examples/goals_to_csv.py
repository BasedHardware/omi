#!/usr/bin/env python3
"""
Convert Omi goal-list JSON exports to a CSV spreadsheet.

Exports personal goals, milestones, and OKRs into a spreadsheet-safe CSV file
with UTF-8 BOM encoding for seamless opening in Microsoft Excel, Apple Numbers,
and Google Sheets.

Features formula injection protection, progress percentage calculation, and
multi-file deduplication.

Usage:
    # Basic conversion
    python goals_to_csv.py goals.json goals.csv

    # Pipeline streaming via stdin
    omi --json goal list --limit 100 --include-inactive | python goals_to_csv.py - goals.csv

    # Multi-file deduplicated export
    python goals_to_csv.py goals_work.json goals_personal.json all_goals.csv --force
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

FIELDS = (
    "id",
    "title",
    "status",
    "goal_type",
    "current_value",
    "target_value",
    "unit",
    "progress_percentage",
    "created_at",
    "updated_at",
)


def spreadsheet_text(value: Any) -> str:
    """Render one exported field as spreadsheet-safe text.

    Protects against CSV formula injection (DDE attacks) by prepending a single
    quote if a field starts with '=', '+', '-', '@', or whitespace characters.
    """
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    else:
        value = str(value)

    # Normalize whitespace
    cleaned = " ".join(value.split())

    # Prevent spreadsheet formula injection
    if cleaned.lstrip().startswith(("=", "+", "-", "@")) or cleaned.startswith(("\t", "\r", "\n")):
        return "'" + cleaned
    return cleaned


def compute_progress(item: Dict[str, Any], is_active: bool) -> Optional[float]:
    """Compute normalized progress percentage (0.0 - 100.0) or None."""
    if not is_active:
        return 100.0

    goal_type = str(item.get("goal_type") or item.get("type") or "qualitative").lower()
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


def load(sources: List[str]) -> Dict[str, Dict[str, Any]]:
    """Load goal objects from one or more JSON files or stdin ('-'). Deduplicates by ID."""
    goals: Dict[str, Dict[str, Any]] = {}
    for src in sources:
        if src == "-":
            raw = sys.stdin.read()
            display_name = "<stdin>"
        else:
            p = Path(src)
            if not p.is_file():
                raise FileNotFoundError(f"Input file not found: {src}")
            raw = p.read_bytes().decode("utf-8-sig")
            display_name = src

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{display_name}: invalid JSON ({exc})") from exc

        if isinstance(parsed, dict):
            items = (
                parsed.get("goals")
                or parsed.get("items")
                or parsed.get("data")
                or [parsed]
            )
        else:
            items = parsed

        if not isinstance(items, list):
            raise ValueError(f"{display_name}: expected a JSON array of goals from 'omi --json goal list'")

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"{display_name}[{idx}]: each goal must be a JSON object")
            item_id = item.get("id")
            if not item_id or not isinstance(item_id, str):
                raise ValueError(f"{display_name}[{idx}]: missing or invalid string 'id'")
            goals[str(item_id).strip()] = item

    return goals


def goals_to_rows(goals: Dict[str, Dict[str, Any]]) -> List[List[str]]:
    """Convert goals mapping to CSV rows."""
    rows = []
    for gid, item in goals.items():
        title = item.get("title") or item.get("text") or item.get("description") or ""
        status_raw = str(item.get("status") or "").strip().lower()
        is_active = item.get("is_active")
        if is_active is not None:
            active_flag = bool(is_active)
            status_str = "active" if active_flag else "completed"
        else:
            active_flag = status_raw not in ("completed", "archived", "done", "achieved", "abandoned")
            status_str = status_raw or "active"

        goal_type = str(item.get("goal_type") or item.get("type") or "qualitative")
        cur_val = item.get("current_value")
        target_val = item.get("target_value") if item.get("target_value") is not None else item.get("max_value")
        unit = item.get("unit") or ""
        progress_pct = compute_progress(item, active_flag)

        progress_str = f"{progress_pct:.2f}%" if progress_pct is not None else ""

        row = [
            spreadsheet_text(gid),
            spreadsheet_text(title),
            spreadsheet_text(status_str),
            spreadsheet_text(goal_type),
            spreadsheet_text(cur_val),
            spreadsheet_text(target_val),
            spreadsheet_text(unit),
            spreadsheet_text(progress_str),
            spreadsheet_text(item.get("created_at")),
            spreadsheet_text(item.get("updated_at")),
        ]
        rows.append(row)
    return rows


def convert(sources: List[str], destination: str, force: bool = False) -> None:
    """Load goals from sources, convert to CSV, and write to destination."""
    dest_path = Path(destination)
    if dest_path.exists() and not force:
        raise FileExistsError(f"Destination file already exists: {destination}. Use --force to overwrite.")

    goals = load(sources)
    rows = goals_to_rows(goals)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(FIELDS)
    writer.writerows(rows)

    # Encode with UTF-8 BOM so Excel opens it with correct encoding on all platforms
    payload = buffer.getvalue().encode("utf-8-sig")

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(payload)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi goal JSON exports to a CSV spreadsheet.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  omi --json goal list --limit 100 --include-inactive | python goals_to_csv.py - goals.csv
  python goals_to_csv.py goals.json my_goals.csv
  python goals_to_csv.py goals_work.json goals_personal.json all.csv --force
""",
    )
    parser.add_argument(
        "sources",
        nargs="+",
        metavar="SOURCE",
        help="One or more JSON files exported from 'omi --json goal list', or '-' for stdin.",
    )
    parser.add_argument(
        "destination",
        metavar="DESTINATION",
        help="Path to output .csv file.",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite destination file if it already exists.",
    )

    args = parser.parse_args()

    try:
        convert(sources=args.sources, destination=args.destination, force=args.force)
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
