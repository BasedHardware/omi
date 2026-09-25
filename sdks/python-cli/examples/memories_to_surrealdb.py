#!/usr/bin/env python3
"""Convert Omi memory JSON exports to a SurrealDB SurrealQL ingestion script.

Reads Omi memory JSON exports (from file paths or stdin), deduplicates by memory ID,
and generates clean, idempotent SurrealQL statements (DEFINE TABLE/FIELD/INDEX and UPSERT).

SurrealDB is an advanced multi-model database (document, graph, vector, full-text)
running embedded or in the cloud.

Zero external dependencies - uses Python 3 standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple


def surreal_quote(val: Any) -> str:
    """Format and escape a scalar value as a SurrealQL string literal."""
    if val is None:
        return "NONE"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    # Double single quotes or backslash escape single quotes for SurrealQL
    text = str(val).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{text}'"


def surreal_array_literal(items: Sequence[str]) -> str:
    """Format a sequence of strings into a SurrealQL array literal."""
    if not items:
        return "[]"
    escaped_items = ["'" + str(x).replace("\\", "\\\\").replace("'", "\\'") + "'" for x in items]
    return f"[{', '.join(escaped_items)}]"


def surreal_record_id(table_name: str, raw_id: str) -> str:
    """Format a safe record ID for SurrealDB using ⟨...⟩ wrapper if needed."""
    cleaned = str(raw_id).strip()
    # SurrealQL allows memory:⟨uuid-or-complex-id⟩
    return f"{table_name}:⟨{cleaned}⟩"


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


def format_memory_for_surreal(item: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize raw memory dictionary into canonical record schema."""
    mid = str(item.get("id") or item.get("uid") or "").strip()
    if not mid:
        raise ValueError("Memory record missing required 'id' field")

    content = ""
    structured = item.get("structured")
    if isinstance(structured, dict):
        content = structured.get("title") or structured.get("overview") or ""
    if not content:
        content = item.get("content") or item.get("text") or item.get("transcript") or ""

    category = item.get("category")
    if not category and isinstance(structured, dict):
        category = structured.get("category")

    tags: List[str] = []
    raw_tags = item.get("tags")
    if isinstance(raw_tags, list):
        tags = [str(t).strip() for t in raw_tags if str(t).strip()]
    elif isinstance(raw_tags, str) and raw_tags.strip():
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]

    visibility = item.get("visibility")

    return {
        "id": mid,
        "content": content,
        "category": category,
        "tags": tags,
        "visibility": visibility,
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }


def generate_surrealql(
    inputs: Sequence[str],
    table_name: str = "memory",
) -> Tuple[str, int]:
    """Load, deduplicate by ID, and generate SurrealQL statements."""
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

    normalized = [format_memory_for_surreal(m) for m in dedup.values()]

    sql_lines: List[str] = [
        f"-- SurrealDB Ingestion Script for Omi Memories",
        f"-- Total records: {len(normalized)}",
        "",
        f"-- Schema definitions",
        f"DEFINE TABLE IF NOT EXISTS {table_name} SCHEMALESS;",
        f"DEFINE FIELD IF NOT EXISTS content ON TABLE {table_name} TYPE string;",
        f"DEFINE FIELD IF NOT EXISTS category ON TABLE {table_name} TYPE option<string>;",
        f"DEFINE FIELD IF NOT EXISTS tags ON TABLE {table_name} TYPE array<string>;",
        f"DEFINE FIELD IF NOT EXISTS visibility ON TABLE {table_name} TYPE option<string>;",
        f"DEFINE FIELD IF NOT EXISTS created_at ON TABLE {table_name} TYPE option<datetime>;",
        f"DEFINE FIELD IF NOT EXISTS updated_at ON TABLE {table_name} TYPE option<datetime>;",
        f"DEFINE INDEX IF NOT EXISTS {table_name}_category ON TABLE {table_name} COLUMNS category;",
        "",
    ]

    for rec in normalized:
        rec_id = surreal_record_id(table_name, rec["id"])
        content_val = surreal_quote(rec["content"])
        category_val = surreal_quote(rec["category"])
        tags_val = surreal_array_literal(rec["tags"])
        vis_val = surreal_quote(rec["visibility"])
        created_val = f"type::datetime({surreal_quote(rec['created_at'])})" if rec["created_at"] else "NONE"
        updated_val = f"type::datetime({surreal_quote(rec['updated_at'])})" if rec["updated_at"] else "NONE"

        sql_lines.append(
            f"UPSERT {rec_id} SET "
            f"content = {content_val}, "
            f"category = {category_val}, "
            f"tags = {tags_val}, "
            f"visibility = {vis_val}, "
            f"created_at = {created_val}, "
            f"updated_at = {updated_val};"
        )

    sql_lines.extend([
        "",
        f"-- Sample Analytical Queries in SurrealQL:",
        f"-- 1. Count memories by category:",
        f"-- SELECT category, count() FROM {table_name} GROUP BY category;",
        "",
        f"-- 2. Find memories with specific tags:",
        f"-- SELECT * FROM {table_name} WHERE tags CONTAINS 'project';",
        "",
        f"-- 3. Full-text search content:",
        f"-- SELECT * FROM {table_name} WHERE content ~ 'meeting';",
        "",
    ])

    return "\n".join(sql_lines), len(normalized)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi memory JSON exports to a SurrealDB SurrealQL ingestion script.",
        epilog="""\
examples:
  omi --json memory list --limit 100 | python memories_to_surrealdb.py - -o memories.surql
  python memories_to_surrealdb.py export.json -o memories.surql --table-name memory
  python memories_to_surrealdb.py day1.json day2.json -o memories.surql --force
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "inputs",
        metavar="INPUT",
        nargs="+",
        help="Path(s) to Omi memory JSON file(s), or '-' to read from standard input.",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        default="-",
        help="Path to write the output .surql script (default: '-' for stdout).",
    )
    parser.add_argument(
        "--table-name",
        default="memory",
        help="Target SurrealDB table name (default: memory).",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite output file if it already exists.",
    )

    args = parser.parse_args()

    if args.output != "-":
        out_path = Path(args.output)
        if out_path.exists() and not args.force:
            sys.stderr.write(
                f"Error: Output file already exists: {args.output} (use --force to overwrite)\n"
            )
            sys.exit(1)

    try:
        sql_content, count = generate_surrealql(args.inputs, table_name=args.table_name)
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)

    if args.output == "-":
        sys.stdout.write(sql_content + "\n")
    else:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(sql_content, encoding="utf-8")
        sys.stderr.write(
            f"Successfully generated SurrealQL script: {args.output} ({count} memories)\n"
        )


if __name__ == "__main__":
    main()
