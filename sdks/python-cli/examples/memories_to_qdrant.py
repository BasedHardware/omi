#!/usr/bin/env python3
"""Convert Omi memories JSON exports into Qdrant vector database points payload.

Usage:
    # Basic conversion from a saved memories JSON export:
    python memories_to_qdrant.py memories.json -o qdrant_points.json

    # Piped directly from omi-cli:
    omi --json memory list --limit 100 | python memories_to_qdrant.py - -o qdrant_points.json

    # Export with zero-vector embedding placeholder (e.g., 768 dims) ready for Qdrant upsert:
    python memories_to_qdrant.py memories.json -o points.json --vector-dim 768

    # Multi-file deduplicated export with overwrite protection:
    python memories_to_qdrant.py day1.json day2.json -o points.json --force

Format:
    Outputs a Qdrant-compliant points batch payload:
    {
        "points": [
            {
                "id": "<uuid>",
                "payload": {
                    "memory_id": "...",
                    "content": "...",
                    "category": "...",
                    "tags": [...],
                    "created_at": "...",
                    "updated_at": "..."
                },
                "vector": [0.0, ...]  # if --vector-dim specified
            }
        ]
    }
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def sanitize_uuid(raw_id: str) -> str:
    """Ensure ID is a valid RFC 4122 UUID string required by Qdrant points.

    If raw_id is not already a valid UUID, generate a deterministic UUIDv5
    under the DNS namespace so IDs remain idempotent across runs.
    """
    cleaned = str(raw_id).strip()
    try:
        val = uuid.UUID(cleaned)
        return str(val)
    except (ValueError, AttributeError):
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"omi-memory:{cleaned}"))


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


def transform_memory_to_qdrant_point(
    item: Dict[str, Any],
    vector_dim: Optional[int] = None,
) -> Dict[str, Any]:
    """Transform an individual memory item into a Qdrant point object."""
    raw_id = str(item.get("id") or item.get("uid") or "").strip()
    if not raw_id:
        raise ValueError("Memory record missing required 'id' field")

    point_id = sanitize_uuid(raw_id)
    content = str(item.get("content") or item.get("text") or item.get("memory") or "").strip()
    category = str(item.get("category") or item.get("type") or "general").strip()

    tags_val = item.get("tags") or []
    if isinstance(tags_val, str):
        tags = [t.strip() for t in tags_val.split(",") if t.strip()]
    elif isinstance(tags_val, list):
        tags = [str(t).strip() for t in tags_val if str(t).strip()]
    else:
        tags = []

    payload: Dict[str, Any] = {
        "memory_id": raw_id,
        "content": content,
        "category": category,
        "tags": tags,
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }

    point: Dict[str, Any] = {
        "id": point_id,
        "payload": payload,
    }

    if vector_dim is not None and vector_dim > 0:
        point["vector"] = [0.0] * vector_dim

    return point


def convert_memories_to_qdrant_payload(
    inputs: Sequence[str],
    vector_dim: Optional[int] = None,
) -> Dict[str, Any]:
    """Load, deduplicate by ID, and transform memories into a Qdrant points payload."""
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
        for mem in memories:
            mid = str(mem.get("id") or mem.get("uid") or "").strip()
            if mid:
                dedup[mid] = mem

    points = [
        transform_memory_to_qdrant_point(mem, vector_dim=vector_dim)
        for mem in dedup.values()
    ]

    return {"points": points}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi memory JSON exports to Qdrant vector database points payload.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  omi --json memory list --limit 100 | python memories_to_qdrant.py - -o points.json
  python memories_to_qdrant.py memories.json -o points.json --vector-dim 768
  python memories_to_qdrant.py m1.json m2.json -o points.json --force
""",
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        metavar="INPUT",
        help="One or more memories JSON files exported from 'omi --json memory list', or '-' for stdin.",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        metavar="FILE",
        help="Output JSON file path.",
    )
    parser.add_argument(
        "--vector-dim",
        type=int,
        default=None,
        metavar="DIM",
        help="Optional placeholder vector dimension (e.g. 768, 1536) for collection schema testing.",
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
        payload = convert_memories_to_qdrant_payload(args.inputs, vector_dim=args.vector_dim)
    except (FileNotFoundError, ValueError) as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Exported {len(payload['points'])} Qdrant point(s) to '{args.output}'.")


if __name__ == "__main__":
    main()
