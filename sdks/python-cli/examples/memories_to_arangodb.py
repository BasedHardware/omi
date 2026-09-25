#!/usr/bin/env python3
"""Convert Omi memory JSON exports to an ArangoDB AQL ingestion script.

Reads Omi memory JSON exports (from file paths or stdin), deduplicates by memory ID,
and generates clean, idempotent ArangoDB AQL statements (UPSERT ... INSERT ... UPDATE ... IN collection).

ArangoDB is a native multi-model database supporting graph, document, and search queries
in a single core engine using AQL (ArangoDB Query Language).

Zero external dependencies - uses Python 3 standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


def aql_quote(val: Any) -> str:
    """Format and escape a scalar value as an AQL literal.

    Escapes backslashes, single quotes, newlines, and control characters
    to prevent syntax errors or unterminated string literals in ArangoDB.
    """
    if val is None:
        return "null"
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


def aql_array_literal(items: Sequence[str]) -> str:
    """Format a sequence of strings into an AQL array literal."""
    if not items:
        return "[]"
    escaped_items = [aql_quote(str(x)) for x in items]
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


def format_memory_for_arango(item: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize raw memory dictionary into canonical ArangoDB record schema."""
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


def generate_aql(
    inputs: Sequence[str],
    collection_name: str = "memories",
) -> Tuple[str, int]:
    """Load, deduplicate by ID, and generate ArangoDB AQL ingestion statements.

    Note: AQL statements do NOT use semicolons as statement terminators.
    Each statement is emitted on its own line for individual execution via
    ArangoShell (db._query) or batch runners.
    """
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

    normalized = [format_memory_for_arango(m) for m in dedup.values()]

    aql_lines: List[str] = [
        "// ArangoDB AQL Ingestion Script for Omi Memories",
        f"// Total records: {len(normalized)}",
        f"// Target collection: {collection_name}",
        "",
        "// Ensure collection exists (run in arangosh or Web UI before ingesting):",
        f"// if (!db._collection('{collection_name}')) {{ db._createDocumentCollection('{collection_name}'); }}",
        "",
    ]

    for rec in normalized:
        key_val = aql_quote(rec["id"])
        content_val = aql_quote(rec["content"])
        category_val = aql_quote(rec["category"])
        tags_val = aql_array_literal(rec["tags"])
        vis_val = aql_quote(rec["visibility"])
        created_val = aql_quote(rec["created_at"])
        updated_val = aql_quote(rec["updated_at"])

        doc_fields = (
            f"{{ _key: {key_val}, "
            f"content: {content_val}, "
            f"category: {category_val}, "
            f"tags: {tags_val}, "
            f"visibility: {vis_val}, "
            f"created_at: {created_val}, "
            f"updated_at: {updated_val} }}"
        )

        update_fields = (
            f"{{ content: {content_val}, "
            f"category: {category_val}, "
            f"tags: {tags_val}, "
            f"visibility: {vis_val}, "
            f"created_at: {created_val}, "
            f"updated_at: {updated_val} }}"
        )

        # In ArangoDB AQL, statements do not have trailing semicolons
        aql_lines.append(
            f"UPSERT {{ _key: {key_val} }} "
            f"INSERT {doc_fields} "
            f"UPDATE {update_fields} "
            f"IN {collection_name}"
        )

    aql_lines.extend([
        "",
        "// Sample Analytical Queries in AQL:",
        "// 1. Tag frequency analysis (unnesting tags):",
        f"// FOR m IN {collection_name}",
        "//   FOR t IN m.tags",
        "//     COLLECT tag = t WITH COUNT INTO count",
        "//     SORT count DESC",
        "//     LIMIT 10",
        "//     RETURN { tag, count }",
        "",
        "// 2. Count memories by category:",
        f"// FOR m IN {collection_name}",
        "//   COLLECT cat = m.category WITH COUNT INTO total",
        "//   SORT total DESC",
        "//   RETURN { category: cat, total }",
    ])

    return "\n".join(aql_lines) + "\n", len(normalized)


def build_parser() -> argparse.ArgumentParser:
    """Build command line argument parser."""
    parser = argparse.ArgumentParser(
        description="Convert Omi memory JSON exports to an ArangoDB AQL ingestion script.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  omi --json memory list --limit 100 > memories.json
  python memories_to_arangodb.py memories.json -o memories.aql
  cat memories.json | python memories_to_arangodb.py - -o memories.aql --collection user_memories
        """,
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        metavar="INPUT",
        help="Input JSON file path(s), or '-' for standard input",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Destination AQL script file path (.aql)",
    )
    parser.add_argument(
        "--collection",
        default="memories",
        help="Target ArangoDB collection name (default: memories)",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite destination file if it already exists",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    dest: Path = args.output
    if dest.exists() and not args.force:
        sys.stderr.write(f"Error: Output file already exists: {dest} (use --force to overwrite)\n")
        return 1

    try:
        aql_content, count = generate_aql(args.inputs, collection_name=args.collection)
    except Exception as exc:
        sys.stderr.write(f"Error generating AQL: {exc}\n")
        return 1

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(aql_content, encoding="utf-8")
    print(f"Generated ArangoDB AQL script with {count} unique record(s) -> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
