"""
Convert Omi tracked goals JSON exports to clean, spreadsheet-safe CSV.
Compatible with Excel, Google Sheets, Notion, and Airtable.

Usage:
    # Pipe directly from omi CLI
    omi --json goal list | python goals_to_csv.py - > goals.csv

    # Export to a specific CSV file
    python goals_to_csv.py goals.json --output goals.csv

    # Filter only active goals
    omi --json goal list | python goals_to_csv.py - --status active -o active_goals.csv
"""

import argparse
import csv
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

FIELDS = (
    "id",
    "title",
    "goal_type",
    "current_value",
    "target_value",
    "progress_pct",
    "unit",
    "min_value",
    "max_value",
    "is_active",
    "created_at",
    "updated_at",
)

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_cell_value(value: Any) -> str:
    """Format value and escape potential formula injection prefixes."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"

    text = str(value)
    if text.startswith(FORMULA_PREFIXES):
        return f"'{text}"
    return text


def format_iso_datetime(iso_str: Optional[str]) -> str:
    """Normalize ISO-8601 timestamps to readable UTC YYYY-MM-DD HH:MM:SS format."""
    if not iso_str or not isinstance(iso_str, str):
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(iso_str)


def compute_progress_pct(current: Any, target: Any) -> str:
    """Calculate completion percentage safely."""
    try:
        c = float(current)
        t = float(target)
        if t > 0:
            pct = (c / t) * 100.0
            return f"{pct:.1f}%"
    except (ValueError, TypeError, ZeroDivisionError):
        pass
    return ""


def goals_to_csv(
    items: List[Dict[str, Any]],
    status_filter: str = "all",
) -> str:
    """Convert a list of goal dicts into a CSV string."""
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")

    writer.writerow(FIELDS)

    for item in items:
        if not isinstance(item, dict):
            continue

        is_active = bool(item.get("is_active", True))
        if status_filter == "active" and not is_active:
            continue
        if status_filter == "inactive" and is_active:
            continue

        current = item.get("current_value", 0)
        target = item.get("target_value", 0)
        progress = compute_progress_pct(current, target)

        row = [
            sanitize_cell_value(item.get("id")),
            sanitize_cell_value(item.get("title")),
            sanitize_cell_value(item.get("goal_type")),
            sanitize_cell_value(current),
            sanitize_cell_value(target),
            sanitize_cell_value(progress),
            sanitize_cell_value(item.get("unit")),
            sanitize_cell_value(item.get("min_value")),
            sanitize_cell_value(item.get("max_value")),
            "true" if is_active else "false",
            format_iso_datetime(item.get("created_at")),
            format_iso_datetime(item.get("updated_at")),
        ]
        writer.writerow(row)

    return output.getvalue()


def parse_input_payload(raw_data: str) -> List[Dict[str, Any]]:
    """Parse JSON array or nested object from CLI output."""
    payload = json.loads(raw_data)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return (
            payload.get("goals")
            or payload.get("items")
            or payload.get("data")
            or [payload]
        )
    raise ValueError("Input must be a JSON array or object containing goals.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi tracked goals JSON to spreadsheet-safe CSV."
    )
    parser.add_argument(
        "input",
        help="Path to JSON file containing goals, or '-' to read from stdin.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Output CSV file path. Defaults to stdout.",
    )
    parser.add_argument(
        "--status",
        "-s",
        choices=["all", "active", "inactive"],
        default="all",
        help="Filter goals by status (default: all).",
    )

    args = parser.parse_args()

    try:
        if args.input == "-":
            raw_data = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
        else:
            input_path = Path(args.input)
            if not input_path.exists():
                sys.stderr.write(f"Error: Input file does not exist: {args.input}\n")
                return 1
            raw_data = input_path.read_bytes().decode("utf-8-sig", errors="replace")

        if not raw_data.strip():
            sys.stderr.write("Error: Input payload is empty.\n")
            return 1

        items = parse_input_payload(raw_data)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"Error: Invalid JSON input: {exc}\n")
        return 1
    except Exception as exc:
        sys.stderr.write(f"Error reading input: {exc}\n")
        return 1

    csv_data = goals_to_csv(items, status_filter=args.status)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # UTF-8 BOM so Excel opens accented characters seamlessly
        args.output.write_bytes(csv_data.encode("utf-8-sig"))
        sys.stderr.write(f"Successfully exported goals to {args.output}\n")
    else:
        try:
            sys.stdout.write(csv_data)
        except UnicodeEncodeError:
            sys.stdout.buffer.write(csv_data.encode("utf-8", errors="replace"))

    return 0


if __name__ == "__main__":
    sys.exit(main())
