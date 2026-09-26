#!/usr/bin/env python3
"""Convert Omi memories JSON exports into Weaviate vector database batch objects.

Usage:
    # From a saved file to stdout or file:
    python memories_to_weaviate.py memories.json -o weaviate_batch.json

    # Piped directly from omi-cli:
    omi --json memory list --limit 200 | python memories_to_weaviate.py - -o weaviate_batch.json

    # Ingest directly into Weaviate REST batch API:
    curl -X POST -H "Content-Type: application/json" \\
         -d @weaviate_batch.json \\
         http://localhost:8080/v1/batch/objects

Converts memories into the official Weaviate v3/v4 REST Batch API payload:
    {
        "objects": [
            {
                "class": "OmiMemory",
                "id": "e4eaaaf2-d142-51a4-9226-490367253597",
                "properties": {
                    "content": "...",
                    "category": "lifestyle",
                    "created_at": "2026-09-24T12:00:00Z",
                    "memory_id": "mem_001"
                }
            }
        ]
    }

Key features:
    - Pure Python 3.10+ standard library (zero external dependencies).
    - Deterministic RFC 4122 UUID generation (UUIDv5) for Weaviate ID compliance.
    - Multi-file merging with automatic deduplication by memory ID.
    - Supports standard input (-) for seamless UNIX CLI piping.
    - Safe overwrite guard (--force required to overwrite existing files).
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def deterministic_uuid(val: Any) -> str:
    """Generate or validate an RFC 4122 compliant UUID string for Weaviate.

    Weaviate requires object IDs to be valid UUID format. If the source ID is already
    a valid UUID, it is normalized to lowercase string. If it is an arbitrary string
    (e.g., 'mem_123'), a deterministic UUIDv5 is generated under the OMI namespace URL.
    """
    raw_str = str(val).strip() if val is not None else ""
    if not raw_str:
        return str(uuid.uuid4())
    try:
        return str(uuid.UUID(raw_str)).lower()
    except ValueError:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"urn:omi:memory:{raw_str}")).lower()


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


def transform_to_weaviate(
    memories: Sequence[Dict[str, Any]],
    collection: str = "OmiMemory",
    category_filter: Optional[str] = None,
    min_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Transform Omi memories into a Weaviate REST batch payload.

    Args:
        memories: Iterable of raw memory dictionaries.
        collection: The Weaviate class/collection name (default: 'OmiMemory').
        category_filter: Optional case-insensitive category to filter by.
        min_date: Optional ISO-8601 minimum creation date filter.

    Returns:
        A dictionary with an 'objects' list ready for POST /v1/batch/objects.
    """
    min_dt = parse_iso_datetime(min_date) if min_date else None
    cat_lower = category_filter.strip().lower() if category_filter else None

    seen_ids = set()
    objects: List[Dict[str, Any]] = []

    for item in memories:
        raw_id = item.get("id")
        dedup_key = str(raw_id) if raw_id is not None else item.get("content", "")
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

        # Build clean properties dictionary
        content = str(item.get("content") or "").strip()
        obj_id = deterministic_uuid(raw_id) if raw_id is not None else deterministic_uuid(content)

        properties: Dict[str, Any] = {
            "content": content,
            "category": item_cat,
        }

        if raw_id is not None:
            properties["memory_id"] = str(raw_id)

        if created_str:
            properties["created_at"] = str(created_str)

        if "updated_at" in item and item["updated_at"]:
            properties["updated_at"] = str(item["updated_at"])

        if "manually_added" in item and isinstance(item["manually_added"], bool):
            properties["manually_added"] = item["manually_added"]

        if "tags" in item and isinstance(item["tags"], list):
            properties["tags"] = [str(t) for t in item["tags"]]

        objects.append({
            "class": collection,
            "id": obj_id,
            "properties": properties,
        })

    return {"objects": objects}


def load_input_sources(inputs: Sequence[str]) -> List[Dict[str, Any]]:
    """Load and merge memories from file paths or stdin."""
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
        description="Convert Omi memory JSON exports to Weaviate vector database batch objects.",
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
        help="Output destination path for the Weaviate batch JSON (default: stdout).",
    )
    parser.add_argument(
        "-c",
        "--collection",
        "--class-name",
        dest="collection",
        default="OmiMemory",
        help="Target Weaviate collection/class name (default: 'OmiMemory').",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing output file if it already exists.",
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
        help="Filter memories created on or after this ISO-8601 timestamp (e.g. 2026-09-01T00:00:00Z).",
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

    # Check overwrite guard before processing
    if args.output and args.output.exists() and not args.force:
        sys.stderr.write(f"Error: Output file '{args.output}' already exists. Use --force to overwrite.\n")
        return 1

    try:
        memories = load_input_sources(args.inputs)
    except Exception as exc:
        sys.stderr.write(f"Error reading input: {exc}\n")
        return 1

    payload = transform_to_weaviate(
        memories=memories,
        collection=args.collection,
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
