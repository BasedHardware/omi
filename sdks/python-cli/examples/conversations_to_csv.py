#!/usr/bin/env python3
"""
Convert Omi conversation-list JSON export to CSV for spreadsheets.

Usage:
    python conversations_to_csv.py conversations.json conversations.csv
    python conversations_to_csv.py conversations.json -o conversations.csv
    python conversations_to_csv.py conversations.json conversations.csv --overwrite
    cat conversations.json | python conversations_to_csv.py - conversations.csv

This converter reads a saved JSON export, makes no network requests, and does not
export transcripts. It formats output with UTF-8 BOM encoding for Excel compatibility,
neutralises formula injection prefixes, and guards against directory traversal.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

FIELDS: Tuple[str, ...] = ("id", "title", "category", "started_at", "source")


def spreadsheet_text(value: Any) -> str:
    """Render one exported field as spreadsheet-safe text.

    The dev API is loosely typed, so a field can arrive as a non-string even
    though the CLI models it as Optional[str]. One odd row must not destroy a
    whole export, so anything non-null is coerced rather than rejected.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
    # Avoid treating common formula prefixes as formulas on spreadsheet import.
    # The apostrophe is intentional and may be visible in some importers.
    if value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


def extract_conversations(raw_data: Union[str, bytes]) -> List[Dict[str, Any]]:
    """Parse JSON text/bytes and extract a normalized list of conversation objects."""
    if isinstance(raw_data, bytes):
        raw_text = raw_data.decode("utf-8-sig")
    else:
        raw_text = raw_data.lstrip("\ufeff")

    try:
        items = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON data: {exc}") from exc

    # Support bare list, wrapped object {"conversations": [...]}, or single object
    if isinstance(items, dict):
        for key in ("conversations", "items", "data", "results"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json conversation list")

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"Conversation at index {idx} must be an object")

    return items


def validate_destination(destination: Union[str, Path], overwrite: bool = False) -> Path:
    """Validate that the destination path is safe to write."""
    dest_path = Path(destination)
    if ".." in dest_path.parts:
        raise ValueError(f"Output path {destination!r} contains '..'; refusing to write outside the intended directory.")
    if dest_path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing {dest_path}")
    return dest_path


def convert_conversations_to_csv_bytes(items: Sequence[Dict[str, Any]]) -> bytes:
    """Transform conversation objects into UTF-8-sig encoded CSV bytes."""
    rows: List[List[str]] = []
    for item in items:
        structured = item.get("structured")
        if structured is None:
            structured = {}
        elif not isinstance(structured, dict):
            raise ValueError("Conversation structured field must be an object or null")

        values = (
            item.get("id"),
            structured.get("title"),
            structured.get("category"),
            item.get("started_at"),
            item.get("source"),
        )
        rows.append([spreadsheet_text(v) for v in values])

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(FIELDS)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def convert(source: Union[str, Path], destination: Union[str, Path], overwrite: bool = False) -> int:
    """Convert JSON conversation export from source file or stdin to destination CSV."""
    if str(source) == "-":
        raw_data = sys.stdin.buffer.read()
    else:
        src_path = Path(source)
        if not src_path.exists():
            raise FileNotFoundError(f"Input file not found: {source}")
        raw_data = src_path.read_bytes()

    dest_path = validate_destination(destination, overwrite=overwrite)
    items = extract_conversations(raw_data)
    payload = convert_conversations_to_csv_bytes(items)

    # Ensure parent directories exist if specified
    if dest_path.parent and not dest_path.parent.exists():
        dest_path.parent.mkdir(parents=True, exist_ok=True)

    # Write payload atomically to avoid corrupting or leaving partial files
    if overwrite:
        dest_path.write_bytes(payload)
    else:
        try:
            with dest_path.open("xb") as fh:
                fh.write(payload)
        except FileExistsError:
            raise FileExistsError(f"Refusing to overwrite existing {dest_path}") from None
        except OSError:
            dest_path.unlink(missing_ok=True)
            raise

    return len(items)


def build_parser() -> argparse.ArgumentParser:
    """Build the command line argument parser."""
    parser = argparse.ArgumentParser(
        description="Convert Omi conversation-list JSON export to CSV for spreadsheets.",
    )
    parser.add_argument(
        "source",
        help="Input JSON file or '-' for stdin",
    )
    parser.add_argument(
        "destination",
        nargs="?",
        default=None,
        help="Output CSV file path",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output_flag",
        default=None,
        help="Output CSV file path (alternative to positional argument)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow overwriting existing destination CSV",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    destination = args.output_flag or args.destination
    if not destination:
        parser.error("Destination CSV path must be provided as second argument or via -o/--output")

    try:
        count = convert(args.source, destination, overwrite=args.overwrite)
        print(f"Exported {count} conversation{'s' if count != 1 else ''} to {destination}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"CSV export failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
