#!/usr/bin/env python3
"""Convert Omi memories and facts JSON exports into Tab-Separated Values (TSV) format.

Usage:
    python memories_to_tsv.py memories.json -o memories.tsv
    omi --json memory list | python memories_to_tsv.py - -o memories.tsv
    python memories_to_tsv.py memories.json -o work_memories.tsv --category work,learnings

Outputs tab-delimited text (TSV) optimized for direct clipboard copy-pasting
into Microsoft Excel, Google Sheets, Airtable, and Notion databases.
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

FIELDS = ("id", "content", "category", "tags", "visibility", "created_at", "updated_at")


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


def convert_to_tsv(
    sources: Sequence[str | Path],
    output_dest: Optional[str | Path] = None,
    category_filter: Optional[str] = None,
) -> int:
    """Convert memories into TSV format."""
    all_items: List[Dict[str, Any]] = []

    for src in sources:
        if str(src) == "-":
            content = sys.stdin.read()
            all_items.extend(extract_memories(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_items.extend(extract_memories(content, str(p)))

    filter_cats = {c.strip().lower() for c in category_filter.split(",")} if category_filter else None

    seen_ids = set()
    rows = []
    count = 0
    for item in all_items:
        mid = str(item.get("id"))
        if mid not in seen_ids:
            seen_ids.add(mid)
            cat = str(item.get("category") or "").strip().lower()
            if filter_cats and cat not in filter_cats:
                continue

            tags_raw = item.get("tags")
            if isinstance(tags_raw, list):
                tags_str = ", ".join(str(t).strip() for t in tags_raw if str(t).strip())
            else:
                tags_str = str(tags_raw or "").strip()

            content_text = item.get("content") or ""
            row = [
                spreadsheet_tsv_text(mid),
                spreadsheet_tsv_text(content_text),
                spreadsheet_tsv_text(cat),
                spreadsheet_tsv_text(tags_str),
                spreadsheet_tsv_text(str(item.get("visibility") or "public").strip().lower()),
                spreadsheet_tsv_text(utc_stamp(item.get("created_at"))),
                spreadsheet_tsv_text(utc_stamp(item.get("updated_at"))),
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
        description="Convert Omi memories JSON exports into Tab-Separated Values (TSV) format."
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
        "-c",
        "--category",
        default=None,
        help="Filter by category (comma-separated, e.g. 'work,learnings')",
    )
    args = parser.parse_args()

    try:
        count = convert_to_tsv(args.inputs, args.output, category_filter=args.category)
        if args.output != "-":
            print(f"Exported {count} memory/memories to {args.output}", file=sys.stderr)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
