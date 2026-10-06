"""Convert an omi-cli memory export to an Apache Parquet columnar dataset.

Reads JSON produced by `omi --json memory list --limit 200` (or piped via stdin),
and generates an Apache Parquet file for high-performance analytics, DuckDB,
Polars, Pandas, and AI fine-tuning.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    import pyarrow as pa
    import pyarrow.parquet as pq

    HAS_PYARROW = True
except ImportError:
    HAS_PYARROW = False

# Strict Parquet schema mirroring omi_cli.models.Memory + precomputed text metrics
SCHEMA_FIELDS = [
    ("id", "string"),
    ("content", "string"),
    ("category", "string"),
    ("visibility", "string"),
    ("tags", "list<string>"),
    ("created_at", "string"),
    ("updated_at", "string"),
    ("manually_added", "bool"),
    ("reviewed", "bool"),
    ("edited", "bool"),
    ("char_len", "int64"),
    ("word_count", "int64"),
]


def validate_path(path_str: str) -> Path:
    """Validate that path does not attempt path traversal."""
    p = Path(path_str)
    if ".." in p.parts:
        raise ValueError(f"Path traversal detected in path: {path_str}")
    return p


def get_pyarrow_schema() -> pa.Schema:
    """Return the PyArrow schema matching SCHEMA_FIELDS."""
    return pa.schema([
        pa.field("id", pa.string()),
        pa.field("content", pa.string()),
        pa.field("category", pa.string()),
        pa.field("visibility", pa.string()),
        pa.field("tags", pa.list_(pa.string())),
        pa.field("created_at", pa.string()),
        pa.field("updated_at", pa.string()),
        pa.field("manually_added", pa.bool_()),
        pa.field("reviewed", pa.bool_()),
        pa.field("edited", pa.bool_()),
        pa.field("char_len", pa.int64()),
        pa.field("word_count", pa.int64()),
    ])


def normalize_record(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize a memory JSON record into the Parquet schema layout."""
    content = str(item.get("content") or "")

    # Tags normalization
    raw_tags = item.get("tags")
    if isinstance(raw_tags, list):
        tags = [str(t) for t in raw_tags]
    elif isinstance(raw_tags, str) and raw_tags.strip():
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    else:
        tags = []

    return {
        "id": str(item.get("id") or ""),
        "content": content,
        "category": str(item.get("category") or "other"),
        "visibility": str(item.get("visibility") or "private"),
        "tags": tags,
        "created_at": str(item.get("created_at")) if item.get("created_at") is not None else None,
        "updated_at": str(item.get("updated_at")) if item.get("updated_at") is not None else None,
        "manually_added": bool(item.get("manually_added") or False),
        "reviewed": bool(item.get("reviewed") or False),
        "edited": bool(item.get("edited") or False),
        "char_len": len(content),
        "word_count": len(content.split()),
    }


def convert(
    source: str | Path,
    destination: str | Path,
    compression: str = "snappy",
    overwrite: bool = False,
) -> int:
    """Convert memory export JSON to an Apache Parquet file.

    Returns the count of exported records.
    """
    if not HAS_PYARROW:
        raise RuntimeError("pyarrow is required for Parquet export. Run 'pip install pyarrow'.")

    if str(source) == "-":
        raw = sys.stdin.buffer.read()
    else:
        src_path = validate_path(str(source))
        raw = src_path.read_bytes()

    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]

    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise ValueError(f"Invalid JSON input: {exc}") from exc

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("memories", "items", "data", "results"):
            if key in data and isinstance(data[key], list):
                items = data[key]
                break
        else:
            raise ValueError("Expected a JSON array or envelope object containing 'memories'")
    else:
        raise ValueError("Expected a JSON array or dictionary object")

    normalized = [normalize_record(item) for item in items]

    schema = get_pyarrow_schema()

    # Build columnar lists
    column_data = {field.name: [] for field in schema}
    for rec in normalized:
        for field in schema:
            column_data[field.name].append(rec[field.name])

    table = pa.Table.from_pydict(column_data, schema=schema)

    output_path = validate_path(str(destination))
    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"Output file '{output_path}' already exists. Use --overwrite to replace it."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial = output_path.with_name(f"{output_path.name}.partial")

    comp_opt = None if compression.lower() == "none" else compression.lower()
    try:
        pq.write_table(table, partial, compression=comp_opt)
        os.replace(partial, output_path)
    except Exception:
        if partial.exists():
            partial.unlink(missing_ok=True)
        raise

    return len(normalized)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert an omi-cli memory export into an Apache Parquet dataset."
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="-",
        help="Input JSON file path or '-' for stdin (default: -)",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output Parquet file path (.parquet)",
    )
    parser.add_argument(
        "-c",
        "--compression",
        choices=["snappy", "gzip", "zstd", "none"],
        default="snappy",
        help="Compression codec (default: snappy)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output file if present",
    )
    parser.add_argument(
        "--schema",
        action="store_true",
        help="Display the Parquet target schema and exit",
    )

    args = parser.parse_args()

    if args.schema:
        print("Apache Parquet Schema for Omi Memories:")
        for name, p_type in SCHEMA_FIELDS:
            print(f"  {name:15} : {p_type}")
        return

    if not args.output:
        parser.error("-o/--output is required unless --schema is specified")

    try:
        count = convert(
            args.input,
            args.output,
            compression=args.compression,
            overwrite=args.overwrite,
        )
        print(f"Exported {count} memory record(s) to {args.output}")
    except (OSError, ValueError, RuntimeError) as exc:
        sys.exit(f"Parquet export failed: {exc}")


if __name__ == "__main__":
    main()
