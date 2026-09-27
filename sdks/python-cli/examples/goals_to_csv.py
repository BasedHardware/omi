#!/usr/bin/env python3
"""Convert Omi goals JSON exports to clean CSV for spreadsheets (Excel, Google Sheets, Pandas).

Features:
- Standalone standard-library utility (no external dependencies).
- Calculates completion progress percentage (`progress_percent`) per goal.
- Built-in CSV formula injection protection (neutralizing '=', '+', '-', '@').
- Supports piping from stdin or reading from files.
- Unwraps raw JSON arrays or wrapped payloads ({"goals": [...]}).

Usage:
    # Pipe directly from omi CLI
    omi --json goal list | python goals_to_csv.py - -o goals.csv

    # Convert saved export file to stdout
    python goals_to_csv.py goals.json

    # Filter only active goals
    omi --json goal list | python goals_to_csv.py - --active-only -o active_goals.csv
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

CSV_HEADERS: Sequence[str] = (
    "id",
    "title",
    "goal_type",
    "current_value",
    "target_value",
    "min_value",
    "max_value",
    "unit",
    "progress_percent",
    "is_active",
    "created_at",
    "updated_at",
)


def spreadsheet_text(value: Any) -> str:
    """Render a field value as safe text to prevent spreadsheet formula injection.

    Leading '=', '+', '-', '@', tab, and newline are escaped with a leading apostrophe
    so spreadsheets treat them as literal strings rather than executable expressions.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return f"{value:g}"
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)

    stripped = value.lstrip()
    if stripped.startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def calculate_progress_percent(item: Dict[str, Any]) -> float:
    """Calculate progress percentage (0.0 to 100.0) based on goal type and values."""
    goal_type = str(item.get("goal_type") or "numeric").lower()
    try:
        current = float(item.get("current_value") or 0.0)
        target = float(item.get("target_value") or 0.0)
        min_val = float(item.get("min_value") or 0.0)
    except (ValueError, TypeError):
        return 0.0

    if goal_type == "boolean":
        is_done = current >= target if target > 0 else bool(current)
        return 100.0 if is_done else 0.0

    span = target - min_val
    if span <= 0:
        return 100.0 if current >= target else 0.0

    pct = ((current - min_val) / span) * 100.0
    return round(max(0.0, min(100.0, pct)), 2)


def unwrap_goals(data: Any) -> List[Dict[str, Any]]:
    """Extract list of goal dictionaries from payload or dictionary envelope."""
    if isinstance(data, list):
        return [g for g in data if isinstance(g, dict)]
    if isinstance(data, dict):
        for key in ("goals", "items", "data", "results"):
            val = data.get(key)
            if isinstance(val, list):
                return [g for g in val if isinstance(g, dict)]
    return []


def format_goal_row(item: Dict[str, Any]) -> Dict[str, str]:
    """Map a goal dictionary into sanitized CSV row string values."""
    pct = calculate_progress_percent(item)
    return {
        "id": spreadsheet_text(item.get("id")),
        "title": spreadsheet_text(item.get("title")),
        "goal_type": spreadsheet_text(item.get("goal_type")),
        "current_value": spreadsheet_text(item.get("current_value")),
        "target_value": spreadsheet_text(item.get("target_value")),
        "min_value": spreadsheet_text(item.get("min_value")),
        "max_value": spreadsheet_text(item.get("max_value")),
        "unit": spreadsheet_text(item.get("unit")),
        "progress_percent": f"{pct:.2f}",
        "is_active": spreadsheet_text(bool(item.get("is_active", True))),
        "created_at": spreadsheet_text(item.get("created_at")),
        "updated_at": spreadsheet_text(item.get("updated_at")),
    }


def convert_goals_to_csv(goals: List[Dict[str, Any]]) -> str:
    """Convert a sequence of goal items into CSV string format."""
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_HEADERS, lineterminator="\n")
    writer.writeheader()
    for item in goals:
        writer.writerow(format_goal_row(item))
    return out.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi goals JSON exports to clean CSV format for spreadsheets.",
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="-",
        help="Input JSON file path, or '-' to read from standard input (default: -)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Path to output CSV file (default: stdout)",
    )
    parser.add_argument(
        "--active-only",
        action="store_true",
        help="Filter and export only active goals",
    )

    args = parser.parse_args()

    if args.input == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(args.input).read_text(encoding="utf-8-sig")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Error parsing JSON input: {exc}", file=sys.stderr)
        sys.exit(1)

    goals = unwrap_goals(data)

    if args.active_only:
        goals = [g for g in goals if bool(g.get("is_active", True))]

    csv_output = convert_goals_to_csv(goals)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(csv_output, encoding="utf-8")
        print(f"Exported {len(goals)} goals to {args.output}")
    else:
        sys.stdout.write(csv_output)


if __name__ == "__main__":
    main()
