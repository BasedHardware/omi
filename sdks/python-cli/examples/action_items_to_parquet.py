#!/usr/bin/env python3
"""
action_items_to_parquet.py — Export Omi action items and tasks to Apache Parquet columnar datasets.

Parquet is the industry-standard columnar storage format optimized for:
  - Task completion analytics, SLA tracking, and productivity dashboards via DuckDB & Polars
  - AI assistant task modeling and habit extraction pipelines (Hugging Face Datasets)
  - High-ratio compression (Snappy, Zstandard, Gzip) and predicate pushdown
  - Seamless ingestion into modern AI data lakes and cloud warehouses

Usage:
  omi --json action-item list --limit 100 | python action_items_to_parquet.py -o action_items.parquet
  python action_items_to_parquet.py -i export.json -o action_items.parquet --compression zstd
  python action_items_to_parquet.py --json '[{"id": "task_1", "description": "Buy groceries"}]' --schema
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

PARQUET_TYPE_MAP = {
    "id": "string",
    "description": "string",
    "completed": "bool",
    "created_at": "string",
    "updated_at": "string",
    "due_at": "string",
    "completed_at": "string",
    "conversation_id": "string",
    "char_len": "int64",
    "word_count": "int64",
}


def normalize_iso_timestamp(val: Any) -> Optional[str]:
    """Normalize timestamp into UTC ISO-8601 string format (YYYY-MM-DDTHH:MM:SSZ)."""
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        try:
            dt = datetime.datetime.fromtimestamp(val, tz=datetime.timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, OSError, OverflowError):
            return None
    if isinstance(val, str):
        val_clean = val.strip()
        if not val_clean:
            return None
        try:
            dt = datetime.datetime.fromisoformat(val_clean.replace("Z", "+00:00"))
            dt_utc = dt.astimezone(datetime.timezone.utc)
            return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return val_clean
    return str(val)


def generate_task_hash_id(description: str, created_at: Optional[str]) -> str:
    """Generate a stable deterministic ID if the raw record lacks an explicit ID."""
    seed = f"{description}|{created_at or ''}"
    return f"task_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}"


def normalize_action_item_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten and normalize a raw Omi action-item dictionary into a typed Parquet row schema
    matching the official omi_cli.models.ActionItem model.
    """
    description = str(raw.get("description") or raw.get("title") or raw.get("content") or "").strip()
    created_at = normalize_iso_timestamp(raw.get("created_at") or raw.get("createdAt"))

    task_id = str(raw.get("id") or "").strip()
    if not task_id:
        task_id = generate_task_hash_id(description, created_at)

    completed = bool(raw.get("completed", raw.get("is_completed", False)))
    updated_at = normalize_iso_timestamp(raw.get("updated_at") or raw.get("updatedAt"))
    due_at = normalize_iso_timestamp(raw.get("due_at") or raw.get("dueAt") or raw.get("due_date"))
    completed_at = normalize_iso_timestamp(raw.get("completed_at") or raw.get("completedAt"))

    conversation_id = raw.get("conversation_id") or raw.get("conversationId")
    conv_id_str = str(conversation_id).strip() if conversation_id else None

    char_len = len(description)
    word_count = len(description.split()) if description else 0

    return {
        "id": task_id,
        "description": description,
        "completed": completed,
        "created_at": created_at,
        "updated_at": updated_at,
        "due_at": due_at,
        "completed_at": completed_at,
        "conversation_id": conv_id_str,
        "char_len": char_len,
        "word_count": word_count,
    }


