#!/usr/bin/env python3
"""Convert Omi memories JSON export into Pinecone vector upsert payloads.

Usage:
    python memories_to_pinecone.py memories.json -o pinecone_batch.json
    omi --json memory list | python memories_to_pinecone.py - --namespace custom-ns -o payload.json

Converts memories into the standard Pinecone REST API upsert format:
    {
        "vectors": [
            {
                "id": "mem-001",
                "metadata": {
                    "text": "...",
                    "category": "work",
                    "created_at": "..."
                }
            }
        ],
        "namespace": "omi-memories"
    }
Enables seamless batch upsert into Pinecone cloud vector indexes.
Requires only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def extract_memories(content: str, source_label: str = "<input>") -> List[Dict[str, Any]]:
    """Parse JSON and extract list of memory items."""
    raw = content.lstrip("\ufeff")
    items = json.loads(raw)

    if isinstance(items, dict):
        for key in ("memories", "items", "data"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError(f"{source_label}: expected a JSON array or wrapped memories object")

    results = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("content") or item.get("text") or "").strip()
        mid = str(item.get("id") or "").strip()
        if text and mid:
            results.append(item)

    return results


def transform_to_pinecone(
    memories: List[Dict[str, Any]], namespace: str = "omi-memories"
) -> Dict[str, Any]:
    """Transform memory items into Pinecone upsert schema."""
    vectors: List[Dict[str, Any]] = []

    for mem in memories:
        mid = str(mem.get("id"))
        text = str(mem.get("content") or mem.get("text") or "").strip()

        metadata: Dict[str, Any] = {
            "text": text,
            "category": str(mem.get("category") or "general"),
            "manually_added": bool(mem.get("manually_added", False)),
        }
        if mem.get("created_at"):
            metadata["created_at"] = str(mem.get("created_at"))
        if mem.get("updated_at"):
            metadata["updated_at"] = str(mem.get("updated_at"))

        vectors.append({
            "id": mid,
            "metadata": metadata,
        })

    payload: Dict[str, Any] = {
        "vectors": vectors,
    }
    if namespace:
        payload["namespace"] = namespace

    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi memories JSON export into Pinecone vector upsert payloads."
    )
    parser.add_argument("inputs", nargs="*", help="Input JSON files or '-' for stdin")
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Destination JSON file (defaults to stdout)",
    )
    parser.add_argument(
        "--namespace",
        default="omi-memories",
        help="Pinecone index namespace (default: 'omi-memories')",
    )
    args = parser.parse_args()

    if not args.inputs:
        parser.print_help()
        sys.exit(1)

    all_memories: List[Dict[str, Any]] = []
    for src in args.inputs:
        if str(src) == "-":
            content = sys.stdin.read()
            all_memories.extend(extract_memories(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_memories.extend(extract_memories(content, str(p)))

    payload = transform_to_pinecone(all_memories, namespace=args.namespace)
    output_text = json.dumps(payload, indent=2, ensure_ascii=False)

    if args.output != "-":
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_text, encoding="utf-8")
        print(f"Generated Pinecone upsert payload with {len(payload['vectors'])} vectors at {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(output_text + "\n")


if __name__ == "__main__":
    main()
