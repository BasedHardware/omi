#!/usr/bin/env python3
"""Convert Omi action items JSON exports into Tab-Separated Values (TSV) format.

Usage:
    python action_items_to_tsv.py action_items.json -o tasks.tsv
    omi --json action-item list | python action_items_to_tsv.py - -o tasks.tsv
    python action_items_to_tsv.py tasks.json -o open_tasks.tsv --status open

Outputs tab-delimited text (TSV) optimized for direct clipboard copy-pasting
into Microsoft Excel, Google Sheets, Airtable, and Notion tables without CSV delimiter confusion.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

FIELDS = ("id", "description", "completed", "due_at", "created_at", "updated_at", "conversation_id")


def utc_stamp(value: Optional[str]) -> str:
    """Normalise an ISO-8601 timestamp to UTC 'YYYY-MM-DD HH:MM:SS' text."""
    if not value or not isinstance(value, str):
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        return value


def parse_boolean(value: Any) -> bool:
    """Normalize completion status to a strict boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "completed", "done")
    return False


def spreadsheet_tsv_text(value: Any) -> str:
    """Render one exported field as TSV and spreadsheet-safe text."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)

    # Clean tabs and newlines to preserve TSV layout integrity
    value = value.replace("\t", " ").replace("\r\n", " ").replace("\n", " ").strip()

    # Prevent CSV / TSV formula injection in spreadsheet applications
    if value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def extract_action_items(content: str, source_label: str = "<input>") -> List[Dict[str, Any]]:
    """Parse JSON content and extract a list of action item dictionaries."""
    raw = content.lstrip("\ufeff")
    items = json.loads(raw)

    if isinstance(items, dict):
        for key in ("action_items", "items", "data"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError(f"{source_label}: expected a JSON array or wrapped action_items object")

    results: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source_label}: each action item must be a JSON object")
        if not item.get("id") or str(item.get("id")).strip() == "":
            raise ValueError(f"{source_label}: action item missing required 'id' field")
        results.append(item)

    return results


def convert_to_tsv(
    sources: Sequence[str | Path],
    output_dest: Optional[str | Path] = None,
    status_filter: str = "all",
) -> int:
    """Convert action items into TSV format."""
    all_items: List[Dict[str, Any]] = []

    for src in sources:
        if str(src) == "-":
            content = sys.stdin.read()
            all_items.extend(extract_action_items(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_items.extend(extract_action_items(content, str(p)))

    seen_ids = set()
    rows = []
    count = 0
    for item in all_items:
        iid = str(item.get("id"))
        if iid not in seen_ids:
            seen_ids.add(iid)
            completed = parse_boolean(item.get("completed"))
            if status_filter == "open" and completed:
                continue
            if status_filter == "completed" and not completed:
                continue

            desc = item.get("description") or item.get("title") or ""
            row = [
                spreadsheet_tsv_text(iid),
                spreadsheet_tsv_text(desc),
                "TRUE" if completed else "FALSE",
                spreadsheet_tsv_text(utc_stamp(item.get("due_at"))),
                spreadsheet_tsv_text(utc_stamp(item.get("created_at"))),
                spreadsheet_tsv_text(utc_stamp(item.get("updated_at"))),
                spreadsheet_tsv_text(item.get("conversation_id")),
            ]
            rows.append(row)
            count += 1

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter="\t", lineterminator="\n")
    writer.writerow(FIELDS)
    writer.writerows(rows)
    tsv_content = buffer.getvalue()

    if output_dest and str(output_dest) != "-":
        out_path = Path(output_dest)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(tsv_content, encoding="utf-8")
    else:
        sys.stdout.write(tsv_content)

    return count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi action items JSON exports into Tab-Separated Values (TSV) format."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Input JSON files or '-' for standard input",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Destination TSV file (defaults to stdout)",
    )
    parser.add_argument(
        "--status",
        choices=["all", "open", "completed"],
        default="all",
        help="Filter action items by status (default: all)",
    )
    args = parser.parse_args()

    try:
        count = convert_to_tsv(args.inputs, args.output, status_filter=args.status)
        if args.output != "-":
            print(f"Exported {count} action item(s) to {args.output}", file=sys.stderr)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
