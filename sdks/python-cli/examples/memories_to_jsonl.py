#!/usr/bin/env python3
"""Convert Omi memories and facts JSON exports into JSON Lines (JSONL / NDJSON) format.

Usage:
    python memories_to_jsonl.py memories.json -o memories.jsonl
    omi --json memory list | python memories_to_jsonl.py - -o dataset.jsonl
    python memories_to_jsonl.py page1.json page2.json -o all_memories.jsonl

Outputs newline-delimited JSON (JSONL) optimized for Pandas, DuckDB, vector search
embeddings, Retrieval-Augmented Generation (RAG) pipelines, and LLM fine-tuning.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def utc_stamp(value: Optional[str]) -> Optional[str]:
    """Normalise an ISO-8601 timestamp to UTC 'YYYY-MM-DD HH:MM:SS' text."""
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        return value


def extract_memories(content: str, source_label: str = "<input>") -> List[Dict[str, Any]]:
    """Parse JSON content and extract a list of memory dictionaries."""
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

    results: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source_label}: each memory must be a JSON object")
        if not item.get("id") or str(item.get("id")).strip() == "":
            raise ValueError(f"{source_label}: memory missing required 'id' field")
        results.append(item)

    return results


def normalize_record(item: Dict[str, Any]) -> Dict[str, Any]:
    """Produce a standardized dictionary for JSONL streaming."""
    tags_raw = item.get("tags")
    tags: List[str] = []
    if isinstance(tags_raw, list):
        tags = [str(t).strip() for t in tags_raw if str(t).strip()]
    elif isinstance(tags_raw, str) and tags_raw.strip():
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

    category = str(item.get("category") or "").strip().lower() or None
    visibility = str(item.get("visibility") or "").strip().lower() or "public"

    record: Dict[str, Any] = {
        "id": str(item.get("id")),
        "content": str(item.get("content") or "").strip(),
        "category": category,
        "tags": tags,
        "visibility": visibility,
        "created_at": utc_stamp(item.get("created_at")),
        "updated_at": utc_stamp(item.get("updated_at")),
    }

    if "source" in item:
        record["source"] = item["source"]

    return record


def convert_paths_to_jsonl(
    sources: Sequence[str | Path],
    output_dest: Optional[str | Path] = None,
    category_filter: Optional[str] = None,
) -> int:
    """Convert memory JSON exports into JSONL format with optional deduplication and filtering."""
    all_memories: List[Dict[str, Any]] = []

    for src in sources:
        if str(src) == "-":
            content = sys.stdin.read()
            all_memories.extend(extract_memories(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_memories.extend(extract_memories(content, str(p)))

    filter_cats = {c.strip().lower() for c in category_filter.split(",")} if category_filter else None

    seen_ids = set()
    deduped: List[Dict[str, Any]] = []
    for mem in all_memories:
        mid = str(mem.get("id"))
        if mid not in seen_ids:
            seen_ids.add(mid)
            if filter_cats:
                cat = str(mem.get("category") or "").strip().lower()
                if cat not in filter_cats:
                    continue
            deduped.append(mem)

    lines = [json.dumps(normalize_record(m), ensure_ascii=False) for m in deduped]
    output_text = "\n".join(lines) + ("\n" if lines else "")

    if output_dest and str(output_dest) != "-":
        out_path = Path(output_dest)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_text, encoding="utf-8")
    else:
        sys.stdout.write(output_text)

    return len(deduped)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi memories JSON exports into JSON Lines (JSONL / NDJSON) format."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Input JSON files or '-' for standard input",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Destination JSONL file (defaults to stdout)",
    )
    parser.add_argument(
        "-c",
        "--category",
        default=None,
        help="Filter by category (comma-separated, e.g. 'work,learnings')",
    )
    args = parser.parse_args()

    try:
        count = convert_paths_to_jsonl(args.inputs, args.output, category_filter=args.category)
        if args.output != "-":
            print(f"Exported {count} memory/memories to {args.output}", file=sys.stderr)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
