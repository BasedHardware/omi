#!/usr/bin/env python3
"""Convert OMI memory exports to ClickHouse DDL and analytical batch ingestion payloads.

Supports both standard ClickHouse SQL INSERT statements and native JSONEachRow streaming,
using ClickHouse's ReplacingMergeTree engine for deduplicated analytical queries.
Zero external dependencies.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Sequence


def escape_clickhouse_string(val: Optional[str]) -> str:
    """Escape a string for safe inclusion in ClickHouse SQL statements."""
    if val is None:
        return "''"
    # ClickHouse accepts both doubled single quotes and backslash escapes
    escaped = val.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def parse_clickhouse_datetime(dt_str: Optional[str]) -> str:
    """Normalize an ISO-8601 string to ClickHouse DateTime64 format 'YYYY-MM-DD HH:MM:SS.mmm'."""
    if not dt_str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.000")
    try:
        cleaned = dt_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.000")


def generate_clickhouse_schema() -> str:
    """Generate DDL for the omi_memories table using ReplacingMergeTree."""
    return """-- OMI Memories ClickHouse Table Definition
CREATE TABLE IF NOT EXISTS omi_memories (
    id String,
    content String,
    category LowCardinality(String),
    created_at DateTime64(3, 'UTC'),
    updated_at DateTime64(3, 'UTC'),
    manually_added UInt8 DEFAULT 0,
    deleted UInt8 DEFAULT 0,
    score Int32 DEFAULT 0,
    metadata_json String
) ENGINE = ReplacingMergeTree(updated_at)
PRIMARY KEY (id)
ORDER BY (category, id)
PARTITION BY toYYYYMM(created_at);
"""


def format_memory_for_clickhouse(memory: Dict[str, Any]) -> Dict[str, Any]:
    """Clean and normalize a raw memory dict into a typed ClickHouse record."""
    mem_id = memory.get("id") or memory.get("uid") or ""
    if not mem_id:
        raise ValueError("Memory record missing required identifier 'id'")

    content = memory.get("content") or memory.get("text") or ""
    category = memory.get("category") or "uncategorized"
    created_at = parse_clickhouse_datetime(memory.get("created_at"))
    updated_at = parse_clickhouse_datetime(memory.get("updated_at")) if memory.get("updated_at") else created_at
    manually_added = 1 if memory.get("manually_added") else 0
    deleted = 1 if memory.get("deleted") else 0

    score = memory.get("score")
    if not isinstance(score, int) or isinstance(score, bool):
        score = 0

    metadata = memory.get("metadata")
    if metadata is None:
        for field in ("structured", "source", "user_facts", "plugin_data"):
            if field in memory:
                if metadata is None:
                    metadata = {}
                metadata[field] = memory[field]

    metadata_json = json.dumps(metadata, ensure_ascii=False) if metadata else "{}"

    return {
        "id": str(mem_id),
        "content": str(content),
        "category": str(category),
        "created_at": created_at,
        "updated_at": updated_at,
        "manually_added": manually_added,
        "deleted": deleted,
        "score": score,
        "metadata_json": metadata_json,
    }


def format_sql_insert(record: Dict[str, Any]) -> str:
    """Format a normalized record as a ClickHouse SQL INSERT row."""
    id_val = escape_clickhouse_string(record["id"])
    content_val = escape_clickhouse_string(record["content"])
    cat_val = escape_clickhouse_string(record["category"])
    created_val = escape_clickhouse_string(record["created_at"])
    updated_val = escape_clickhouse_string(record["updated_at"])
    manual_val = str(record["manually_added"])
    deleted_val = str(record["deleted"])
    score_val = str(record["score"])
    meta_val = escape_clickhouse_string(record["metadata_json"])

    return f"""INSERT INTO omi_memories (
    id, content, category, created_at, updated_at, manually_added, deleted, score, metadata_json
) VALUES (
    {id_val}, {content_val}, {cat_val}, {created_val}, {updated_val}, {manual_val}, {deleted_val}, {score_val}, {meta_val}
);"""


def convert_memories_to_clickhouse(raw_data: Any, format_mode: str = "sql", with_schema: bool = True) -> str:
    """Convert input memories to ClickHouse SQL script or JSONEachRow format."""
    if isinstance(raw_data, dict):
        if "items" in raw_data and isinstance(raw_data["items"], list):
            memories = raw_data["items"]
        elif "memories" in raw_data and isinstance(raw_data["memories"], list):
            memories = raw_data["memories"]
        else:
            memories = [raw_data]
    elif isinstance(raw_data, list):
        memories = raw_data
    else:
        raise ValueError(f"Expected JSON list or object with 'items' key, got {type(raw_data).__name__}")

    records = []
    for mem in memories:
        if not isinstance(mem, dict):
            continue
        try:
            records.append(format_memory_for_clickhouse(mem))
        except Exception:
            continue

    if format_mode == "jsonl":
        lines = [json.dumps(r, ensure_ascii=False) for r in records]
        return "\n".join(lines) + ("\n" if lines else "")

    # SQL mode
    output = []
    if with_schema:
        output.append(generate_clickhouse_schema())

    for r in records:
        output.append(format_sql_insert(r))

    output.append(f"-- Transformed {len(records)} memories for ClickHouse successfully.")
    return "\n".join(output) + "\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Convert OMI memory exports to ClickHouse schema and ingestion data.")
    parser.add_argument("-i", "--input", type=Path, help="Input JSON file containing OMI memories (default: stdin)")
    parser.add_argument("-o", "--output", type=Path, help="Output file path (default: stdout)")
    parser.add_argument(
        "--format",
        choices=["sql", "jsonl"],
        default="sql",
        help="Output format: 'sql' for INSERT statements, 'jsonl' for JSONEachRow (default: sql)",
    )
    parser.add_argument("--no-schema", action="store_true", help="Omit table creation DDL in SQL mode")

    args = parser.parse_args(argv)

    if args.input:
        if not args.input.exists():
            sys.stderr.write(f"Error: input file {args.input} not found\n")
            return 1
        content_text = args.input.read_text(encoding="utf-8")
    else:
        if sys.stdin.isatty():
            sys.stderr.write("Reading OMI memories JSON from stdin...\n")
        content_text = sys.stdin.read()

    if not content_text.strip():
        sys.stderr.write("Error: empty input data\n")
        return 1

    try:
        data = json.loads(content_text)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"Error: invalid JSON input: {exc}\n")
        return 1

    try:
        result = convert_memories_to_clickhouse(data, format_mode=args.format, with_schema=not args.no_schema)
    except Exception as exc:
        sys.stderr.write(f"Error converting memories: {exc}\n")
        return 1

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding="utf-8")
        sys.stderr.write(f"Wrote ClickHouse output to {args.output}\n")
    else:
        sys.stdout.write(result)

    return 0


if __name__ == "__main__":
    sys.exit(main())
