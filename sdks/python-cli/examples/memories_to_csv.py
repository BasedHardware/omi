#!/usr/bin/env python3
"""
Convert Omi memories JSON exports to clean CSV for Excel, Google Sheets, Airtable, or Notion.

Usage:
    # Pipe directly from omi CLI
    omi --json memory list | python memories_to_csv.py -

    # Export to a specific CSV file
    omi --json memory list | python memories_to_csv.py - --output ~/Desktop/memories.csv

    # Filter specific categories (e.g. work and learnings)
    python memories_to_csv.py memories.json --category work,learnings --output work_memories.csv

    # Filter by visibility or tag
    python memories_to_csv.py memories.json --visibility private --tag architecture
"""

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

DEFAULT_COLUMNS = ["id", "category", "content", "tags", "visibility", "created_at"]


def sanitize_cell_value(value: Any) -> str:
    """
    Sanitize text against CSV Formula Injection.
    If text begins with =, +, -, @, \\t, or \\r, prepend a single quote so spreadsheet
    apps interpret it as pure text rather than executable formulas.
    """
    if value is None:
        return ""
    text = str(value).strip().replace("\r\n", " ").replace("\n", " ")
    if text and text[0] in ("=", "+", "-", "@", "\t", "\r"):
        return f"'{text}"
    return text


def parse_iso_datetime(iso_str: Optional[str]) -> Optional[datetime]:
    """Safely parse an ISO-8601 datetime string and normalize to UTC."""
    if not iso_str or not isinstance(iso_str, str):
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception:
        return None


def format_iso_datetime(iso_str: Optional[str]) -> str:
    """Format ISO timestamp into human-friendly ISO format YYYY-MM-DD HH:MM:SS (UTC)."""
    dt = parse_iso_datetime(iso_str)
    if not dt:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def filter_memories(
    items: List[Dict[str, Any]],
    categories: Optional[Set[str]] = None,
    visibility: Optional[str] = None,
    tag: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Filter memory items by category, visibility, or tag."""
    filtered: List[Dict[str, Any]] = []
    vis_filter = visibility.strip().lower() if visibility else None
    tag_filter = tag.strip().lower() if tag else None

    for item in items:
        if not isinstance(item, dict):
            continue

        if categories:
            cat = str(item.get("category") or "").strip().lower()
            if cat not in categories:
                continue

        if vis_filter:
            vis = str(item.get("visibility") or "").strip().lower()
            if vis != vis_filter:
                continue

        if tag_filter:
            item_tags = item.get("tags") or []
            if isinstance(item_tags, list):
                tags_lower = [str(t).strip().lower() for t in item_tags if t]
                if tag_filter not in tags_lower:
                    continue
            else:
                continue

        filtered.append(item)

    return filtered


def memories_to_csv(
    items: List[Dict[str, Any]],
    columns: Optional[List[str]] = None,
    sort_order: str = "date_desc",
) -> str:
    """
    Render a list of memory dictionaries into a CSV string.
    Safely sanitizes cells against formula injection.
    """
    cols = columns or DEFAULT_COLUMNS
    output = StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(cols)

    # Sorting
    def sort_key(item: Dict[str, Any]):
        dt = parse_iso_datetime(item.get("created_at"))
        timestamp = dt.timestamp() if dt else 0.0
        return timestamp

    sorted_items = list(items)
    if sort_order == "date_desc":
        sorted_items.sort(key=sort_key, reverse=True)
    elif sort_order == "date_asc":
        sorted_items.sort(key=sort_key, reverse=False)
    elif sort_order == "category":
        sorted_items.sort(key=lambda x: (str(x.get("category") or "").lower(), -sort_key(x)))

    for item in sorted_items:
        row = []
        for col in cols:
            if col == "id":
                row.append(sanitize_cell_value(item.get("id")))
            elif col == "category":
                row.append(sanitize_cell_value(item.get("category") or "uncategorized"))
            elif col == "content":
                row.append(sanitize_cell_value(item.get("content")))
            elif col == "tags":
                tags_list = item.get("tags") or []
                if isinstance(tags_list, list):
                    tags_str = ", ".join(str(t).strip() for t in tags_list if t)
                else:
                    tags_str = str(tags_list)
                row.append(sanitize_cell_value(tags_str))
            elif col == "visibility":
                row.append(sanitize_cell_value(item.get("visibility") or "private"))
            elif col == "created_at":
                row.append(format_iso_datetime(item.get("created_at")))
            else:
                # Custom column fallback
                row.append(sanitize_cell_value(item.get(col)))
        writer.writerow(row)

    return output.getvalue()


def parse_input_payload(raw_data: str) -> List[Dict[str, Any]]:
    """Parse JSON data from string, supporting top-level list or dict wrapper."""
    cleaned = raw_data.strip()
    if cleaned.startswith("\ufeff"):
        cleaned = cleaned[1:]
    if not cleaned:
        return []

    data = json.loads(cleaned)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # OMI CLI often wraps list in 'memories' or 'data'
        if "memories" in data and isinstance(data["memories"], list):
            return data["memories"]
        if "data" in data and isinstance(data["data"], list):
            return data["data"]
        return [data]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi memories JSON to spreadsheet-friendly CSV."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="-",
        help="Input JSON file path or '-' for standard input (default: '-')",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Output CSV file path. If omitted, outputs to stdout.",
    )
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="Filter comma-separated list of categories (e.g. 'work,learnings').",
    )
    parser.add_argument(
        "--visibility",
        type=str,
        default=None,
        choices=["public", "private"],
        help="Filter by visibility ('public' or 'private').",
    )
    parser.add_argument(
        "--tag",
        type=str,
        default=None,
        help="Filter by specific tag.",
    )
    parser.add_argument(
        "--sort",
        type=str,
        default="date_desc",
        choices=["date_desc", "date_asc", "category"],
        help="Sort order of memories (default: 'date_desc').",
    )
    args = parser.parse_args()

    # Read input
    if args.input == "-":
        raw_text = sys.stdin.read()
    else:
        in_path = Path(args.input)
        if not in_path.is_file():
            sys.stderr.write(f"Error: Input file '{args.input}' not found.\n")
            return 1
        raw_text = in_path.read_text(encoding="utf-8")

    try:
        items = parse_input_payload(raw_text)
    except Exception as e:
        sys.stderr.write(f"Error parsing JSON input: {e}\n")
        return 1

    cats_filter = None
    if args.category:
        cats_filter = {c.strip().lower() for c in args.category.split(",") if c.strip()}

    filtered = filter_memories(
        items,
        categories=cats_filter,
        visibility=args.visibility,
        tag=args.tag,
    )

    csv_content = memories_to_csv(filtered, sort_order=args.sort)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # Use utf-8-sig for seamless Excel compatibility
        out_path.write_text(csv_content, encoding="utf-8-sig")
        sys.stderr.write(f"Exported {len(filtered)} memories to '{args.output}'.\n")
    else:
        sys.stdout.write(csv_content)

    return 0


if __name__ == "__main__":
    sys.exit(main())
