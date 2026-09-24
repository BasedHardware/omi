#!/usr/bin/env python3
"""Convert Omi memories JSON export into ChromaDB collection upsert payloads.

Usage:
    python memories_to_chroma.py memories.json -o chroma_batch.json
    omi --json memory list | python memories_to_chroma.py - --collection omi_memories -o chroma_payload.json

Converts memories into the standard ChromaDB / Chroma Client upsert format:
    {
        "ids": [...],
        "documents": [...],
        "metadatas": [...]
    }
Enables direct ingestion into local Chroma vector stores for RAG, semantic search, and agent memory.
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
        # Extract content
        text = str(item.get("content") or item.get("text") or "").strip()
        mid = str(item.get("id") or "").strip()
        if text and mid:
            results.append(item)

    return results


def transform_to_chroma(
    memories: List[Dict[str, Any]], collection_name: str | None = None
) -> Dict[str, Any]:
    """Transform memory items into ChromaDB upsert format."""
    ids: List[str] = []
    documents: List[str] = []
    metadatas: List[Dict[str, Any]] = []

    for mem in memories:
        mid = str(mem.get("id"))
        doc = str(mem.get("content") or mem.get("text") or "").strip()
        meta: Dict[str, Any] = {
            "category": str(mem.get("category") or "general"),
            "manually_added": bool(mem.get("manually_added", False)),
        }
        if mem.get("created_at"):
            meta["created_at"] = str(mem.get("created_at"))
        if mem.get("updated_at"):
            meta["updated_at"] = str(mem.get("updated_at"))

        ids.append(mid)
        documents.append(doc)
        metadatas.append(meta)

    payload: Dict[str, Any] = {
        "ids": ids,
        "documents": documents,
        "metadatas": metadatas,
    }

    if collection_name:
        payload["collection"] = collection_name

    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi memories JSON export into ChromaDB upsert payloads."
    )
    parser.add_argument("inputs", nargs="*", help="Input JSON files or '-' for stdin")
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Destination JSON file (defaults to stdout)",
    )
    parser.add_argument(
        "--collection",
        help="Optional collection name to associate with the payload",
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

    chroma_payload = transform_to_chroma(all_memories, args.collection)
    output_text = json.dumps(chroma_payload, indent=2, ensure_ascii=False)

    if args.output != "-":
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_text, encoding="utf-8")
        print(
            f"Wrote ChromaDB payload with {len(chroma_payload['ids'])} items to {args.output}",
            file=sys.stderr,
        )
    else:
        sys.stdout.write(output_text + "\n")


if __name__ == "__main__":
    main()
