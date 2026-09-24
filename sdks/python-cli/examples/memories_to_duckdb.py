#!/usr/bin/env python3
"""Convert Omi memories JSON exports into a DuckDB SQL ingestion script.

Usage:
    # Basic export from saved memories JSON:
    python memories_to_duckdb.py memories.json -o memories.sql

    # Piped directly from omi-cli:
    omi --json memory list --limit 100 | python memories_to_duckdb.py - -o memories.sql

    # Custom table name:
    python memories_to_duckdb.py memories.json -o memories.sql --table-name my_memories

    # Multi-file deduplicated export with overwrite protection:
    python memories_to_duckdb.py day1.json day2.json -o memories.sql --force

Format:
    Generates a standards-compliant SQL script optimized for DuckDB OLAP execution:
    - Strongly typed table schema with VARCHAR, TIMESTAMP_TZ, and VARCHAR[] list types.
    - Idempotent INSERT OR REPLACE statements.
    - Sample analytical queries for category aggregation and tag unnesting.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


def sql_quote(val: Any) -> str:
    """Safely format a value as a SQL literal string."""
    if val is None:
        return "NULL"
    text = str(val).replace("'", "''")
    return f"'{text}'"


def sql_array_literal(items: Sequence[str]) -> str:
    """Format a list of strings as a DuckDB array literal ['item1', 'item2']."""
    if not items:
        return "[]"
    quoted = [sql_quote(i) for i in items]
    return f"[{', '.join(quoted)}]"


def parse_memories_data(data: Any) -> List[Dict[str, Any]]:
    """Parse raw JSON input into a list of memory dictionaries."""
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON data: {exc}") from exc
    else:
        parsed = data

    if isinstance(parsed, dict):
        items = (
            parsed.get("memories")
            or parsed.get("items")
            or parsed.get("data")
            or parsed.get("result")
            or [parsed]
        )
    elif isinstance(parsed, list):
        items = parsed
    else:
        raise ValueError("Expected a JSON object or array of memory items")

    if not isinstance(items, list):
        raise ValueError("Memory items must resolve to a list")

    records: List[Dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            records.append(item)
    return records


def format_memory_for_duckdb(item: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and normalize memory fields for DuckDB insertion."""
    raw_id = str(item.get("id") or item.get("uid") or "").strip()
    if not raw_id:
        raise ValueError("Memory record missing required 'id' field")

    content = str(item.get("content") or item.get("text") or item.get("memory") or "").strip()
    category = str(item.get("category") or item.get("type") or "general").strip()

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
        "    created_at TIMESTAMP_TZ,",
        "    updated_at TIMESTAMP_TZ",
        ");",
        "",
    ]

    for rec in normalized:
        id_val = sql_quote(rec["id"])
        content_val = sql_quote(rec["content"])
        category_val = sql_quote(rec["category"])
        tags_val = sql_array_literal(rec["tags"])
        created_val = f"TRY_CAST({sql_quote(rec['created_at'])} AS TIMESTAMP_TZ)" if rec["created_at"] else "NULL"
        updated_val = f"TRY_CAST({sql_quote(rec['updated_at'])} AS TIMESTAMP_TZ)" if rec["updated_at"] else "NULL"

        sql_lines.append(
            f"INSERT OR REPLACE INTO {table_name} (id, content, category, tags, created_at, updated_at) "
            f"VALUES ({id_val}, {content_val}, {category_val}, {tags_val}, {created_val}, {updated_val});"
        )

    sql_lines.extend([
        "",
        "-- Sample Analytical Queries:",
        f"-- 1. Memory count by category:",
        f"-- SELECT category, COUNT(*) as total FROM {table_name} GROUP BY category ORDER BY total DESC;",
        "",
        f"-- 2. Most frequent tags (unnested):",
        f"-- SELECT UNNEST(tags) as tag, COUNT(*) as count FROM {table_name} GROUP BY tag ORDER BY count DESC LIMIT 10;",
        "",
        f"-- 3. Search memory content:",
        f"-- SELECT id, content, created_at FROM {table_name} WHERE content ILIKE '%project%' ORDER BY created_at DESC;",
        "",
    ])

    return "\n".join(sql_lines), len(normalized)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi memory JSON exports to a DuckDB SQL ingestion script.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  omi --json memory list --limit 100 | python memories_to_duckdb.py - -o memories.sql
  python memories_to_duckdb.py memories.json -o memories.sql --table-name omi_memories
  python memories_to_duckdb.py m1.json m2.json -o memories.sql --force
""",
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        metavar="INPUT",
        help="One or more memory JSON files exported from 'omi --json memory list', or '-' for stdin.",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        metavar="FILE",
        help="Output .sql file path.",
    )
    parser.add_argument(
        "--table-name",
        default="memories",
        metavar="TABLE",
        help="Target table name (default: 'memories').",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite output file if it already exists.",
    )

    args = parser.parse_args()

    out_path = Path(args.output)
    if out_path.exists() and not args.force:
        print(f"Error: Destination file '{args.output}' already exists. Use --force to overwrite.", file=sys.stderr)
        sys.exit(1)

    try:
        content, count = generate_duckdb_sql(args.inputs, table_name=args.table_name)
    except (FileNotFoundError, ValueError) as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    print(f"Exported {count} memory record(s) to '{args.output}'.")


if __name__ == "__main__":
    main()
