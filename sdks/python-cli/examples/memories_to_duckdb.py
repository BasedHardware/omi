#!/usr/bin/env python3
"""Convert Omi memory JSON exports to a DuckDB SQL ingestion script.

Reads Omi memory JSON exports (from file paths or stdin), deduplicates by memory ID,
and generates clean, idempotent DuckDB SQL statements (CREATE TABLE IF NOT EXISTS
and INSERT OR REPLACE INTO).

Zero external dependencies - uses Python 3 standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple


def sql_quote(val: Any) -> str:
    """Format and escape a scalar value as a DuckDB SQL literal."""
    if val is None:
        return "NULL"
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        return str(val)
    # Double single quotes for standard SQL literal escaping
    text = str(val).replace("'", "''")
    return f"'{text}'"


def sql_array_literal(items: Sequence[str]) -> str:
    """Format a sequence of strings into a DuckDB VARCHAR[] array literal."""
    if not items:
        return "[]"
    escaped_items = ["'" + str(x).replace("'", "''") + "'" for x in items]
    return f"[{', '.join(escaped_items)}]"


def parse_memories_data(raw: Any) -> List[Dict[str, Any]]:
    """Unwrap Omi memories from raw JSON input supporting common CLI shapes."""
    if isinstance(raw, str):
        data = json.loads(raw)
    else:
        data = raw

    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    elif isinstance(data, dict):
        for key in ("memories", "items", "data", "result"):
            val = data.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]
        return [data]
    return []


def format_memory_for_duckdb(item: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and normalize memory properties for DuckDB relational storage."""
    raw_id = str(item.get("id") or item.get("uid") or "").strip()
    if not raw_id:
        raw_id = str(hash(json.dumps(item, sort_keys=True)))

    content = str(item.get("content") or item.get("text") or "").strip()
    category = str(item.get("category") or "general").strip()
    visibility = str(item.get("visibility") or "").strip()

    tags_val = item.get("tags") or []
    if isinstance(tags_val, str):
        tags = [t.strip() for t in tags_val.split(",") if t.strip()]
    elif isinstance(tags_val, list):
        tags = [str(t).strip() for t in tags_val if str(t).strip()]
    else:
        tags = []

    return {
        "id": raw_id,
        "content": content,
        "category": category,
        "tags": tags,
        "visibility": visibility,
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }


def generate_duckdb_sql(
    inputs: Sequence[str],
    table_name: str = "memories",
) -> Tuple[str, int]:
    """Load, deduplicate by ID, and generate DuckDB SQL statements."""
    dedup: Dict[str, Dict[str, Any]] = {}

    for inp in inputs:
        if inp == "-":
            raw_content = sys.stdin.read()
        else:
            p = Path(inp)
            if not p.is_file():
                raise FileNotFoundError(f"Input file not found: {inp}")
            raw_content = p.read_bytes().decode("utf-8-sig")

        memories = parse_memories_data(raw_content)
        for m in memories:
            mid = str(m.get("id") or m.get("uid") or "").strip()
            if mid:
                dedup[mid] = m

    normalized = [format_memory_for_duckdb(m) for m in dedup.values()]

    sql_lines: List[str] = [
        f"-- DuckDB Ingestion Script for Omi Memories",
        f"-- Generated records: {len(normalized)}",
        "",
        f"CREATE TABLE IF NOT EXISTS {table_name} (",
        "    id VARCHAR PRIMARY KEY,",
        "    content TEXT NOT NULL,",
        "    category VARCHAR,",
        "    tags VARCHAR[],",
        "    visibility VARCHAR,",
        "    created_at TIMESTAMPTZ,",
        "    updated_at TIMESTAMPTZ",
        ");",
        "",
    ]

    for rec in normalized:
        id_val = sql_quote(rec["id"])
        content_val = sql_quote(rec["content"])
        category_val = sql_quote(rec["category"])
        tags_val = sql_array_literal(rec["tags"])
        vis_val = sql_quote(rec["visibility"])
        created_val = f"TRY_CAST({sql_quote(rec['created_at'])} AS TIMESTAMPTZ)" if rec["created_at"] else "NULL"
        updated_val = f"TRY_CAST({sql_quote(rec['updated_at'])} AS TIMESTAMPTZ)" if rec["updated_at"] else "NULL"

        sql_lines.append(
            f"INSERT OR REPLACE INTO {table_name} (id, content, category, tags, visibility, created_at, updated_at) "
            f"VALUES ({id_val}, {content_val}, {category_val}, {tags_val}, {vis_val}, {created_val}, {updated_val});"
        )

    sql_lines.extend([
        "",
        "-- Sample Analytical Queries:",
        f"-- 1. Memory count by category:",
        f"-- SELECT category, COUNT(*) as total FROM {table_name} GROUP BY category ORDER BY total DESC;",
        "",
        f"-- 2. Most frequent tags (unnested):",
        f"-- SELECT tag, COUNT(*) as count FROM (SELECT UNNEST(tags) as tag FROM {table_name}) GROUP BY tag ORDER BY count DESC LIMIT 10;",
        "",
        f"-- 3. Search memory content:",
        f"-- SELECT id, content, created_at FROM {table_name} WHERE content ILIKE '%project%' ORDER BY created_at DESC;",
        "",
    ])

    return "\n".join(sql_lines), len(normalized)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi memory JSON exports to a DuckDB SQL ingestion script.",
        epilog="Example: omi --json memory list --limit 100 | python memories_to_duckdb.py - -o memories.sql",
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        metavar="INPUT",
        help="One or more JSON files exported from 'omi memory list', or '-' for stdin",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output",
        default=None,
        help="Destination SQL file path (default: write to stdout)",
    )
    parser.add_argument(
        "--table-name",
        dest="table_name",
        default="memories",
        help="DuckDB target table name (default: memories)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing output file without prompting",
    )

    args = parser.parse_args()

    out_path = Path(args.output) if args.output else None
    if out_path and out_path.exists() and not args.force:
        print(f"Error: Output file already exists: {out_path} (use --force to overwrite)", file=sys.stderr)
        sys.exit(1)

    try:
        sql_content, count = generate_duckdb_sql(args.inputs, table_name=args.table_name)
    except Exception as exc:
        print(f"Error during DuckDB SQL generation: {exc}", file=sys.stderr)
        sys.exit(1)

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(sql_content, encoding="utf-8")
        print(f"Successfully generated DuckDB SQL ingestion script: {out_path} ({count} memories)")
    else:
        sys.stdout.write(sql_content + "\n")


if __name__ == "__main__":
    main()
