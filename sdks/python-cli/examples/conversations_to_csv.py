#!/usr/bin/env python3
"""Convert Omi conversation-list export to CSV."""

import csv
import io
import json
import sys
from pathlib import Path

FIELDS = ("id", "title", "category", "started_at", "source")


def spreadsheet_text(value):
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


def convert(source, destination):
    raw_payload = Path(source).read_bytes()
    items = json.loads(raw_payload)
    if isinstance(items, dict):
        for key in ("conversations", "data", "items"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json conversation list")
    rows = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each conversation must be an object")
        structured = item.get("structured")
        if structured is None:
            structured = {}
        if not isinstance(structured, dict):
            raise ValueError("Conversation structured field must be an object or null")
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
    # Exclusive creation still protects an existing export.
    try:
        output = output_path.open("xb")
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing {output_path}") from None
    try:
        with output:
            output.write(payload)
    except OSError:
        # Leave no partial export behind when the write itself fails.
        output_path.unlink(missing_ok=True)
        raise
    return len(rows)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        sys.exit("Usage: python conversations_to_csv.py INPUT.json OUTPUT.csv")
    try:
        count = convert(args[0], args[1])
    except (OSError, ValueError) as exc:
        sys.exit(f"CSV export failed: {exc}")
    print(f"{count} row{'s' if count != 1 else ''} written to {args[1]}")


if __name__ == "__main__":
    main()
