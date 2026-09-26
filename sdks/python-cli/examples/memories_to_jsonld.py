#!/usr/bin/env python3
"""Convert Omi memories JSON exports into W3C JSON-LD (schema.org) linked data graphs.

Usage:
    # From a saved file to output JSON-LD:
    python memories_to_jsonld.py memories.json -o memories.jsonld

    # Piped directly from omi-cli:
    omi --json memory list --limit 200 | python memories_to_jsonld.py - -o memories.jsonld

    # With custom creator and category filter:
    omi --json memory list | python memories_to_jsonld.py - --creator-name "Alice" --category work -o work_graph.jsonld

Converts memories into standard W3C JSON-LD knowledge graph format:
    {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "NoteDigitalDocument",
                "@id": "urn:omi:memory:mem_001",
                "identifier": "mem_001",
                "text": "User prefers asynchronous standup notes",
                "genre": "work",
                "dateCreated": "2026-09-24T12:00:00Z",
                "keywords": ["remote", "work"],
                "creator": {
                    "@type": "Person",
                    "name": "Omi User"
                }
            }
        ]
    }

Key features:
    - Pure Python 3.10+ standard library (zero external dependencies).
    - Fully compliant with W3C JSON-LD 1.1 and schema.org vocabularies.
    - Multi-file merging with automatic deduplication by memory ID.
    - Category and date filtering (--category, --min-date).
    - Streaming standard input (-) for seamless UNIX CLI piping.
    - Safe overwrite guard (--force required to replace existing files).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def parse_iso_datetime(val: Any) -> Optional[datetime]:
    """Parse an ISO 8601 string into a UTC datetime, or return None if invalid."""
    if not isinstance(val, str) or not val.strip():
        return None
    cleaned = val.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def extract_memories(data: Any) -> List[Dict[str, Any]]:
    """Extract list of memory dictionaries from JSON string, dict, or list."""
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON data: {exc}") from exc
    else:
        parsed = data

    if isinstance(parsed, dict):
        if "memories" in parsed and isinstance(parsed["memories"], list):
            items = parsed["memories"]
        elif "id" in parsed or "content" in parsed:
            items = [parsed]
        else:
            raise ValueError("Expected a JSON array or object containing 'memories'")
    elif isinstance(parsed, list):
        items = parsed
    else:
        raise ValueError(f"Unexpected JSON root type: {type(parsed).__name__}")

    result: List[Dict[str, Any]] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"Item at index {idx} is not a valid JSON object")
        result.append(item)
    return result


def transform_to_jsonld(
    memories: Sequence[Dict[str, Any]],
    creator_name: str = "Omi User",
    category_filter: Optional[str] = None,
    min_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Transform Omi memories into a W3C schema.org JSON-LD graph."""
    min_dt = parse_iso_datetime(min_date) if min_date else None
    cat_lower = category_filter.strip().lower() if category_filter else None

    seen_ids = set()
    graph: List[Dict[str, Any]] = []

    for item in memories:
        raw_id = item.get("id")
        dedup_key = str(raw_id) if raw_id is not None else str(item.get("content", ""))
        if dedup_key in seen_ids:
            continue
        seen_ids.add(dedup_key)

        # Apply category filter
        item_cat = str(item.get("category") or "general").strip()
        if cat_lower and item_cat.lower() != cat_lower:
            continue

        # Apply date filter
        created_str = item.get("created_at")
        if min_dt:
            item_dt = parse_iso_datetime(created_str)
            if item_dt and item_dt < min_dt:
                continue

        content = str(item.get("content") or "").strip()
        doc_id = str(raw_id) if raw_id is not None else dedup_key
        uri_id = f"urn:omi:memory:{doc_id}"

        doc: Dict[str, Any] = {
            "@type": "NoteDigitalDocument",
            "@id": uri_id,
            "identifier": doc_id,
            "text": content,
            "genre": item_cat,
        }

        if created_str:
            doc["dateCreated"] = str(created_str)

        if "updated_at" in item and item["updated_at"]:
            doc["dateModified"] = str(item["updated_at"])

        # Tags and keywords
        tags = item.get("tags") or []
        if isinstance(tags, list) and tags:
            doc["keywords"] = [str(t) for t in tags]

        if creator_name:
            doc["creator"] = {
                "@type": "Person",
                "name": creator_name,
            }

        graph.append(doc)

    return {
        "@context": "https://schema.org",
        "@graph": graph,
    }


def load_input_sources(inputs: Sequence[str]) -> List[Dict[str, Any]]:
    """Load memories from files or stdin."""
    all_memories: List[Dict[str, Any]] = []
    for src in inputs:
        if src == "-":
            raw = sys.stdin.read()
            if raw.strip():
                all_memories.extend(extract_memories(raw))
        else:
            path = Path(src)
            if not path.is_file():
                raise FileNotFoundError(f"Input file not found: {path}")
            raw = path.read_text(encoding="utf-8")
            if raw.strip():
                all_memories.extend(extract_memories(raw))
    return all_memories


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Convert Omi memory JSON exports into W3C JSON-LD schema.org linked data graphs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        default=["-"],
        help="Input JSON file path(s), or '-' to read from standard input (default: -).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output destination path for the JSON-LD document (default: stdout).",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing output file if it already exists.",
    )
    parser.add_argument(
        "--creator-name",
        type=str,
        default="Omi User",
        help="Name of the document creator (default: 'Omi User').",
    )
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="Filter memories to a specific category (case-insensitive).",
    )
    parser.add_argument(
        "--min-date",
        type=str,
        default=None,
        help="Filter memories created on or after this ISO-8601 timestamp.",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="Number of spaces for JSON indentation (default: 2; set 0 for compact).",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.output and args.output.exists() and not args.force:
        sys.stderr.write(f"Error: Output file '{args.output}' already exists. Use --force to overwrite.\n")
        return 1

    try:
        memories = load_input_sources(args.inputs)
    except Exception as exc:
        sys.stderr.write(f"Error reading input: {exc}\n")
        return 1

    payload = transform_to_jsonld(
        memories=memories,
        creator_name=args.creator_name,
        category_filter=args.category,
        min_date=args.min_date,
    )

    indent = args.indent if args.indent > 0 else None
    out_json = json.dumps(payload, indent=indent, ensure_ascii=False) + "\n"

    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(out_json, encoding="utf-8")
        except OSError as exc:
            sys.stderr.write(f"Error writing output file: {exc}\n")
            return 1
    else:
        sys.stdout.write(out_json)

    return 0


if __name__ == "__main__":
    sys.exit(main())
