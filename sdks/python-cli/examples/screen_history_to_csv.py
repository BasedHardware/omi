#!/usr/bin/env python3
"""
screen_history_to_csv.py

Converts a screen history JSON file (containing OCR text and metadata) into a
CSV file that is safe to import into spreadsheet applications.

The script is intentionally lightweight and does not depend on any external
packages beyond the Python standard library. It performs robust error handling
and writes the output atomically to avoid corrupting existing files.

Usage:
    python screen_history_to_csv.py <input.json> [--output <output.csv>]

If --output is omitted, the CSV will be written to the same directory as the
input file with the same base name and a .csv extension.
"""

import argparse
import csv
import json
import os
import pathlib
import shutil
import sys
import tempfile
from typing import Iterable, Mapping, Sequence


def _collect_headers(records: Sequence[Mapping[str, object]]) -> Sequence[str]:
    """
    Return a sorted list of all unique keys found in the sequence of records.
    """
    header_set = set()
    for record in records:
        header_set.update(record.keys())
    return sorted(header_set)


def _write_csv_atomic(
    records: Sequence[Mapping[str, object]],
    output_path: pathlib.Path,
) -> pathlib.Path:
    """
    Write the records to a CSV file atomically.

    The function writes to a temporary file in the same directory and then
    replaces the target file in a single atomic operation.

    Parameters
    ----------
    records
        Sequence of mapping objects representing rows.
    output_path
        Destination path for the CSV file.

    Returns
    -------
    pathlib.Path
        The path to the written CSV file.
    """
    headers = _collect_headers(records)
    temp_path = output_path.with_suffix(".tmp")

    try:
        with temp_path.open("w", newline="", encoding="utf-8") as fp:
            writer = csv.DictWriter(fp, fieldnames=headers)
            writer.writeheader()
            for record in records:
                writer.writerow(record)
        # Atomic replace
        output_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temp_path, output_path)
    except Exception:
        # Ensure the temp file is removed on failure
        if temp_path.exists():
            temp_path.unlink()
        raise
    return output_path


def convert_to_csv(
    input_path: pathlib.Path,
    output_path: pathlib.Path | None = None,
) -> pathlib.Path:
    """
    Convert a screen history JSON file to a CSV file.

    Parameters
    ----------
    input_path
        Path to the input JSON file.
    output_path
        Optional path for the output CSV. If omitted, the CSV will be written
        to the same directory as the input file with a .csv extension.

    Returns
    -------
    pathlib.Path
        The path to the created CSV file.
    """
    if not input_path.is_file():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    with input_path.open("r", encoding="utf-8") as fp:
        try:
            data = json.load(fp)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Failed to parse JSON: {exc}") from exc

    if not isinstance(data, list):
        raise ValueError("Expected a JSON array of records")

    if output_path is None:
        output_path = input_path.with_suffix(".csv")

    return _write_csv_atomic(data, output_path)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert screen history JSON to CSV."
    )
    parser.add_argument(
        "input",
        type=pathlib.Path,
        help="Path to the input screen history JSON file.",
    )
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        help="Optional path for the output CSV file.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    try:
        output = convert_to_csv(args.input, args.output)
        print(f"CSV written to: {output}")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
