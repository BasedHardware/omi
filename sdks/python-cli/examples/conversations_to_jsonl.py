#!/usr/bin/env python3
"""Convert Omi conversations JSON exports into JSON Lines (JSONL / NDJSON) format.

Usage:
    python conversations_to_jsonl.py conversations.json -o conversations.jsonl
    omi --json conversation list | python conversations_to_jsonl.py - -o dataset.jsonl
    python conversations_to_jsonl.py page1.json page2.json -o all_conversations.jsonl

Outputs newline-delimited JSON (JSONL) optimized for Pandas, DuckDB, Spark,
vector database embedding pipelines, and LLM fine-tuning datasets.
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


def extract_conversations(content: str, source_label: str = "<input>") -> List[Dict[str, Any]]:
    """Parse JSON content and extract a list of conversation dictionaries."""
    raw = content.lstrip("\ufeff")
    items = json.loads(raw)

    if isinstance(items, dict):
        for key in ("conversations", "items", "data"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError(f"{source_label}: expected a JSON array or wrapped conversations object")

    results: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source_label}: each conversation must be a JSON object")
        if not item.get("id") or str(item.get("id")).strip() == "":
            raise ValueError(f"{source_label}: conversation missing required 'id' field")
        results.append(item)

    return results


def normalize_record(item: Dict[str, Any]) -> Dict[str, Any]:
    """Produce a standardized dictionary for JSONL streaming."""
    structured = item.get("structured") or {}
    if not isinstance(structured, dict):
        structured = {}

    segments = item.get("transcript_segments") or []
    turns_count = len(segments) if isinstance(segments, list) else 0

    record: Dict[str, Any] = {
        "id": str(item.get("id")),
        "title": structured.get("title") or item.get("title"),
        "category": structured.get("category") or item.get("category"),
        "overview": structured.get("overview") or item.get("overview"),
        "source": item.get("source"),
        "turns_count": turns_count,
        "started_at": utc_stamp(item.get("started_at")),
        "finished_at": utc_stamp(item.get("finished_at")),
        "created_at": utc_stamp(item.get("created_at")),
        "updated_at": utc_stamp(item.get("updated_at")),
    }

    if item.get("transcript"):
        record["transcript"] = item["transcript"]
    elif segments:
        record["transcript_segments"] = segments

    return record


def convert_paths_to_jsonl(
    sources: Sequence[str | Path],
    output_dest: Optional[str | Path] = None,
) -> int:
    """Convert conversation JSON exports into JSONL format."""
    all_conversations: List[Dict[str, Any]] = []

    for src in sources:
        if str(src) == "-":
            content = sys.stdin.read()
            all_conversations.extend(extract_conversations(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_conversations.extend(extract_conversations(content, str(p)))

    seen_ids = set()
    deduped: List[Dict[str, Any]] = []
    for conv in all_conversations:
        cid = str(conv.get("id"))
        if cid not in seen_ids:
            seen_ids.add(cid)
            deduped.append(conv)

    lines = [json.dumps(normalize_record(c), ensure_ascii=False) for c in deduped]
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
        description="Convert Omi conversations JSON exports into JSON Lines (JSONL / NDJSON) format."
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
    args = parser.parse_args()

    try:
        count = convert_paths_to_jsonl(args.inputs, args.output)
        if args.output != "-":
            print(f"Exported {count} conversation(s) to {args.output}", file=sys.stderr)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
