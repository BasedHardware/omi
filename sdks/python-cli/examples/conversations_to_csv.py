#!/usr/bin/env python3
"""Convert an Omi conversation-list export to a spreadsheet-safe CSV file.

Reads a saved JSON export from `omi --json conversation list`, sanitizes fields
against spreadsheet formula injection, handles loose dev-API types gracefully,
and performs atomic output writing with overwrite protection.
"""

from __future__ import annotations

import csv
import io
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

FIELDS: Sequence[str] = ("id", "title", "category", "started_at", "source")


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


def convert(source: str | Path, destination: str | Path) -> int:
    """Convert an Omi conversations JSON export file into a CSV file.

    Returns the number of conversations converted.
    Raises ValueError on invalid JSON structure or item schemas.
    Raises FileExistsError if the destination file already exists.
    """
    raw_content = Path(source).read_bytes()
    try:
        items = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON source: {exc}") from exc

    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json conversation list")

    rows: List[List[str]] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"Conversation at index {idx} must be an object")
        structured = item.get("structured")
        if structured is None:
            structured = {}
        if not isinstance(structured, dict):
            raise ValueError(f"Conversation structured field at index {idx} must be an object or null")

        values = (
            item.get("id"),
            structured.get("title"),
            structured.get("category"),
            item.get("started_at"),
            item.get("source"),
        )
        rows.append([spreadsheet_text(value) for value in values])

    # Format and encode the whole export before touching the filesystem, so a
    # conversion failure cannot leave a truncated CSV behind for the next run.
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(FIELDS)
    writer.writerows(rows)
    payload = buffer.getvalue().encode("utf-8-sig")

    output_path = Path(destination)
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing {output_path}")

    # Write to a temporary sibling file in the same directory to allow atomic publish.
    parent_dir = output_path.parent if str(output_path.parent) != "" else Path(".")
    temp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=parent_dir,
            prefix=f".{output_path.name}.",
            delete=False,
        ) as tmp:
            temp_path = Path(tmp.name)
            tmp.write(payload)

        try:
            os.link(temp_path, output_path)
            temp_path.unlink(missing_ok=True)
        except (AttributeError, OSError):
            if output_path.exists():
                raise FileExistsError(f"Refusing to overwrite existing {output_path}")
            temp_path.replace(output_path)
    except Exception:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise

    return len(rows)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entrypoint."""
    args = sys.argv[1:] if argv is None else list(argv)
    if len(args) != 2:
        sys.stderr.write("Usage: python conversations_to_csv.py INPUT.json OUTPUT.csv\n")
        return 1

    source, destination = args[0], args[1]
    try:
        count = convert(source, destination)
        sys.stderr.write(f"Successfully exported {count} conversation(s) to {destination}\n")
        return 0
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"CSV export failed: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
