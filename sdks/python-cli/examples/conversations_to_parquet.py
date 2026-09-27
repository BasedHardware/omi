#!/usr/bin/env python3
"""
Convert Omi conversation-list JSON exports to Apache Parquet dataset files.

Usage:
    # From authenticated omi CLI stream:
    omi --json conversation list --include-transcript --limit 200 | python conversations_to_parquet.py -o conversations.parquet

    # From saved JSON files:
    python conversations_to_parquet.py conversations.json -o conversations.parquet

    # Multiple files combined into a single dataset:
    python conversations_to_parquet.py page1.json page2.json -o conversations.parquet

Features:
- Full transcript extraction from transcript_segments with speaker attribution
- Clean duration_seconds derivation from finished_at - started_at (handles ISO strings and timestamps)
- Action item description extraction from structured API objects or plain strings
- PyArrow columnar dataset conversion with Snappy, Gzip, or uncompressed output
- Pure-Python fallback when pyarrow is not installed (emits valid columnar JSON)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

try:
    import pyarrow as pa
    import pyarrow.parquet as pq

    HAS_PYARROW = True
except ImportError:
    HAS_PYARROW = False


def normalize_iso_timestamp(val: Any) -> Optional[str]:
    """Normalise an ISO string or epoch timestamp to UTC 'YYYY-MM-DDTHH:MM:SSZ' format."""
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        try:
            dt = datetime.fromtimestamp(val, tz=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return None
    if isinstance(val, str):
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc)
            else:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return val
    return None


def calculate_duration_seconds(
    started_at: Any,
    finished_at: Any,
    fallback_duration: Any = None,
) -> float:
    """Derive duration in seconds from finished_at - started_at or fallback."""
    if fallback_duration is not None:
        try:
            dur = float(fallback_duration)
            if dur > 0:
                return round(dur, 2)
        except (ValueError, TypeError):
            pass

    def to_datetime(v: Any) -> Optional[datetime]:
        if v is None or v == "":
            return None
        if isinstance(v, (int, float)):
            try:
                return datetime.fromtimestamp(v, tz=timezone.utc)
            except Exception:
                return None
        if isinstance(v, str):
            try:
                dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception:
                return None
        return None

    dt_start = to_datetime(started_at)
    dt_end = to_datetime(finished_at)
    if dt_start and dt_end:
        delta = (dt_end - dt_start).total_seconds()
        if delta >= 0:
            return round(delta, 2)
    return 0.0


def extract_segments_data(segments: Optional[Sequence[Dict[str, Any]]]) -> Tuple[str, int, int]:
    """
    Extract formatted multi-speaker transcript, total segment count, and unique speaker count.
    Returns: (full_transcript_str, segment_count, unique_speaker_count)
    """
    if not segments:
        return "", 0, 0

    lines: List[str] = []
    speakers = set()
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        speaker = str(seg.get("speaker") or f"SPEAKER_{seg.get('speaker_id', 0)}").strip()
        speakers.add(speaker)
        lines.append(f"{speaker}: {text}")

    return "\n".join(lines), len(lines), len(speakers)


def extract_action_items(action_items: Any) -> List[str]:
    """Extract string descriptions from API action item dicts or strings."""
    if not action_items:
        return []
    result: List[str] = []
    if isinstance(action_items, list):
        for item in action_items:
            if isinstance(item, dict):
                desc = item.get("description") or item.get("text") or ""
                if desc:
                    result.append(str(desc).strip())
            elif isinstance(item, str) and item.strip():
                result.append(item.strip())
            elif item is not None:
                result.append(str(item).strip())
    return result


def normalize_conversation_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Transform a raw Omi conversation JSON document into a flat columnar record."""
    conv_id = str(raw.get("id") or "").strip()
    structured = raw.get("structured") or {}
    if not isinstance(structured, dict):
        structured = {}

    title = str(structured.get("title") or raw.get("title") or "").strip()
    overview = str(structured.get("overview") or "").strip()
    category = str(structured.get("category") or "other").strip().lower()

    action_items_list = extract_action_items(structured.get("action_items"))
    action_items_json = json.dumps(action_items_list, ensure_ascii=False)

    source = str(raw.get("source") or "omi").strip().lower()
    language = str(raw.get("language") or "en").strip().lower()
    user_id = str(raw.get("user_id") or "").strip()

    started_at = normalize_iso_timestamp(raw.get("started_at") or raw.get("startedAt"))
    finished_at = normalize_iso_timestamp(raw.get("finished_at") or raw.get("finishedAt"))
    created_at = normalize_iso_timestamp(raw.get("created_at") or raw.get("createdAt"))
    updated_at = normalize_iso_timestamp(raw.get("updated_at") or raw.get("updatedAt"))

    duration_seconds = calculate_duration_seconds(
        raw.get("started_at") or raw.get("startedAt"),
        raw.get("finished_at") or raw.get("finishedAt"),
        raw.get("duration"),
    )

    is_discarded = bool(raw.get("discarded", False))

    segments = raw.get("transcript_segments") or []
    full_transcript, num_segments, num_speakers = extract_segments_data(segments)

    # Fallback to top-level transcript text if transcript_segments was not fetched
    if not full_transcript and raw.get("transcript"):
        full_transcript = str(raw.get("transcript")).strip()

    char_len = len(full_transcript)
    word_count = len(full_transcript.split()) if full_transcript else 0

    return {
        "id": conv_id,
        "title": title,
        "overview": overview,
        "category": category,
        "source": source,
        "language": language,
        "user_id": user_id,
        "started_at": started_at or "",
        "finished_at": finished_at or "",
        "created_at": created_at or "",
        "updated_at": updated_at or "",
        "duration_seconds": float(duration_seconds),
        "is_discarded": is_discarded,
        "action_items": action_items_json,
        "num_action_items": len(action_items_list),
        "full_transcript": full_transcript,
        "num_segments": int(num_segments),
        "num_speakers": int(num_speakers),
        "char_len": int(char_len),
        "word_count": int(word_count),
    }


