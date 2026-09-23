#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""
Convert OMI memory JSON export to CSV for spreadsheets.

Reads a JSON export from `omi --json memory list` and generates a spreadsheet-ready
CSV file. Protects against spreadsheet formula injection, handles UTF-8 BOM encoding
for Excel and Google Sheets, and writes output safely.

Usage:
    # Convert from file
    python3 memories_to_csv.py memories.json memories.csv

    # Pipe directly from omi CLI
    omi --json memory list | python3 memories_to_csv.py - memories.csv
"""

import argparse
import csv
import io
import json
import sys
from pathlib import Path

FIELDS = ("id", "content", "category", "created_at", "updated_at", "manually_added")


def spreadsheet_text(value) -> str:
    """Render one exported field as spreadsheet-safe text.

    Coerces non-string types and prefixes cells starting with formula trigger
    characters (=, +, -, @) with a single apostrophe to prevent CSV injection.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        if isinstance(value, bool):
            return "true" if value else "false"
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)

    # Prevent formula execution in spreadsheet applications
    stripped = value.lstrip()
    if stripped.startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def convert(source: str | Path, destination: str | Path, force: bool = False) -> int:
    """Convert JSON memory export to a CSV file."""
    if str(source) == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(source).read_text(encoding="utf-8")

    if not raw.strip():
        raise ValueError("Input JSON payload is empty")

    data = json.loads(raw)
    if isinstance(data, dict):
        if "memories" in data and isinstance(data["memories"], list):
            items = data["memories"]
        elif "items" in data and isinstance(data["items"], list):
            items = data["items"]
        else:
            items = [data]
    elif isinstance(data, list):
        items = data
    else:
        raise ValueError("Expected a JSON array of memories or memory object")

    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"Each memory item must be a JSON object, got {type(item).__name__}")

        mid = spreadsheet_text(item.get("id"))
        content = spreadsheet_text(item.get("content") or item.get("text"))
        category = spreadsheet_text(item.get("category"))
        created_at = spreadsheet_text(item.get("created_at"))
        updated_at = spreadsheet_text(item.get("updated_at"))
        manually_added = spreadsheet_text(item.get("manually_added"))

        rows.append((mid, content, category, created_at, updated_at, manually_added))

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(FIELDS)
    writer.writerows(rows)

    dest = Path(destination)
    mode = "wb" if force else "xb"
    try:
        with dest.open(mode) as fh:
            fh.write(buf.getvalue().encode("utf-8-sig"))
    except FileExistsError:
        raise FileExistsError(f"Destination file '{dest}' already exists. Use --force to overwrite.")

    return len(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Convert OMI memory JSON export to CSV for spreadsheets."
    )
    parser.add_argument(
        "source",
        help="Path to JSON file from 'omi --json memory list' (use '-' for stdin)",
    )
    parser.add_argument(
        "destination",
        help="Path to output .csv file",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Overwrite destination file if it already exists",
    )

    args = parser.parse_args(argv)

    try:
        count = convert(args.source, args.destination, force=args.force)
        print(f"Exported {count} memory record(s) to '{args.destination}'")
        return 0
    except Exception as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
