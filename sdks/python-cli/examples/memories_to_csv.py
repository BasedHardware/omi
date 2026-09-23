#!/usr/bin/env python3
"""Convert an Omi memory-list JSON export to CSV for spreadsheets.

Reads the JSON array produced by ``omi --json memory list`` and writes one
row per memory. Zero third-party dependencies: only the Python standard
library (``csv``, ``io``, ``json``, ``argparse``, ``os``, ``sys``,
``pathlib``, ``tempfile``).

Usage:
    omi --json memory list --limit 200 > memories.json
    python memories_to_csv.py memories.json memories.csv

    omi --json memory list --limit 200 | python memories_to_csv.py - memories.csv

The whole export is formatted in memory before anything is written to disk,
so a conversion failure can never leave a truncated CSV behind. An existing
destination is never overwritten unless ``--force`` is passed; with
``--force`` the replacement happens through an atomic rename.
"""

import argparse
import csv
import io
import json
import os
import sys
import tempfile
from pathlib import Path

# Columns mirror the CLI's Memory model (omi_cli/models.py: Memory):
# id, content, category, visibility, tags, created_at, updated_at,
# manually_added, reviewed, edited.
FIELDS = (
    "id",
    "content",
    "category",
    "visibility",
    "tags",
    "created_at",
    "updated_at",
    "manually_added",
    "reviewed",
    "edited",
)

FORMULA_PREFIXES = ("=", "+", "-", "@")


def spreadsheet_text(value):
    """Render one exported field as spreadsheet-safe text.

    The dev API is loosely typed, so a field can arrive as a non-string even
    though the CLI models it as a string. One odd row must not destroy a
    whole export, so anything non-null is coerced rather than rejected.

    Cells that would otherwise be interpreted as formulas on spreadsheet
    import (leading =, +, -, @, tab, CR, LF) are prefixed with an apostrophe,
    the standard CSV-injection guard used across the export trilogy. The
    apostrophe is intentional and may be visible in some importers.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if not isinstance(value, str):
        value = (
            json.dumps(value, ensure_ascii=False)
            if isinstance(value, (dict, list))
            else str(value)
        )
    if value.lstrip().startswith(FORMULA_PREFIXES) or value.startswith(
        ("\t", "\r", "\n")
    ):
        return "'" + value
    return value


def join_tags(tags):
    """Render the memory's tag list as one spreadsheet cell."""
    if tags is None:
        return ""
    if isinstance(tags, str):
        return spreadsheet_text(tags)
    if not isinstance(tags, list):
        raise ValueError("Each memory's tags must be a list, a string, or null")
    return "; ".join(spreadsheet_text(tag) for tag in tags)


def convert(source, destination, force=False):
    """Convert the JSON export at *source* into a CSV at *destination*.

    *source* may be a path or ``-`` for stdin. Raises ValueError on malformed
    input, FileExistsError when *destination* exists without ``--force``.
    """
    if source == "-":
        raw = sys.stdin.buffer.read()
    else:
        raw = Path(source).read_bytes()
    # utf-8-sig tolerates a BOM emitted by Windows PowerShell redirects.
    items = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(items, list):
        raise ValueError("Expected the JSON array from omi --json memory list")
    rows = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"Memory at index {index} must be an object")
        rows.append(
            [
                spreadsheet_text(item.get("id")),
                spreadsheet_text(item.get("content")),
                spreadsheet_text(item.get("category")),
                spreadsheet_text(item.get("visibility")),
                join_tags(item.get("tags")),
                spreadsheet_text(item.get("created_at")),
                spreadsheet_text(item.get("updated_at")),
                spreadsheet_text(item.get("manually_added")),
                spreadsheet_text(item.get("reviewed")),
                spreadsheet_text(item.get("edited")),
            ]
        )
    # Format and encode the whole export before touching the filesystem, so a
    # conversion failure cannot leave a truncated CSV behind for the next run.
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(FIELDS)
    writer.writerows(rows)
    payload = buffer.getvalue().encode("utf-8-sig")  # BOM for desktop spreadsheets

    output_path = Path(destination)
    if output_path.exists() and not force:
        raise FileExistsError(
            f"Refusing to overwrite existing {output_path} (use --force)"
        )
    if force:
        # Atomic replacement: write a temp file in the same directory, then
        # rename over the destination so readers never see a partial file.
        fd, tmp_name = tempfile.mkstemp(
            dir=str(output_path.parent) if str(output_path.parent) else ".",
            prefix=output_path.name,
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
            os.replace(tmp_name, output_path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
    else:
        # Exclusive creation still protects an existing export.
        try:
            output = output_path.open("xb")
        except FileExistsError:
            raise FileExistsError(
                f"Refusing to overwrite existing {output_path} (use --force)"
            ) from None
        try:
            with output:
                output.write(payload)
        except OSError:
            # Leave no partial export behind when the write itself fails.
            output_path.unlink(missing_ok=True)
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Convert an omi --json memory list export to CSV."
    )
    parser.add_argument("input", help="Path to the JSON export, or - for stdin")
    parser.add_argument("output", help="Destination .csv path")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the destination if it already exists",
    )
    args = parser.parse_args(argv)
    try:
        convert(args.input, args.output, force=args.force)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"CSV export failed: {exc}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
