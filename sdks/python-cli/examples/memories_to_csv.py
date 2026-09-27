#!/usr/bin/env python3
"""Convert Omi memories JSON exports to clean CSV for spreadsheets (Excel, Google Sheets, Pandas).

Features:
- Standalone standard-library utility (no external dependencies).
- Built-in CSV formula injection protection (neutralizing '=', '+', '-', '@', '\t', '\r').
- Supports piping from stdin or reading from files.
- Unwraps raw JSON arrays or wrapped payloads ({"memories": [...]}).
- Optional filtering by category and tag.
- Output encoded with UTF-8-SIG for instant compatibility with Microsoft Excel.

Usage:
    # Pipe directly from omi CLI
    omi --json memory list | python memories_to_csv.py - -o memories.csv

    # Convert saved export file to stdout
    python memories_to_csv.py memories.json

    # Filter by category
    omi --json memory list | python memories_to_csv.py - --category work,learnings -o work_memories.csv
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set

CSV_HEADERS: Sequence[str] = (
    "id",
    "category",
    "content",
    "tags",
    "visibility",
    "is_user_created",
    "created_at",
    "updated_at",
)


def spreadsheet_text(value: Any) -> str:
    """Sanitize strings against CSV formula injection and normalize nulls."""
    if value is None:
        return ""
    text = str(value).strip().replace("\r\n", " ").replace("\n", " ")
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{text}"
    return text


def format_tags(tags_val: Any) -> str:
    """Format tags list or string into comma-separated text."""
    if tags_val is None:
        return ""
    if isinstance(tags_val, list):
        return ", ".join(str(t).strip() for t in tags_val if str(t).strip())
    return str(tags_val).strip()


def parse_memories_payload(payload: Any) -> List[Dict[str, Any]]:
    """Extract list of memory objects from raw list or common envelope dictionaries."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("memories", "items", "data", "results"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, dict)]
        if "id" in payload or "content" in payload:
            return [payload]
    return []


def memory_to_csv_row(memory: Dict[str, Any]) -> Dict[str, str]:
    """Convert single memory dict to sanitized CSV row dict matching CSV_HEADERS."""
    is_user_created = memory.get("is_user_created")
    is_user_created_str = ""
    if is_user_created is not None:
        is_user_created_str = "true" if bool(is_user_created) else "false"

    return {
        "id": spreadsheet_text(memory.get("id")),
        "category": spreadsheet_text(memory.get("category")),
        "content": spreadsheet_text(memory.get("content")),
        "tags": spreadsheet_text(format_tags(memory.get("tags"))),
        "visibility": spreadsheet_text(memory.get("visibility")),
        "is_user_created": is_user_created_str,
        "created_at": spreadsheet_text(memory.get("created_at")),
        "updated_at": spreadsheet_text(memory.get("updated_at")),
    }


def filter_memories(
    memories: Sequence[Dict[str, Any]],
    categories: Optional[Set[str]] = None,
    tags: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """Filter memory items by category and/or tag."""
    filtered: List[Dict[str, Any]] = []
    for mem in memories:
        if categories:
            cat = str(mem.get("category") or "").strip().lower()
            if cat not in categories:
                continue

        if tags:
            mem_tags_raw = mem.get("tags")
            mem_tags: Set[str] = set()
            if isinstance(mem_tags_raw, list):
                mem_tags = {str(t).strip().lower() for t in mem_tags_raw if str(t).strip()}
            elif isinstance(mem_tags_raw, str):
                mem_tags = {t.strip().lower() for t in mem_tags_raw.split(",") if t.strip()}
            if not (tags & mem_tags):
                continue

        filtered.append(mem)
    return filtered


def convert_to_csv(
    memories: Sequence[Dict[str, Any]],
    output_stream: io.TextIOBase,
    categories: Optional[Set[str]] = None,
    tags: Optional[Set[str]] = None,
) -> int:
    """Write sanitized memory rows to the given CSV text stream and return row count."""
    items = filter_memories(memories, categories=categories, tags=tags)
    writer = csv.DictWriter(output_stream, fieldnames=CSV_HEADERS, lineterminator="\n")
    writer.writeheader()
    for item in items:
        writer.writerow(memory_to_csv_row(item))
    return len(items)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Convert Omi memories JSON exports to clean CSV for spreadsheets.")
    parser.add_argument(
        "input",
        nargs="?",
        default="-",
        help="Input JSON file path or '-' to read from standard input (default: '-')",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output CSV file path. If omitted, writes to stdout.",
    )
    parser.add_argument(
        "--category",
        help="Filter by comma-separated categories (e.g. 'work,learnings'). Case-insensitive.",
    )
    parser.add_argument(
        "--tag",
        help="Filter by comma-separated tags (e.g. 'python,ai'). Case-insensitive.",
    )

    args = parser.parse_args(argv)

    # Read input payload
    if args.input == "-":
        raw_text = sys.stdin.read()
    else:
        in_path = Path(args.input)
        if not in_path.exists():
            sys.stderr.write(f"Error: input file not found: {in_path}\n")
            return 1
        raw_text = in_path.read_text(encoding="utf-8-sig")

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"Error: invalid JSON input: {exc}\n")
        return 1

    memories = parse_memories_payload(data)

    cat_filter = None
    if args.category:
        cat_filter = {c.strip().lower() for c in args.category.split(",") if c.strip()}

    tag_filter = None
    if args.tag:
        tag_filter = {t.strip().lower() for t in args.tag.split(",") if t.strip()}

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8-sig", newline="") as f:
            count = convert_to_csv(memories, f, categories=cat_filter, tags=tag_filter)
        print(f"Exported {count} memory item(s) to {args.output}")
    else:
        convert_to_csv(memories, sys.stdout, categories=cat_filter, tags=tag_filter)

    return 0


if __name__ == "__main__":
    sys.exit(main())
