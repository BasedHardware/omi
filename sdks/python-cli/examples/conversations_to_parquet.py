#!/usr/bin/env python3
"""Convert Omi conversation JSON exports to an Apache Parquet dataset for
DuckDB, Polars, Pandas, and Spark analytics.

See conversations_to_parquet.md for the full recipe. Requires ``pyarrow``
(``pip install pyarrow``) — Parquet is a binary columnar format, not
something the stdlib emits.

Usage:
    omi --json conversation list --limit 200 > conversations.json
    python conversations_to_parquet.py conversations.json [page2.json ...] -o conversations.parquet

    duckdb -c "SELECT category, COUNT(*) FROM 'conversations.parquet' GROUP BY 1"
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pyarrow as pa
import pyarrow.parquet as pq

ENVELOPE_KEYS = ("conversations", "items", "data", "results")

SCHEMA = pa.schema(
    [
        ("id", pa.string()),
        ("title", pa.string()),
        ("category", pa.string()),
        ("overview", pa.string()),
        ("source", pa.string()),
        ("language", pa.string()),
        ("started_at", pa.timestamp("ms", tz="UTC")),
        ("finished_at", pa.timestamp("ms", tz="UTC")),
        ("duration_minutes", pa.float64()),
        ("action_items_count", pa.int64()),
        ("transcript_segment_count", pa.int64()),
        ("raw_json", pa.string()),
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
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)


def count_list(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def normalize(item: Dict[str, Any]) -> Dict[str, Any]:
    """Project a raw conversation onto the Parquet schema."""
    structured = item.get("structured") if isinstance(item.get("structured"), dict) else {}
    started, finished = to_ts(item.get("started_at")), to_ts(item.get("finished_at"))
    duration = None
    if started is not None and finished is not None and finished >= started:
        duration = round((finished - started).total_seconds() / 60, 2)
    return {
        "id": to_text(item.get("id") or item.get("conversation_id")),
        "title": to_text(item.get("title") or structured.get("title")),
        "category": to_text(item.get("category") or structured.get("category")),
        "overview": to_text(item.get("overview") or structured.get("overview")),
        "source": to_text(item.get("source") or "omi"),
        "language": to_text(item.get("language")),
        "started_at": started,
        "finished_at": finished,
        "duration_minutes": duration,
        "action_items_count": count_list(item.get("action_items")),
        "transcript_segment_count": count_list(item.get("transcript_segments") or item.get("transcript")),
        "raw_json": json.dumps(item, ensure_ascii=False),
    }


def extract_conversations(data: Any) -> List[Any]:
    """Unwrap conversations from bare lists or wrapped envelope dictionaries."""
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
        for item in extract_conversations(raw):
            if not isinstance(item, dict):
                continue
            cid = str(item.get("id") or item.get("conversation_id") or "")
            if cid and cid in seen:
                continue
            if cid:
                seen.add(cid)
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
    ap = argparse.ArgumentParser(description="Convert Omi conversation JSON exports to Apache Parquet.")
    ap.add_argument("inputs", nargs="+", help="JSON export files")
    ap.add_argument("-o", "--output", required=True, help="Destination .parquet path")
    args = ap.parse_args(argv)
    try:
        n = convert(args.inputs, args.output)
    except (ValueError, FileExistsError, OSError, json.JSONDecodeError) as e:
        print(f"conversations_to_parquet: {e}", file=sys.stderr)
        return 2
    print(f"conversations_to_parquet: wrote {n} row(s) to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
