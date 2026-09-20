"""
Convert Omi action items / tasks JSON exports to clean, spreadsheet-safe CSV.
Compatible with Excel, Google Sheets, Notion, Todoist, and Airtable.

Usage:
    # Pipe directly from omi CLI
    omi --json action-item list | python action_items_to_csv.py - > action_items.csv

    # Export to a specific CSV file
    python action_items_to_csv.py action_items.json --output action_items.csv

    # Filter only open (pending) action items
    omi --json action-item list | python action_items_to_csv.py - --status open -o open_tasks.csv
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
    "completed",
    "description",
    "due_at",
    "created_at",
    "updated_at",
    "conversation_id",
)

# Spreadsheet formula trigger characters to escape against CSV injection
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_cell_value(value: Any) -> str:
    """Format value and escape potential formula injection prefixes."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"

    text = str(value)
    # If text starts with formula triggers, quote with a leading apostrophe
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


def action_items_to_csv(
    items: List[Dict[str, Any]],
    status_filter: str = "all",
) -> str:
    """Convert a list of action item dicts into a CSV string."""
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")

    writer.writerow(FIELDS)

    for item in items:
        if not isinstance(item, dict):
            continue

        is_completed = bool(item.get("completed", False))
        if status_filter == "open" and is_completed:
            continue
        if status_filter == "completed" and not is_completed:
            continue

        row = [
            sanitize_cell_value(item.get("id")),
            "true" if is_completed else "false",
            sanitize_cell_value(item.get("description")),
            format_iso_datetime(item.get("due_at")),
            format_iso_datetime(item.get("created_at")),
            format_iso_datetime(item.get("updated_at")),
            sanitize_cell_value(item.get("conversation_id")),
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
            payload.get("action_items")
            or payload.get("items")
            or payload.get("data")
            or [payload]
        )
    raise ValueError("Input must be a JSON array or object containing action items.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi action items JSON to spreadsheet-safe CSV."
    )
    parser.add_argument(
        "input",
        help="Path to JSON file containing action items, or '-' to read from stdin.",
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
        choices=["all", "open", "completed"],
        default="all",
        help="Filter action items by completion status (default: all).",
    )

    args = parser.parse_args()

    # Read input payload
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

    csv_data = action_items_to_csv(items, status_filter=args.status)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        # Write with UTF-8 BOM so Excel opens accented characters seamlessly
        args.output.write_bytes(csv_data.encode("utf-8-sig"))
        sys.stderr.write(
            f"Successfully exported action items to {args.output}\n"
        )
    else:
        try:
            sys.stdout.write(csv_data)
        except UnicodeEncodeError:
            sys.stdout.buffer.write(csv_data.encode("utf-8", errors="replace"))

    return 0


if __name__ == "__main__":
    sys.exit(main())
