#!/usr/bin/env python3
"""
memories_to_parquet.py — Export Omi memories to Apache Parquet columnar datasets.

Parquet is the industry-standard columnar storage format optimized for:
  - AI model fine-tuning and evaluation datasets (Hugging Face Datasets)
  - Blazing-fast analytical queries via DuckDB, Polars, and Apache Arrow
  - High-ratio compression (Snappy, Zstandard, Gzip) and predicate pushdown
  - Seamless ingestion into modern AI data lakes and cloud warehouses

Usage:
  omi memories list --json --limit 200 | python memories_to_parquet.py -o memories.parquet
  python memories_to_parquet.py -i export.json -o memories.parquet --compression zstd
  python memories_to_parquet.py --json '[{...}]' --schema
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


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


def extract_tags_json(raw_tags: Any) -> str:
    """Extract and normalize tags as a deterministic JSON array string."""
    if not raw_tags:
        return "[]"
    if isinstance(raw_tags, list):
        clean_tags = [str(t).strip() for t in raw_tags if str(t).strip()]
        return json.dumps(clean_tags, ensure_ascii=False)
    if isinstance(raw_tags, str):
        raw_str = raw_tags.strip()
        if raw_str.startswith("[") and raw_str.endswith("]"):
            try:
                parsed = json.loads(raw_str)
                if isinstance(parsed, list):
                    clean_tags = [str(t).strip() for t in parsed if str(t).strip()]
                    return json.dumps(clean_tags, ensure_ascii=False)
            except Exception:
                pass
        return json.dumps([raw_str], ensure_ascii=False)
    return json.dumps([str(raw_tags)], ensure_ascii=False)


def normalize_memory_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten and normalize a raw Omi memory dictionary into a typed Parquet row schema.
    """
    record_id = str(raw.get("id") or "").strip()
    content = str(raw.get("content") or raw.get("text") or "").strip()
    category = str(raw.get("category") or "other").strip().lower()
    visibility = str(raw.get("visibility") or "private").strip().lower()
    user_id = str(raw.get("user_id") or raw.get("uid") or "").strip()
    conversation_id = raw.get("conversation_id")
    conv_id_str = str(conversation_id).strip() if conversation_id else None

    is_starred = bool(raw.get("is_starred", raw.get("starred", False)))
    is_discarded = bool(raw.get("is_discarded", raw.get("discarded", False)))

    created_at = normalize_iso_timestamp(raw.get("created_at") or raw.get("createdAt"))
    updated_at = normalize_iso_timestamp(raw.get("updated_at") or raw.get("updatedAt"))

    tags_json = extract_tags_json(raw.get("tags") or raw.get("structured_tags"))
    source = str(raw.get("source") or "omi").strip()

    char_len = len(content)
    word_count = len(content.split()) if content else 0

    return {
        "id": record_id,
        "content": content,
        "category": category,
        "visibility": visibility,
        "user_id": user_id,
        "conversation_id": conv_id_str,
        "is_starred": is_starred,
        "is_discarded": is_discarded,
        "created_at": created_at,
        "updated_at": updated_at,
        "tags": tags_json,
        "source": source,
        "char_len": char_len,
        "word_count": word_count,
    }


def parse_omi_memories(input_data: Union[str, bytes, List[Any], Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Parse raw JSON input (or python objects) into a list of normalized memory dicts."""
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
        if "memories" in data and isinstance(data["memories"], list):
            raw_list = [item for item in data["memories"] if isinstance(item, dict)]
        elif "items" in data and isinstance(data["items"], list):
            raw_list = [item for item in data["items"] if isinstance(item, dict)]
        elif "data" in data and isinstance(data["data"], list):
            raw_list = [item for item in data["data"] if isinstance(item, dict)]
        elif "id" in data or "content" in data:
            raw_list = [data]

    normalized = [normalize_memory_record(r) for r in raw_list]
    return [r for r in normalized if r["id"] or r["content"]]


def records_to_columnar_dict(records: List[Dict[str, Any]]) -> Dict[str, List[Any]]:
    """Convert a row-oriented list of dicts into columnar arrays for Apache Parquet."""
    columns: Dict[str, List[Any]] = {
        "id": [],
        "content": [],
        "category": [],
        "visibility": [],
        "user_id": [],
        "conversation_id": [],
        "is_starred": [],
        "is_discarded": [],
        "created_at": [],
        "updated_at": [],
        "tags": [],
        "source": [],
        "char_len": [],
        "word_count": [],
    }
    for r in records:
        for k in columns:
            columns[k].append(r.get(k))
    return columns


def build_pyarrow_table(records: List[Dict[str, Any]]) -> Any:
    """Build a strongly-typed pyarrow.Table from normalized records."""
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
            ("content", pa.string()),
            ("category", pa.string()),
            ("visibility", pa.string()),
            ("user_id", pa.string()),
            ("conversation_id", pa.string()),
            ("is_starred", pa.bool_()),
            ("is_discarded", pa.bool_()),
            ("created_at", pa.string()),
            ("updated_at", pa.string()),
            ("tags", pa.string()),
            ("source", pa.string()),
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
    Write normalized memory records to an Apache Parquet file.
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
            "schema": {
                "id": "string",
                "content": "string",
                "category": "string",
                "visibility": "string",
                "user_id": "string",
                "conversation_id": "string",
                "is_starred": "bool",
                "is_discarded": "bool",
                "created_at": "string",
                "updated_at": "string",
                "tags": "string",
                "source": "string",
                "char_len": "int64",
                "word_count": "int64",
            },
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
        description="Export Omi memories to Apache Parquet columnar datasets for AI training and fast analytics."
    )
    parser.add_argument(
        "-i",
        "--input",
        help="Input JSON file path containing Omi memories (default: stdin).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="memories.parquet",
        help="Output Parquet file path (default: memories.parquet).",
    )
    parser.add_argument(
        "--json",
        dest="json_arg",
        help="Direct JSON payload string containing memories.",
    )
    parser.add_argument(
        "-n",
        "--limit",
        type=int,
        default=None,
        help="Limit number of exported memory records.",
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
            sys.stderr.write("Waiting for JSON memories on stdin (or use -i / --json)...\n")
        raw_text = sys.stdin.read()

    # 2. Parse & normalize
    records = parse_omi_memories(raw_text)
    if args.limit and args.limit > 0:
        records = records[: args.limit]

    # 3. Schema mode
    if args.schema:
        col_dict = records_to_columnar_dict(records)
        print("Apache Parquet Inferred Schema:")
        for col_name in col_dict:
            sample_val = col_dict[col_name][0] if col_dict[col_name] else None
            sample_type = type(sample_val).__name__ if sample_val is not None else "string"
            print(f"  - {col_name:18s} ({sample_type})")
        print(f"\nTotal records: {len(records)}")
        return 0

    # 4. Write Parquet
    try:
        count, file_size, is_fallback = write_parquet_file(records, args.output, compression=args.compression)
        if is_fallback:
            print(
                f"Exported {count} memories to columnar fallback payload '{args.output}.json' "
                f"({file_size:,} bytes). Install 'pyarrow' for binary Parquet format: pip install pyarrow"
            )
        else:
            print(
                f"Successfully exported {count} memories to '{args.output}' "
                f"({file_size:,} bytes, compression: {args.compression})"
            )
        return 0
    except Exception as e:
        sys.stderr.write(f"Unexpected Error: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
