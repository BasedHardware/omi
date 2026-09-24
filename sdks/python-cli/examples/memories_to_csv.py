#!/usr/bin/env python3
"""Convert Omi memories JSON exports to CSV spreadsheet format.

Usage:
    python memories_to_csv.py memories.json -o memories.csv
    omi --json memory list | python memories_to_csv.py - -o memories.csv
    python memories_to_csv.py page1.json page2.json -o all_memories.csv

Outputs a spreadsheet-ready UTF-8 CSV with formula injection safeguards and
UTC-normalized timestamps compatible with Excel, Google Sheets, and LibreOffice.
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

FIELDS: Sequence[str] = (
    "id",
    "content",
    "category",
    "manually_added",
    "created_at",
    "updated_at",
)


def spreadsheet_text(value: Any) -> str:
    """Render one exported field as spreadsheet-safe text.

    Coerces non-null values safely to strings and escapes common formula
    prefixes (=, +, -, @) to prevent CSV formula injection vulnerabilities.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def boolean_text(value: Any) -> str:
    """Render boolean status cleanly as 'true' or 'false'."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return "true" if value else "false"
    if isinstance(value, str):
        return "true" if value.strip().lower() in ("true", "1", "yes") else "false"
    return "false"


def utc_stamp(value: Optional[str]) -> str:
    """Normalise an ISO-8601 timestamp to UTC 'YYYY-MM-DD HH:MM:SS' text.

    Returns empty string for None/empty to keep CSV output clean.
    """
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        return str(value)


def extract_memories(content: str, source_label: str = "<input>") -> List[Dict[str, Any]]:
    """Parse JSON content and extract a list of memory dictionaries."""
    raw = content.lstrip("\ufeff")
    items = json.loads(raw)

    if isinstance(items, dict):
        for key in ("memories", "items", "data"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError(f"{source_label}: expected a JSON array or wrapped memories object")

    results: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source_label}: each memory must be a JSON object")
        if not item.get("id") or str(item.get("id")).strip() == "":
            raise ValueError(f"{source_label}: memory missing required 'id' field")
        results.append(item)

    return results


def memory_to_row(item: Dict[str, Any]) -> List[str]:
    """Convert a single memory object into a formatted CSV row."""
    mem_id = str(item.get("id"))
    content = item.get("content") or item.get("text") or item.get("description") or ""
    category = item.get("category") or ""
    manually_added = boolean_text(item.get("manually_added"))
    created_at = utc_stamp(item.get("created_at"))
    updated_at = utc_stamp(item.get("updated_at"))

    return [
        spreadsheet_text(mem_id),
        spreadsheet_text(content),
        spreadsheet_text(category),
        spreadsheet_text(manually_added),
        spreadsheet_text(created_at),
        spreadsheet_text(updated_at),
    ]


def convert_paths_to_csv(sources: Sequence[str | Path], output_dest: Optional[str | Path] = None) -> int:
    """Convert one or more JSON files (or stdin) to CSV format.

    Returns the number of memories converted.
    """
    all_memories: List[Dict[str, Any]] = []

    for src in sources:
        if str(src) == "-":
            content = sys.stdin.read()
            all_memories.extend(extract_memories(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_memories.extend(extract_memories(content, str(p)))

    rows = [list(FIELDS)]
    for mem in all_memories:
        rows.append(memory_to_row(mem))

    if output_dest and str(output_dest) != "-":
        out_path = Path(output_dest)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerows(rows)
    else:
        out_buf = io.StringIO()
        writer = csv.writer(out_buf)
        writer.writerows(rows)
        sys.stdout.write(out_buf.getvalue())

    return len(all_memories)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi memories JSON exports to a CSV spreadsheet."
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
        help="Destination CSV file (defaults to stdout)",
    )
    args = parser.parse_args()

    try:
        count = convert_paths_to_csv(args.inputs, args.output)
        if args.output != "-":
            print(f"Exported {count} memory/memories to {args.output}", file=sys.stderr)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
