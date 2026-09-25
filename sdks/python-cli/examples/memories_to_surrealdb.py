#!/usr/bin/env python3
"""Convert Omi memory JSON exports to a SurrealDB SurrealQL ingestion script.

Reads Omi memory JSON exports (from file paths or stdin), deduplicates by memory ID,
and generates clean, idempotent SurrealQL statements (UPSERT memory:⟨id⟩ MERGE ...).

SurrealDB is a multi-model database that integrates document, graph, and vector capabilities
into a unified SurrealQL engine.

Zero external dependencies - uses Python 3 standard library only.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


def surreal_quote(val: Any) -> str:
    """Format and escape a scalar value as a SurrealQL string literal."""
    if val is None:
        return "NONE"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    text = (
        str(val)
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
    )
    return f"'{text}'"


def surreal_datetime_literal(val: Any) -> str:
    """Format an ISO-8601 timestamp string into a SurrealDB datetime literal d'...'.

    Validates that the string conforms to ISO-8601 (handling 'Z' suffix).
    If valid, returns d'...' literal for native SurrealDB datetime storage.
    If unparseable or invalid, falls back to a plain quoted string literal
    to prevent malformed records from aborting the entire surreal import.
    Returns 'NONE' if the value is absent or empty.
    """
    if not val:
        return "NONE"
    cleaned = str(val).strip()
    if not cleaned:
        return "NONE"
    if (cleaned.startswith("'") and cleaned.endswith("'")) or (cleaned.startswith('"') and cleaned.endswith('"')):
        cleaned = cleaned[1:-1].strip()
    cleaned = cleaned.replace("'", "").replace("\\", "")
    if not cleaned:
        return "NONE"

    try:
        norm = cleaned.replace("Z", "+00:00")
        datetime.fromisoformat(norm)
        return f"d'{cleaned}'"
    except (ValueError, TypeError):
        return surreal_quote(cleaned)


def surreal_array_literal(items: Sequence[str]) -> str:
    """Format a sequence of strings into a SurrealQL array literal."""
    if not items:
        return "[]"
    escaped_items = [surreal_quote(str(x)) for x in items]
    return f"[{', '.join(escaped_items)}]"


def surreal_record_id(table_name: str, raw_id: str) -> str:
    """Format a safe record ID for SurrealDB using ⟨...⟩ wrapper if needed."""
    cleaned = str(raw_id).strip()
    if not cleaned:
        raise ValueError("Memory record missing required 'id' field")
    if "⟩" in cleaned:
        raise ValueError(f"Invalid memory record id containing literal '⟩': {raw_id}")
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

    content = str(item.get("content") or item.get("text") or item.get("transcript") or "").strip()
    structured = item.get("structured")
    if not content and isinstance(structured, dict):
        content = str(structured.get("title") or structured.get("overview") or "").strip()

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
    """Load, deduplicate by ID, and generate SurrealQL ingestion script."""
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

    lines: List[str] = [
        "OPTION IMPORT;",
        "",
        "-- SurrealDB SurrealQL Ingestion Script for Omi Memories",
        f"-- Total records: {len(normalized)}",
        f"-- Table name: {table_name}",
        "",
        "-- 1. Table schema and indexes definition (safe to run repeatedly)",
        f"DEFINE TABLE IF NOT EXISTS {table_name} SCHEMALESS;",
        f"DEFINE INDEX IF NOT EXISTS idx_{table_name}_category ON {table_name} FIELDS category;",
        f"DEFINE INDEX IF NOT EXISTS idx_{table_name}_created ON {table_name} FIELDS created_at;",
        "",
        "-- 2. Upsert memory records",
    ]

    for rec in normalized:
        rec_id = surreal_record_id(table_name, rec["id"])
        content_val = surreal_quote(rec["content"])
        category_val = surreal_quote(rec["category"])
        tags_val = surreal_array_literal(rec["tags"])
        vis_val = surreal_quote(rec["visibility"])
        created_val = surreal_datetime_literal(rec["created_at"])
        updated_val = surreal_datetime_literal(rec["updated_at"])

        fields = (
            f"{{ content: {content_val}, "
            f"category: {category_val}, "
            f"tags: {tags_val}, "
            f"visibility: {vis_val}, "
            f"created_at: {created_val}, "
            f"updated_at: {updated_val} }}"
        )
        lines.append(f"UPSERT {rec_id} MERGE {fields};")

    lines.extend(
        [
            "",
            "-- Sample Analytical Queries in SurrealQL:",
            f"-- 1. Search content: SELECT * FROM {table_name} WHERE string::contains(string::lowercase(content), 'meeting');",
            f"-- 2. Count by category: SELECT category, count() AS total FROM {table_name} GROUP BY category;",
            f"-- 3. Recent memories: SELECT * FROM {table_name} WHERE created_at > d'2026-01-01T00:00:00Z' ORDER BY created_at DESC LIMIT 10;",
            "",
        ]
    )

    return "\n".join(lines), len(normalized)


def build_parser() -> argparse.ArgumentParser:
    """Build CLI parser."""
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
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.output != "-":
        out_path = Path(args.output)
        if out_path.exists() and not args.force:
            sys.stderr.write(f"Error: Output file already exists: {args.output} (use --force to overwrite)\n")
            return 1

    try:
        sql_content, count = generate_surrealql(args.inputs, table_name=args.table_name)
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        return 1

    if args.output == "-":
        sys.stdout.write(sql_content + "\n")
    else:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(sql_content, encoding="utf-8")
        sys.stderr.write(f"Successfully generated SurrealQL script: {args.output} ({count} memories)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
