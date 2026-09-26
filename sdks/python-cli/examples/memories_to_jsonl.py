#!/usr/bin/env python3
"""
Convert Omi memories JSON export to JSON Lines (.jsonl) for AI fine-tuning, RAG, and vector DBs.

Usage:
    python memories_to_jsonl.py memories.json -o memories.jsonl
    omi --json memory list | python memories_to_jsonl.py - -o memories.jsonl --mode rag
    python memories_to_jsonl.py memories.json -o fine_tune.jsonl --mode system_prompt --category work,skills

Supported Modes:
    standard      - Structured fields: id, content, category, visibility, tags, timestamps
    rag           - Document text with metadata payload for vector search & embeddings
    system_prompt - Formatted system instructions for persona/context injection
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set


def parse_datetime(iso_str: Optional[str]) -> Optional[str]:
    """Normalize ISO-8601 string to standard UTC ISO text."""
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(str(iso_str).replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        return dt.isoformat()
    except (ValueError, AttributeError):
        return str(iso_str)


def parse_tags(tags: Any) -> List[str]:
    """Normalize tags into a clean list of strings."""
    if not tags:
        return []
    if isinstance(tags, (list, tuple, set)):
        return [str(t).strip() for t in tags if str(t).strip()]
    if isinstance(tags, str):
        return [t.strip() for t in tags.split(",") if t.strip()]
    return [str(tags)]


def read_memories(inputs: Sequence[str]) -> List[Dict[str, Any]]:
    """Read and unwrap memory records across one or more files or stdin."""
    all_items: List[Dict[str, Any]] = []
    for source in inputs:
        if source == "-":
            raw = sys.stdin.read().lstrip("\ufeff")
            src_name = "<stdin>"
        else:
            p = Path(source)
            if not p.is_file():
                raise FileNotFoundError(f"Input file not found: {source}")
            raw = p.read_text(encoding="utf-8").lstrip("\ufeff")
            src_name = source

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {src_name}: {exc}") from exc

        if isinstance(parsed, dict):
            for key in ("memories", "items", "data"):
                if isinstance(parsed.get(key), list):
                    parsed = parsed[key]
                    break

        if not isinstance(parsed, list):
            raise ValueError(f"{src_name}: expected a JSON array of memories")

        for item in parsed:
            if not isinstance(item, dict):
                raise ValueError(f"{src_name}: each record must be a JSON object")
            if not item.get("id"):
                raise ValueError(f"{src_name}: record missing required 'id' field")
            all_items.append(item)

    return all_items


def format_record(
    item: Dict[str, Any], mode: str = "standard"
) -> Dict[str, Any]:
    """Format an individual memory item according to selected output mode."""
    mem_id = str(item.get("id"))
    content = str(item.get("content") or item.get("description") or "").strip()
    category = str(item.get("category") or "other").strip().lower()
    visibility = str(item.get("visibility") or "private").strip().lower()
    tags = parse_tags(item.get("tags"))
    created_at = parse_datetime(item.get("created_at"))
    updated_at = parse_datetime(item.get("updated_at"))

    if mode == "rag":
        metadata: Dict[str, Any] = {
            "id": mem_id,
            "category": category,
            "visibility": visibility,
            "tags": tags,
        }
        if created_at:
            metadata["created_at"] = created_at
        return {
            "id": mem_id,
            "text": f"[{category.upper()}] {content}",
            "metadata": metadata,
        }

    if mode == "system_prompt":
        tag_str = f" (#{', #'.join(tags)})" if tags else ""
        return {
            "role": "system",
            "content": f"User memory ({category}): {content}{tag_str}",
            "memory_id": mem_id,
        }

    # standard mode
    return {
        "id": mem_id,
        "content": content,
        "category": category,
        "visibility": visibility,
        "tags": tags,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def convert(
    inputs: Sequence[str],
    output_path: str,
    mode: str = "standard",
    categories: Optional[Set[str]] = None,
    dedupe: bool = True,
) -> int:
    """Read memory inputs and write formatted lines to output_path. Returns count written."""
    out = Path(output_path)
    if ".." in out.parts:
        raise ValueError(f"Output path {output_path!r} contains '..'; refusing to write.")

    memories = read_memories(inputs)
    seen_ids: Set[str] = set()
    written_count = 0

    lines: List[str] = []
    for item in memories:
        mem_id = str(item.get("id"))
        if dedupe and mem_id in seen_ids:
            continue
        seen_ids.add(mem_id)

        cat = str(item.get("category") or "").strip().lower()
        if categories and cat not in categories:
            continue

        record = format_record(item, mode=mode)
        lines.append(json.dumps(record, ensure_ascii=False))
        written_count += 1

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return written_count


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi memories JSON export into JSON Lines (.jsonl) for AI applications."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        metavar="JSON_FILE",
        help="One or more memory JSON files (or '-' for stdin).",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        metavar="JSONL_FILE",
        help="Output destination path for .jsonl file.",
    )
    parser.add_argument(
        "-m",
        "--mode",
        choices=["standard", "rag", "system_prompt"],
        default="standard",
        help="Output JSONL formatting mode (default: standard).",
    )
    parser.add_argument(
        "-c",
        "--category",
        help="Comma-separated category filter (e.g. 'work,learnings,skills').",
    )
    parser.add_argument(
        "--no-dedupe",
        action="store_true",
        help="Disable deduplication across input files.",
    )

    args = parser.parse_args(argv)

    category_filter: Optional[Set[str]] = None
    if args.category:
        category_filter = {c.strip().lower() for c in args.category.split(",") if c.strip()}

    try:
        count = convert(
            inputs=args.inputs,
            output_path=args.output,
            mode=args.mode,
            categories=category_filter,
            dedupe=not args.no_dedupe,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Exported {count} memories to {args.output} in '{args.mode}' mode.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
