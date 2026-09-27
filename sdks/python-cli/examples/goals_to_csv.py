#!/usr/bin/env python3
"""Convert Omi goals JSON exports to clean CSV for spreadsheets (Excel, Google Sheets, Numbers, Pandas).

Features:
- Standalone standard-library utility (no external dependencies).
- Calculates completion progress percentage (`progress_percent`) per goal.
- Built-in CSV formula injection protection (neutralizing '=', '+', '-', '@', '\t', '\r').
- Supports piping from stdin or reading from files.
- Unwraps raw JSON arrays, dictionary envelopes ({"goals": [...]}), or single objects.
- Optional filtering for active goals only (--active-only).
- Output encoded with UTF-8-SIG for instant compatibility with Microsoft Excel.
- Safe file I/O protecting existing files against accidental overwrite unless --force is given.

Usage:
    # Pipe directly from omi CLI
    omi --json goal list | python goals_to_csv.py - -o goals.csv

    # Convert saved export file to stdout
    python goals_to_csv.py goals.json

    # Convert saved export file to a CSV file
    python goals_to_csv.py goals.json goals.csv

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
        text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    else:
        text = value

    text = text.strip().replace("\r\n", " ").replace("\n", " ")
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r")):
        return f"'{text}"
    return text


def calculate_progress_percent(item: Dict[str, Any]) -> float:
    """Calculate progress percentage (0.0 to 100.0) based on goal type and values."""
    goal_type = str(item.get("goal_type") or "numeric").lower()
    try:
        current = float(item.get("current_value") if item.get("current_value") is not None else 0.0)
        target = float(item.get("target_value") if item.get("target_value") is not None else 0.0)
        min_val = float(item.get("min_value") if item.get("min_value") is not None else 0.0)
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
    """Extract list of goal dictionaries from payload, dictionary envelope, or single object."""
    if isinstance(data, list):
        return [g for g in data if isinstance(g, dict)]
    if isinstance(data, dict):
        for key in ("goals", "items", "data", "results"):
            if key in data:
                val = data[key]
                if isinstance(val, list):
                    return [g for g in val if isinstance(g, dict)]
        if "id" in data or "title" in data:
            return [data]
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
        "is_active": spreadsheet_text(item.get("is_active")),
        "created_at": spreadsheet_text(item.get("created_at")),
        "updated_at": spreadsheet_text(item.get("updated_at")),
    }


def convert_goals_to_csv(goals: Sequence[Dict[str, Any]]) -> str:
    """Serialize list of goals to an in-memory CSV string."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_HEADERS, lineterminator="\n")
    writer.writeheader()
    for g in goals:
        writer.writerow(format_goal_row(g))
    return buf.getvalue()


def build_parser() -> argparse.ArgumentParser:
    """Build command-line parser."""
    parser = argparse.ArgumentParser(
        description="Convert Omi goals JSON exports to clean CSV for spreadsheets."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="-",
        help="Path to JSON file, or '-' to read from stdin (default: '-')",
    )
    parser.add_argument(
        "destination",
        nargs="?",
        default=None,
        help="Destination CSV file path (optional; can also use -o/--output)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Destination CSV file path. If omitted and no destination is given, writes to stdout.",
    )
    parser.add_argument(
        "--active-only",
        action="store_true",
        help="Filter to export only active (is_active == True) goals",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite destination file if it already exists",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.input == "-":
        raw = sys.stdin.read()
    else:
        in_path = Path(args.input)
        if not in_path.exists():
            sys.stderr.write(f"Error: input file not found: {in_path}\n")
            return 1
        raw = in_path.read_text(encoding="utf-8-sig")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"Error: invalid JSON input: {exc}\n")
        return 1

    goals = unwrap_goals(data)

    if args.active_only:
        goals = [g for g in goals if bool(g.get("is_active", True))]

    csv_output = convert_goals_to_csv(goals)
    target_output: Optional[Path] = args.output or (Path(args.destination) if args.destination else None)

    if target_output:
        target_output.parent.mkdir(parents=True, exist_ok=True)
        if not args.force:
            try:
                handle = target_output.open("xb")
            except FileExistsError:
                sys.stderr.write(f"Error: refusing to overwrite existing file: {target_output} (use --force)\n")
                return 1
        else:
            handle = target_output.open("wb")

        payload = csv_output.encode("utf-8-sig")
        try:
            with handle:
                handle.write(payload)
        except OSError as exc:
            if not args.force:
                target_output.unlink(missing_ok=True)
            sys.stderr.write(f"Error writing output file: {exc}\n")
            return 1
        print(f"Exported {len(goals)} goal(s) to {target_output}")
    else:
        sys.stdout.write(csv_output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
