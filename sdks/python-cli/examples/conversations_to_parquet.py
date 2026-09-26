#!/usr/bin/env python3
"""
conversations_to_parquet.py — Export Omi conversations to Apache Parquet columnar datasets.

Parquet is the industry-standard columnar storage format optimized for:
  - LLM instruction tuning and dialogue dataset training (Hugging Face Datasets)
  - Ultra-fast analytical SQL queries via DuckDB, Polars, and Apache Arrow
  - High-ratio compression (Snappy, Zstandard, Gzip) and predicate pushdown
  - Seamless ingestion into modern AI data lakes and cloud warehouses

Usage:
  omi --json conversation list --include-transcript --limit 200 | python conversations_to_parquet.py -o conversations.parquet
  python conversations_to_parquet.py -i export.json -o conversations.parquet --compression zstd
  python conversations_to_parquet.py --json '[{"id": "conv_1", "title": "Sample"}]' --schema
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

PARQUET_TYPE_MAP = {
    "id": "string",
    "title": "string",
    "overview": "string",
    "category": "string",
    "language": "string",
    "source": "string",
    "created_at": "string",
    "updated_at": "string",
    "started_at": "string",
    "finished_at": "string",
    "duration_seconds": "float64",
    "num_segments": "int64",
    "num_speakers": "int64",
    "full_transcript": "string",
    "action_items": "string",
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


def compute_duration_seconds(
    started_at_str: Optional[str],
    finished_at_str: Optional[str],
    explicit_duration: Any = None,
) -> float:
    """Derive duration in seconds from finished_at - started_at timestamps, or fallback to explicit duration."""
    if explicit_duration is not None:
        try:
            return max(0.0, float(explicit_duration))
        except (ValueError, TypeError):
            pass

    if not started_at_str or not finished_at_str:
        return 0.0

    try:
        dt_start = datetime.datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
        dt_finish = datetime.datetime.fromisoformat(finished_at_str.replace("Z", "+00:00"))
        delta = (dt_finish - dt_start).total_seconds()
        return max(0.0, float(delta))
    except Exception:
        return 0.0


def extract_segments_data(segments: Any) -> Tuple[str, int, int]:
    """
    Extract full transcript text, number of segments, and distinct speakers count
    from raw transcript segments.
    Returns (full_transcript, num_segments, num_speakers).
    """
    if not isinstance(segments, list) or not segments:
        return "", 0, 0

    transcript_parts: List[str] = []
    speakers_set = set()

    for seg in segments:
        if not isinstance(seg, dict):
            continue
        text = str(seg.get("text") or "").strip()
        speaker = str(seg.get("speaker") or seg.get("speaker_id") or "UNKNOWN").strip()
        if speaker:
            speakers_set.add(speaker)
        if text:
            transcript_parts.append(f"{speaker}: {text}" if speaker != "UNKNOWN" else text)

    full_transcript = "\n".join(transcript_parts)
    return full_transcript, len(segments), len(speakers_set)


def extract_action_item_text(item: Any) -> str:
    """Extract clean text description from an action item string or API object shape."""
    if isinstance(item, dict):
        return str(item.get("description") or item.get("title") or item.get("content") or "").strip()
    return str(item).strip()


def normalize_conversation_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Flatten and normalize a raw Omi conversation dictionary into a typed Parquet row schema
    matching the official omi_cli.models.Conversation model.
    """
    conv_id = str(raw.get("id") or "").strip()
    source = str(raw.get("source") or "omi").strip()
    language = str(raw.get("language") or "en").strip().lower()

    structured = raw.get("structured") if isinstance(raw.get("structured"), dict) else {}
    title = str(structured.get("title") or raw.get("title") or "Untitled Conversation").strip()
    overview = str(structured.get("overview") or structured.get("summary") or raw.get("summary") or "").strip()
    category = str(structured.get("category") or raw.get("category") or "other").strip().lower()

    action_items_raw = structured.get("action_items") or raw.get("action_items") or []
    if isinstance(action_items_raw, list):
        action_item_strings = [extract_action_item_text(a) for a in action_items_raw if extract_action_item_text(a)]
        action_items_json = json.dumps(action_item_strings, ensure_ascii=False)
    else:
        text = extract_action_item_text(action_items_raw)
        action_items_json = json.dumps([text] if text else [], ensure_ascii=False)

    created_at = normalize_iso_timestamp(raw.get("created_at") or raw.get("createdAt"))
    updated_at = normalize_iso_timestamp(raw.get("updated_at") or raw.get("updatedAt"))
    started_at = normalize_iso_timestamp(raw.get("started_at") or raw.get("startedAt") or created_at)
    finished_at = normalize_iso_timestamp(raw.get("finished_at") or raw.get("finishedAt"))

    duration_sec = compute_duration_seconds(started_at, finished_at, explicit_duration=raw.get("duration"))

    segments = raw.get("transcript_segments") or raw.get("segments") or []
    full_transcript, num_segments, num_speakers = extract_segments_data(segments)

    char_len = len(full_transcript)
    word_count = len(full_transcript.split()) if full_transcript else 0

    return {
        "id": conv_id,
        "title": title,
        "overview": overview,
        "category": category,
        "language": language,
        "source": source,
        "created_at": created_at,
        "updated_at": updated_at,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": duration_sec,
        "num_segments": num_segments,
        "num_speakers": num_speakers,
        "full_transcript": full_transcript,
        "action_items": action_items_json,
        "char_len": char_len,
        "word_count": word_count,
    }