def parse_omi_action_items(input_data: Union[str, bytes, List[Any], Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Parse raw JSON input (or python objects) into a list of normalized action item dicts."""
    if isinstance(input_data, (str, bytes)):
        text = input_data.decode("utf-8") if isinstance(input_data, bytes) else input_data
        text = text.strip()
        if not text:
            return []
        data = json.loads(text)
    else:
        data = input_data

    raw_list: List[Dict[str, Any]] = []
    if isinstance(data, list):
        raw_list = [item for item in data if isinstance(item, dict)]
    elif isinstance(data, dict):
        if "action_items" in data and isinstance(data["action_items"], list):
            raw_list = [item for item in data["action_items"] if isinstance(item, dict)]
        elif "items" in data and isinstance(data["items"], list):
            raw_list = [item for item in data["items"] if isinstance(item, dict)]
        elif "tasks" in data and isinstance(data["tasks"], list):
            raw_list = [item for item in data["tasks"] if isinstance(item, dict)]
        elif "data" in data and isinstance(data["data"], list):
            raw_list = [item for item in data["data"] if isinstance(item, dict)]
        elif "description" in data or "id" in data or "title" in data:
            raw_list = [data]

    normalized = [normalize_action_item_record(r) for r in raw_list]
    return [r for r in normalized if r["id"] or r["description"]]


def records_to_columnar_dict(records: List[Dict[str, Any]]) -> Dict[str, List[Any]]:
    """Convert a row-oriented list of dicts into columnar arrays for Apache Parquet."""
    columns: Dict[str, List[Any]] = {k: [] for k in PARQUET_TYPE_MAP}
    for r in records:
        for k in columns:
            columns[k].append(r.get(k))
    return columns


def build_pyarrow_table(records: List[Dict[str, Any]]) -> Any:
    """Build a strongly-typed pyarrow.Table from normalized action item records."""
    try:
        import pyarrow as pa
    except ImportError as exc:
        raise ImportError(
            "The 'pyarrow' package is required to serialize to Apache Parquet format. "
            "Install it via: pip install pyarrow"
        ) from exc

    col_dict = records_to_columnar_dict(records)
    schema = pa.schema(
        [
            ("id", pa.string()),
            ("description", pa.string()),
            ("completed", pa.bool_()),
            ("created_at", pa.string()),
            ("updated_at", pa.string()),
            ("due_at", pa.string()),
            ("completed_at", pa.string()),
            ("conversation_id", pa.string()),
            ("char_len", pa.int64()),
            ("word_count", pa.int64()),
        ]
    )
    return pa.Table.from_pydict(col_dict, schema=schema)


def write_parquet_file(
    records: List[Dict[str, Any]],
    output_path: Union[str, Path],
    compression: str = "snappy",
) -> Tuple[int, int, bool]:
    """
    Write normalized action item records to an Apache Parquet file.
    If pyarrow is available, writes binary Parquet.
    If pyarrow is not installed, writes a structured columnar JSON fallback
    so CI tests and lightweight environments execute without breaking.
    Returns (num_records, bytes_written, is_fallback).
    """
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        import pyarrow.parquet as pq

        table = build_pyarrow_table(records)
        codec = compression.lower()
        if codec == "none":
            codec = None

        pq.write_table(table, str(out_file), compression=codec)
        file_size = out_file.stat().st_size
        return len(records), file_size, False
    except ImportError:
        # Graceful zero-dependency columnar fallback
        fallback_file = (
            out_file if out_file.suffix in [".json", ".jsonl"] else out_file.with_name(f"{out_file.name}.json")
        )
        col_dict = records_to_columnar_dict(records)
        payload = {
            "format": "columnar_parquet_fallback",
            "schema": PARQUET_TYPE_MAP,
            "num_rows": len(records),
            "columns": col_dict,
        }
        fallback_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        file_size = fallback_file.stat().st_size
        return len(records), file_size, True


def inspect_parquet_file(file_path: Union[str, Path]) -> Dict[str, Any]:
    """Inspect schema, metadata, and row count of an existing Parquet file."""
    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise ImportError("pyarrow is required to inspect parquet files.") from exc

    parquet_file = pq.ParquetFile(str(file_path))
    metadata = parquet_file.metadata
    schema = parquet_file.schema_arrow

    return {
        "num_rows": metadata.num_rows,
        "num_columns": metadata.num_columns,
        "num_row_groups": metadata.num_row_groups,
        "serialized_size_bytes": Path(file_path).stat().st_size,
        "columns": [field.name for field in schema],
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Export Omi action items to Apache Parquet columnar datasets for analytics and productivity insights."
    )
    parser.add_argument(
        "-i",
        "--input",
        help="Input JSON file path containing Omi action items (default: stdin).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="action_items.parquet",
        help="Output Parquet file path (default: action_items.parquet).",
    )
    parser.add_argument(
        "--json",
        dest="json_arg",
        help="Direct JSON payload string containing action items.",
    )
    parser.add_argument(
        "-n",
        "--limit",
        type=int,
        default=None,
        help="Limit number of exported action item records.",
    )
    parser.add_argument(
        "-c",
        "--compression",
        choices=["snappy", "gzip", "zstd", "none"],
        default="snappy",
        help="Parquet compression codec (default: snappy).",
    )
    parser.add_argument(
        "--schema",
        action="store_true",
        help="Print the Parquet table schema and exit without writing.",
    )

    args = parser.parse_args(argv)

    # 1. Read input payload
    if args.json_arg:
        raw_text = args.json_arg
    elif args.input and args.input != "-":
        input_path = Path(args.input)
        if not input_path.exists():
            sys.stderr.write(f"Error: input file '{args.input}' not found.\n")
            return 1
        raw_text = input_path.read_text(encoding="utf-8")
    else:
        if sys.stdin.isatty():
            sys.stderr.write("Waiting for JSON action items on stdin (or use -i / --json)...\n")
        raw_text = sys.stdin.read()

    # 2. Parse & normalize
    records = parse_omi_action_items(raw_text)
    if args.limit and args.limit > 0:
        records = records[: args.limit]

    # 3. Schema mode
    if args.schema:
        print("Apache Parquet Inferred Schema for Action Items:")
        for col_name, parquet_type in PARQUET_TYPE_MAP.items():
            print(f"  - {col_name:18s} ({parquet_type})")
        print(f"\nTotal records: {len(records)}")
        return 0

    # 4. Write Parquet
    try:
        count, file_size, is_fallback = write_parquet_file(records, args.output, compression=args.compression)
        if is_fallback:
            print(
                f"Exported {count} action items to columnar fallback payload '{args.output}.json' "
                f"({file_size:,} bytes). Install 'pyarrow' for binary Parquet format: pip install pyarrow"
            )
        else:
            print(
                f"Successfully exported {count} action items to '{args.output}' "
                f"({file_size:,} bytes, compression: {args.compression})"
            )
        return 0
    except Exception as e:
        sys.stderr.write(f"Unexpected Error: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
