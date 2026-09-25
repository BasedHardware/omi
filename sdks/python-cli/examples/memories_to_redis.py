#!/usr/bin/env python3
"""Convert Omi memory JSON exports to a Redis Stack (RedisJSON + RediSearch) ingestion script.

Reads Omi memory JSON exports (from file paths or stdin), deduplicates by memory ID,
and generates clean, idempotent Redis CLI commands (FT.CREATE index and JSON.SET commands).

Redis Stack provides lightning-fast in-memory document storage and real-time secondary
indexing with full-text search.

Zero external dependencies - uses Python 3 standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple


def redis_escape_string(val: str) -> str:
    """Escape string for single-quoted Redis CLI command arguments."""
    # Escape backslashes and single quotes
    escaped = val.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


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


def format_memory_for_redis(item: Dict[str, Any]) -> Dict[str, Any]:
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


def generate_redis_commands(
    inputs: Sequence[str],
    key_prefix: str = "memory:",
    index_name: str = "idx:memories",
) -> Tuple[str, int]:
    """Load, deduplicate by ID, and generate Redis CLI ingestion commands."""
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

    normalized = [format_memory_for_redis(m) for m in dedup.values()]

    lines: List[str] = [
        f"# Redis Stack (RedisJSON + RediSearch) Ingestion Script for Omi Memories",
        f"# Total records: {len(normalized)}",
        f"# Key prefix: {key_prefix}",
        f"# Search index: {index_name}",
        "",
        "# 1. Create RediSearch secondary index if not already created",
        f"# Run via redis-cli: FT.CREATE {index_name} ON JSON PREFIX 1 {redis_escape_string(key_prefix)} SCHEMA $.content AS content TEXT $.category AS category TAG $.tags.* AS tags TAG $.visibility AS visibility TAG $.created_at AS created_at TEXT",
        "",
        "# 2. Ingest JSON documents",
    ]

    for rec in normalized:
        key = f"{key_prefix}{rec['id']}"
        json_payload = json.dumps(rec, ensure_ascii=False)
        escaped_payload = redis_escape_string(json_payload)
        lines.append(f"JSON.SET {key} $ {escaped_payload}")

    lines.extend([
        "",
        "# Sample Search Queries (RediSearch):",
        f"# Search memory content: FT.SEARCH {index_name} \"meeting\"",
        f"# Filter by category:    FT.SEARCH {index_name} \"@category:{{work}}\"",
        f"# Filter by tag:         FT.SEARCH {index_name} \"@tags:{{project}}\"",
        "",
    ])

    return "\n".join(lines), len(normalized)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi memory JSON exports to Redis Stack ingestion commands.",
        epilog="""\
examples:
  omi --json memory list --limit 100 | python memories_to_redis.py - -o memories.redis
  python memories_to_redis.py export.json -o memories.redis --key-prefix memory:
  cat memories.redis | redis-cli
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
        help="Path to write the output .redis script (default: '-' for stdout).",
    )
    parser.add_argument(
        "--key-prefix",
        default="memory:",
        help="Key prefix for Redis documents (default: memory:).",
    )
    parser.add_argument(
        "--index-name",
        default="idx:memories",
        help="RediSearch index name (default: idx:memories).",
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
        content, count = generate_redis_commands(
            args.inputs,
            key_prefix=args.key_prefix,
            index_name=args.index_name,
        )
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)

    if args.output == "-":
        sys.stdout.write(content + "\n")
    else:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        sys.stderr.write(
            f"Successfully generated Redis script: {args.output} ({count} memories)\n"
        )


if __name__ == "__main__":
    main()