def parse_omi_conversations(input_data: Union[str, bytes, List[Any], Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Parse raw JSON input (or python objects) into a list of normalized conversation dicts."""
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
        if "conversations" in data and isinstance(data["conversations"], list):
            raw_list = [item for item in data["conversations"] if isinstance(item, dict)]
        elif "items" in data and isinstance(data["items"], list):
            raw_list = [item for item in data["items"] if isinstance(item, dict)]
        elif "data" in data and isinstance(data["data"], list):
            raw_list = [item for item in data["data"] if isinstance(item, dict)]
        elif "id" in data or "structured" in data or "transcript_segments" in data:
            raw_list = [data]

    normalized = [normalize_conversation_record(r) for r in raw_list]
    return [r for r in normalized if r["id"] or r["title"]]


def records_to_columnar_dict(records: List[Dict[str, Any]]) -> Dict[str, List[Any]]:
    """Convert a row-oriented list of dicts into columnar arrays for Apache Parquet."""
    columns: Dict[str, List[Any]] = {k: [] for k in PARQUET_TYPE_MAP}
    for r in records:
        for k in columns:
            columns[k].append(r.get(k))
    return columns


def build_pyarrow_table(records: List[Dict[str, Any]]) -> Any:
    """Build a strongly-typed pyarrow.Table from normalized conversation records."""
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
            ("title", pa.string()),
            ("overview", pa.string()),
            ("category", pa.string()),
            ("language", pa.string()),
            ("source", pa.string()),
            ("created_at", pa.string()),
            ("updated_at", pa.string()),
            ("started_at", pa.string()),
            ("finished_at", pa.string()),
            ("duration_seconds", pa.float64()),
            ("num_segments", pa.int64()),
            ("num_speakers", pa.int64()),
            ("full_transcript", pa.string()),
            ("action_items", pa.string()),
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
    Write normalized conversation records to an Apache Parquet file.
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
        description="Export Omi conversations to Apache Parquet columnar datasets for AI model training and analytics."
    )
    parser.add_argument(
        "-i",
        "--input",
        help="Input JSON file path containing Omi conversations (default: stdin).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="conversations.parquet",
        help="Output Parquet file path (default: conversations.parquet).",
    )
    parser.add_argument(
        "--json",
        dest="json_arg",
        help="Direct JSON payload string containing conversations.",
    )
    parser.add_argument(
        "-n",
        "--limit",
        type=int,
        default=None,
        help="Limit number of exported conversation records.",
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
            sys.stderr.write("Waiting for JSON conversations on stdin (or use -i / --json)...\n")
        raw_text = sys.stdin.read()

    # 2. Parse & normalize
    records = parse_omi_conversations(raw_text)
    if args.limit and args.limit > 0:
        records = records[: args.limit]

    # 3. Schema mode
    if args.schema:
        print("Apache Parquet Inferred Schema for Conversations:")
        for col_name, parquet_type in PARQUET_TYPE_MAP.items():
            print(f"  - {col_name:18s} ({parquet_type})")
        print(f"\nTotal records: {len(records)}")
        return 0

    # 4. Write Parquet
    try:
        count, file_size, is_fallback = write_parquet_file(records, args.output, compression=args.compression)
        if is_fallback:
            print(
                f"Exported {count} conversations to columnar fallback payload '{args.output}.json' "
                f"({file_size:,} bytes). Install 'pyarrow' for binary Parquet format: pip install pyarrow"
            )
        else:
            print(
                f"Successfully exported {count} conversations to '{args.output}' "
                f"({file_size:,} bytes, compression: {args.compression})"
            )
        return 0
    except Exception as e:
        sys.stderr.write(f"Unexpected Error: {e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
