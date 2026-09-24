#!/usr/bin/env python3
"""
Convert Omi action-item list JSON exports to a CSV spreadsheet.

Exports personal action items, tasks, and follow-ups into a spreadsheet-safe
CSV file with UTF-8 BOM encoding for seamless opening in Microsoft Excel,
Apple Numbers, Google Sheets, or Python/Pandas data pipelines.

Features formula injection protection, completion status normalization,
optional status filtering (--status open/completed/all), and multi-file deduplication.

Usage:
    # Basic conversion
    python action_items_to_csv.py action_items.json tasks.csv

    # Pipeline streaming via stdin
    omi --json action-item list --limit 200 | python action_items_to_csv.py - tasks.csv

    # Filter only open / pending tasks
    python action_items_to_csv.py action_items.json pending_tasks.csv --status open

    # Multi-page deduplicated export
    python action_items_to_csv.py page1.json page2.json all_tasks.csv --force
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

FIELDS = (
    "id",
    "description",
    "completed",
    "status",
    "due_at",
    "created_at",
    "updated_at",
    "conversation_id",
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

    # Normalize internal spaces while preserving content
    cleaned = " ".join(value.split())

    # Prevent spreadsheet formula injection
    if cleaned.lstrip().startswith(("=", "+", "-", "@")) or cleaned.startswith(("\t", "\r", "\n")):
        return "'" + cleaned
    return cleaned


def is_completed(value: Any) -> bool:
    """Normalize completion status from bool, int, or string."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "completed", "done")
    return False


def load(sources: List[str]) -> Dict[str, Dict[str, Any]]:
    """Load action item objects from one or more JSON files or stdin ('-'). Deduplicates by ID."""
    items_map: Dict[str, Dict[str, Any]] = {}
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
                parsed.get("action_items")
                or parsed.get("items")
                or parsed.get("data")
                or [parsed]
            )
        else:
            items = parsed

        if not isinstance(items, list):
            raise ValueError(f"{display_name}: expected a JSON array of action items from 'omi --json action-item list'")

        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"{display_name}[{idx}]: each action item must be a JSON object")
            item_id = item.get("id")
            if not item_id or not isinstance(item_id, str):
                raise ValueError(f"{display_name}[{idx}]: missing or invalid string 'id'")
            items_map[str(item_id).strip()] = item

    return items_map


def items_to_rows(items_map: Dict[str, Dict[str, Any]], status_filter: str = "all") -> List[List[str]]:
    """Convert action items mapping to CSV rows, optionally filtering by status."""
    rows: List[List[str]] = []
    norm_filter = status_filter.strip().lower()

    for item_id, item in items_map.items():
        completed_flag = is_completed(item.get("completed"))
        status_str = "completed" if completed_flag else "open"

        # Apply status filtering
        if norm_filter in ("open", "pending") and completed_flag:
            continue
        if norm_filter in ("completed", "done") and not completed_flag:
            continue

        desc = item.get("description") or item.get("text") or item.get("title") or ""
        due_at = item.get("due_at") or item.get("due_date") or ""
        created_at = item.get("created_at") or ""
        updated_at = item.get("updated_at") or ""
        conversation_id = item.get("conversation_id") or ""

        row = [
            spreadsheet_text(item_id),
            spreadsheet_text(desc),
            spreadsheet_text("TRUE" if completed_flag else "FALSE"),
            spreadsheet_text(status_str),
            spreadsheet_text(due_at),
            spreadsheet_text(created_at),
            spreadsheet_text(updated_at),
            spreadsheet_text(conversation_id),
        ]
        rows.append(row)
    return rows


def convert(
    sources: List[str],
    destination: str,
    status_filter: str = "all",
    force: bool = False,
) -> None:
    """Load action items from sources, convert to CSV, and write to destination."""
    dest_path = Path(destination)
    if dest_path.exists() and not force:
        raise FileExistsError(f"Destination file already exists: {destination}. Use --force to overwrite.")

    items_map = load(sources)
    rows = items_to_rows(items_map, status_filter=status_filter)

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
        description="Convert Omi action-item JSON exports to a CSV spreadsheet.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  omi --json action-item list | python action_items_to_csv.py - tasks.csv
  python action_items_to_csv.py tasks.json tasks.csv --status open
  python action_items_to_csv.py p1.json p2.json all_tasks.csv --force
""",
    )
    parser.add_argument(
        "sources",
        nargs="+",
        metavar="SOURCE",
        help="One or more JSON files exported from 'omi --json action-item list', or '-' for stdin.",
    )
    parser.add_argument(
        "destination",
        metavar="DESTINATION",
        help="Path to output .csv file.",
    )
    parser.add_argument(
        "--status",
        choices=["all", "open", "pending", "completed", "done"],
        default="all",
        help="Filter action items by status (default: all).",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite destination file if it already exists.",
    )

    args = parser.parse_args()

    try:
        convert(
            sources=args.sources,
            destination=args.destination,
            status_filter=args.status,
            force=args.force,
        )
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
