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
from typing import Any, Dict, List, Sequence, Tuple


def aql_quote(val: Any) -> str:
    """Format and escape a scalar value as an AQL literal."""
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    # Escape backslashes and single quotes for AQL string literals
    text = str(val).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{text}'"


def aql_array_literal(items: Sequence[str]) -> str:
    """Format a sequence of strings into an AQL array literal."""
    if not items:
        return "[]"
    escaped_items = ["'" + str(x).replace("\\", "\\\\").replace("'", "\\'") + "'" for x in items]
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
    """Load, deduplicate by ID, and generate ArangoDB AQL ingestion statements."""
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
        f"// ArangoDB AQL Ingestion Script for Omi Memories",
        f"// Total records: {len(normalized)}",
        f"// Target collection: {collection_name}",
        "",
        f"// Ensure collection exists (or create via Web UI / arangosh):",
        f"// db._createDocumentCollection('{collection_name}');",
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

        aql_lines.append(
            f"UPSERT {{ _key: {key_val} }} "
            f"INSERT {doc_fields} "
            f"UPDATE {update_fields} "
            f"IN {collection_name};"
        )

    aql_lines.extend([
        "",
        f"// Sample Analytical Queries in AQL:",
        f"// 1. Tag frequency analysis (unnesting tags):",
        f"// FOR m IN {collection_name}",
        f"//   FOR t IN m.tags",
        f"//     COLLECT tag = t WITH COUNT INTO count",
        f"//     SORT count DESC",
        f"//     LIMIT 10",
        f"//     RETURN {{ tag, count }};",
        "",
        f"// 2. Count memories by category:",
        f"// FOR m IN {collection_name}",
        f"//   COLLECT cat = m.category WITH COUNT INTO total",
        f"//   SORT total DESC",
        f"//   RETURN {{ category: cat, total }};",
        "",
        f"// 3. Search memories by content substring:",
        f"// FOR m IN {collection_name}",
        f"//   FILTER CONTAINS(LOWER(m.content), 'meeting')",
        f"//   SORT m.created_at DESC",
        f"//   RETURN m;",
        "",
    ])

    return "\n".join(aql_lines), len(normalized)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi memory JSON exports to an ArangoDB AQL ingestion script.",
        epilog="""\
examples:
  omi --json memory list --limit 100 | python memories_to_arangodb.py - -o memories.aql
  python memories_to_arangodb.py export.json -o memories.aql --collection user_memories
  python memories_to_arangodb.py day1.json day2.json -o memories.aql --force
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
        help="Path to write the output .aql script (default: '-' for stdout).",
    )
    parser.add_argument(
        "--collection",
        default="memories",
        help="Target ArangoDB collection name (default: memories).",
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
        aql_content, count = generate_aql(args.inputs, collection_name=args.collection)
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)

    if args.output == "-":
        sys.stdout.write(aql_content + "\n")
    else:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(aql_content, encoding="utf-8")
        sys.stderr.write(
            f"Successfully generated ArangoDB AQL script: {args.output} ({count} memories)\n"
        )


if __name__ == "__main__":
    main()
