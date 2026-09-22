#!/usr/bin/env python3
"""
screen_history_to_csv.py

A utility to convert a screen history file (JSON) into a CSV that is safe for
spreadsheet ingestion.  The input file is expected to contain a JSON array of
objects, each with at least the following keys:

    - timestamp: ISO‑8601 string or any string that can be written as-is
    - text:      the raw screen text
    - ocr_text:  optional OCR extracted text

The script writes a CSV with columns ``timestamp``, ``text`` and ``ocr_text``.
If ``ocr_text`` is missing for an entry it will be written as an empty string.

The conversion is performed atomically: a temporary file is written first and
then renamed to the target output path.  This guarantees that the output file
is never left in a partially written state.

Usage
-----
    python screen_history_to_csv.py --input screen_history.json [--output screen_history.csv]

If ``--output`` is omitted the input file will be overwritten atomically.
"""

import argparse
import csv
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Iterable, Mapping, Any


def _load_json(path: Path) -> Iterable[Mapping[str, Any]]:
    """Load a JSON array from *path* and return an iterable of dicts."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Input file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse JSON from {path}: {exc}") from exc

    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array in {path}, got {type(data).__name__}")

    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Item {idx} in {path} is not a JSON object")
        yield item


def _write_csv_atomic(rows: Iterable[Mapping[str, Any]], output_path: Path) -> None:
    """Write *rows* to *output_path* atomically."""
    temp_dir = output_path.parent
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        delete=False,
        dir=str(temp_dir),
        suffix=".tmp",
    ) as tmp_fh:
        writer = csv.DictWriter(
            tmp_fh,
            fieldnames=["timestamp", "text", "ocr_text"],
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "timestamp": row.get("timestamp", ""),
                    "text": row.get("text", ""),
                    "ocr_text": row.get("ocr_text", ""),
                }
            )
        temp_path = Path(tmp_fh.name)

    # Replace the target file atomically
    try:
        temp_path.replace(output_path)
    except Exception as exc:
        # Clean up temp file on failure
        temp_path.unlink(missing_ok=True)
        raise RuntimeError(f"Failed to replace {output_path} with temporary file: {exc}") from exc


def convert_screen_history_to_csv(input_path: Path, output_path: Path | None = None) -> None:
    """
    Convert a screen history JSON file to CSV.

    Parameters
    ----------
    input_path : Path
        Path to the input JSON file.
    output_path : Path | None
        Path to the output CSV file.  If None, *input_path* is overwritten
        atomically.
    """
    if output_path is None:
        output_path = input_path

    rows = _load_json(input_path)
    _write_csv_atomic(rows, output_path)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert screen history JSON to CSV for spreadsheet use."
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        type=Path,
        help="Path to the input screen history JSON file.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Path to the output CSV file. If omitted, the input file is overwritten.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    try:
        convert_screen_history_to_csv(args.input, args.output)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
