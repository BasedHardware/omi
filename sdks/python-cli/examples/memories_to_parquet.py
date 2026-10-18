#!/usr/bin/env python3
"""Convert Omi memory JSON exports to an Apache Parquet dataset for DuckDB,
Polars, Pandas, and Spark analytics.

See memories_to_parquet.md for the full recipe. Requires ``pyarrow``
(``pip install pyarrow``) — Parquet is a binary columnar format, not
something the stdlib emits.

Usage:
    omi --json memory list > memories.json
    python memories_to_parquet.py memories.json [page2.json ...] -o memories.parquet

    duckdb -c "SELECT category, COUNT(*) FROM 'memories.parquet' GROUP BY 1"
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pyarrow as pa
import pyarrow.parquet as pq

ENVELOPE_KEYS = ("memories", "items", "data")

SCHEMA = pa.schema(
    [
        ("id", pa.string()),
        ("content", pa.string()),
        ("category", pa.string()),
        ("tags", pa.list_(pa.string())),
        ("visibility", pa.string()),
        ("manually_added", pa.bool_()),
        ("reviewed", pa.bool_()),
        ("app_id", pa.string()),
        ("created_at", pa.timestamp("ms", tz="UTC")),
        ("updated_at", pa.timestamp("ms", tz="UTC")),
    ]
)


def to_ts(value: Any) -> Optional[datetime]:
    """ISO-8601 → aware UTC datetime for timestamp(ms, UTC); None if unusable."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_text(value: Any) -> Optional[str]:
    """Loosely typed field → str; None → NULL."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)


def to_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    low = str(value).strip().lower()
    if low in ("true", "yes", "1", "t"):
        return True
    if low in ("false", "no", "0", "f"):
        return False
    return None


def to_tags(value: Any) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(t) for t in value if t is not None]
    return [str(value)]


def normalize(item: Dict[str, Any]) -> Dict[str, Any]:
    """Project a raw memory onto the Parquet schema."""
    return {
        "id": to_text(item.get("id") or item.get("memory_id")),
        "content": to_text(item.get("content") or item.get("text") or item.get("title")),
        "category": to_text(item.get("category")),
        "tags": to_tags(item.get("tags")),
        "visibility": to_text(item.get("visibility")),
        "manually_added": to_bool(item.get("manually_added")),
        "reviewed": to_bool(item.get("reviewed")),
        "app_id": to_text(item.get("app_id") or item.get("source_app")),
        "created_at": to_ts(item.get("created_at")),
        "updated_at": to_ts(item.get("updated_at")),
    }


def extract_memories(data: Any) -> List[Any]:
    """Unwrap memories from bare lists or wrapped envelope dictionaries."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ENVELOPE_KEYS:
            if isinstance(data.get(key), list):
                return data[key]
        return [data]
    return []


def rows(sources: List[str]) -> List[Dict[str, Any]]:
    """Load all pages, dedupe by id (first wins)."""
    seen = set()
    out = []
    for src in sources:
        raw = json.loads(Path(src).read_bytes().decode("utf-8-sig"))
        for item in extract_memories(raw):
            if not isinstance(item, dict):
                continue
            mid = str(item.get("id") or item.get("memory_id") or "")
            if mid and mid in seen:
                continue
            if mid:
                seen.add(mid)
            row = normalize(item)
            if row["id"]:
                out.append(row)
    return out


def convert(sources: List[str], destination: str) -> int:
    """Write the Parquet file; return the row count."""
    rs = rows(sources)
    out = Path(destination)
    if ".." in out.parts:
        raise ValueError(f"Refusing '..' in output path {destination}")
    if out.exists():
        raise FileExistsError(f"Refusing to overwrite existing {out}")

    # Write next to the destination and rename, so a failed write leaves no
    # truncated parquet file behind.
    partial = out.with_name(out.name + ".partial")
    try:
        table = pa.Table.from_pylist(rs, schema=SCHEMA)
        pq.write_table(table, partial, compression="snappy")
        partial.replace(out)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return len(rs)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Convert Omi memory JSON exports to Apache Parquet.")
    ap.add_argument("inputs", nargs="+", help="JSON export files")
    ap.add_argument("-o", "--output", required=True, help="Destination .parquet path")
    args = ap.parse_args(argv)
    try:
        n = convert(args.inputs, args.output)
    except (ValueError, FileExistsError, OSError, json.JSONDecodeError) as e:
        print(f"memories_to_parquet: {e}", file=sys.stderr)
        return 2
    print(f"memories_to_parquet: wrote {n} row(s) to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