def parse_omi_conversations(content_or_obj: Union[str, bytes, List[Any], Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Parse JSON or native Python object into list of conversation dicts."""
    if isinstance(content_or_obj, (str, bytes)):
        content_str = content_or_obj.decode("utf-8") if isinstance(content_or_obj, bytes) else content_or_obj
        stripped = content_str.strip().lstrip("\ufeff")
        if not stripped:
            return []
        data = json.loads(stripped)
    else:
        data = content_or_obj

    if isinstance(data, list):
        return [c for c in data if isinstance(c, dict)]
    elif isinstance(data, dict):
        for key in ("conversations", "items", "data", "results"):
            if isinstance(data.get(key), list):
                return [c for c in data[key] if isinstance(c, dict)]
        if "id" in data:
            return [data]
    return []


def records_to_columnar_dict(records: Sequence[Dict[str, Any]]) -> Dict[str, List[Any]]:
    """Convert sequence of normalized record dictionaries into columnar arrays."""
    columns: Dict[str, List[Any]] = {
        "id": [],
        "title": [],
        "overview": [],
        "category": [],
        "source": [],
        "language": [],
        "user_id": [],
        "started_at": [],
        "finished_at": [],
        "created_at": [],
        "updated_at": [],
        "duration_seconds": [],
        "is_discarded": [],
        "action_items": [],
        "num_action_items": [],
        "full_transcript": [],
        "num_segments": [],
        "num_speakers": [],
        "char_len": [],
        "word_count": [],
    }

    for r in records:
        for k in columns:
            columns[k].append(r.get(k))

    return columns


def build_pyarrow_table(records: Sequence[Dict[str, Any]]) -> "pa.Table":
    """Build a strongly-typed Apache Arrow Table from normalized records."""
    if not HAS_PYARROW:
        raise ImportError("pyarrow is required to build an Arrow Table.")

    cols = records_to_columnar_dict(records)

    schema = pa.schema(
        [
            pa.field("id", pa.string(), nullable=False),
            pa.field("title", pa.string(), nullable=True),
            pa.field("overview", pa.string(), nullable=True),
            pa.field("category", pa.string(), nullable=True),
            pa.field("source", pa.string(), nullable=True),
            pa.field("language", pa.string(), nullable=True),
            pa.field("user_id", pa.string(), nullable=True),
            pa.field("started_at", pa.string(), nullable=True),
            pa.field("finished_at", pa.string(), nullable=True),
            pa.field("created_at", pa.string(), nullable=True),
            pa.field("updated_at", pa.string(), nullable=True),
            pa.field("duration_seconds", pa.float64(), nullable=False),
            pa.field("is_discarded", pa.bool_(), nullable=False),
            pa.field("action_items", pa.string(), nullable=True),
            pa.field("num_action_items", pa.int32(), nullable=False),
            pa.field("full_transcript", pa.string(), nullable=True),
            pa.field("num_segments", pa.int32(), nullable=False),
            pa.field("num_speakers", pa.int32(), nullable=False),
            pa.field("char_len", pa.int32(), nullable=False),
            pa.field("word_count", pa.int32(), nullable=False),
        ]
    )

    arrays = [
        pa.array(cols["id"], type=pa.string()),
        pa.array(cols["title"], type=pa.string()),
        pa.array(cols["overview"], type=pa.string()),
        pa.array(cols["category"], type=pa.string()),
        pa.array(cols["source"], type=pa.string()),
        pa.array(cols["language"], type=pa.string()),
        pa.array(cols["user_id"], type=pa.string()),
        pa.array(cols["started_at"], type=pa.string()),
        pa.array(cols["finished_at"], type=pa.string()),
        pa.array(cols["created_at"], type=pa.string()),
        pa.array(cols["updated_at"], type=pa.string()),
        pa.array(cols["duration_seconds"], type=pa.float64()),
        pa.array(cols["is_discarded"], type=pa.bool_()),
        pa.array(cols["action_items"], type=pa.string()),
        pa.array(cols["num_action_items"], type=pa.int32()),
        pa.array(cols["full_transcript"], type=pa.string()),
        pa.array(cols["num_segments"], type=pa.int32()),
        pa.array(cols["num_speakers"], type=pa.int32()),
        pa.array(cols["char_len"], type=pa.int32()),
        pa.array(cols["word_count"], type=pa.int32()),
    ]

    return pa.Table.from_arrays(arrays, schema=schema)


def write_parquet_file(
    records: Sequence[Dict[str, Any]],
    output_path: Union[str, Path],
    compression: str = "snappy",
) -> Tuple[int, int, bool]:
    """
    Write records to Apache Parquet file.
    Returns: (record_count, file_size_bytes, is_fallback)
    """
    target = Path(output_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    if HAS_PYARROW:
        try:
            table = build_pyarrow_table(records)
            comp = None if compression.lower() == "none" else compression.lower()
            pq.write_table(table, str(target), compression=comp)
            return len(records), target.stat().st_size, False
        except ImportError:
            pass

    # Fallback to columnar json format
    fallback_path = target.with_suffix(target.suffix + ".json")
    payload = {
        "format": "columnar_parquet_fallback",
        "num_rows": len(records),
        "columns": records_to_columnar_dict(records),
    }
    fallback_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return len(records), fallback_path.stat().st_size, True


def inspect_parquet_file(file_path: Union[str, Path]) -> Dict[str, Any]:
    """Inspect schema and row count of an exported Parquet file."""
    if not HAS_PYARROW:
        raise ImportError("pyarrow is required to inspect Parquet metadata.")
    target = Path(file_path).resolve()
    parquet_file = pq.ParquetFile(str(target))
    meta = parquet_file.metadata
    schema = parquet_file.schema
    return {
        "num_rows": meta.num_rows,
        "num_columns": meta.num_columns,
        "columns": [schema.names[i] for i in range(len(schema.names))],
        "serialized_size": meta.serialized_size,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi conversation-list JSON exports to Apache Parquet dataset files."
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help="Input JSON file(s). If omitted or '-', reads JSON from standard input.",
    )
    parser.add_argument(
        "-i",
        "--input",
        dest="flag_input",
        help="Single input file path (alias).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="conversations.parquet",
        help="Destination Parquet filepath (default: conversations.parquet).",
    )
    parser.add_argument(
        "-c",
        "--compression",
        default="snappy",
        choices=["snappy", "gzip", "none"],
        help="Compression codec (default: snappy).",
    )
    parser.add_argument(
        "-n",
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of records to export.",
    )
    parser.add_argument(
        "--schema",
        action="store_true",
        help="Print the inferred Parquet schema and exit.",
    )

    args = parser.parse_args(argv)

    raw_items: List[Dict[str, Any]] = []

    # Gather inputs
    input_paths = list(args.inputs)
    if args.flag_input:
        input_paths.insert(0, args.flag_input)

    if not input_paths or input_paths == ["-"]:
        # Read from stdin
        try:
            content = sys.stdin.read()
            raw_items = parse_omi_conversations(content)
        except Exception as e:
            sys.stderr.write(f"Error reading JSON from stdin: {e}\n")
            return 1
    else:
        for p in input_paths:
            path_obj = Path(p)
            if not path_obj.exists():
                sys.stderr.write(f"Error: input file does not exist: {p}\n")
                return 1
            try:
                items = parse_omi_conversations(path_obj.read_bytes())
                raw_items.extend(items)
            except Exception as e:
                sys.stderr.write(f"Error reading {p}: {e}\n")
                return 1

    if args.limit and args.limit > 0:
        raw_items = raw_items[: args.limit]

    normalized = [normalize_conversation_record(r) for r in raw_items]

    if args.schema:
        print("Apache Parquet Inferred Schema for Conversations:")
        for field, sample_val in (
            normalized[0] if normalized else normalize_conversation_record({})
        ).items():
            print(f"  - {field}: {type(sample_val).__name__}")
        return 0

    count, size, is_fallback = write_parquet_file(
        normalized,
        args.output,
        compression=args.compression,
    )

    if is_fallback:
        print(
            f"Wrote {count} conversation(s) to {args.output}.json (columnar JSON fallback; install pyarrow for binary Parquet)."
        )
    else:
        print(
            f"Successfully exported {count} conversation(s) to {args.output} ({size:,} bytes, codec: {args.compression})."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
