#!/usr/bin/env python3
"""Convert Omi action items JSON exports into JSON Lines (JSONL / NDJSON) format.

Usage:
    python action_items_to_jsonl.py action_items.json -o tasks.jsonl
    omi --json action-item list | python action_items_to_jsonl.py - -o dataset.jsonl
    python action_items_to_jsonl.py page1.json page2.json -o all_tasks.jsonl --status open

Outputs newline-delimited JSON (JSONL) optimized for task tracking pipelines, Pandas,
DuckDB, and automated task execution agents.
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


def parse_boolean(value: Any) -> bool:
    """Normalize completion status to a strict boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "completed", "done")
    return False


def extract_action_items(content: str, source_label: str = "<input>") -> List[Dict[str, Any]]:
    """Parse JSON content and extract a list of action item dictionaries."""
    raw = content.lstrip("\ufeff")
    items = json.loads(raw)

    if isinstance(items, dict):
        for key in ("action_items", "items", "data"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError(f"{source_label}: expected a JSON array or wrapped action_items object")

    results: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source_label}: each action item must be a JSON object")
        if not item.get("id") or str(item.get("id")).strip() == "":
            raise ValueError(f"{source_label}: action item missing required 'id' field")
        results.append(item)

    return results


def normalize_record(item: Dict[str, Any]) -> Dict[str, Any]:
    """Produce a standardized dictionary for JSONL streaming."""
    desc = item.get("description") or item.get("title") or ""
    completed = parse_boolean(item.get("completed"))

    record: Dict[str, Any] = {
        "id": str(item.get("id")),
        "description": str(desc).strip(),
        "completed": completed,
        "due_at": utc_stamp(item.get("due_at")),
        "created_at": utc_stamp(item.get("created_at")),
        "updated_at": utc_stamp(item.get("updated_at")),
    }

    if item.get("conversation_id"):
        record["conversation_id"] = str(item.get("conversation_id"))

    return record


def convert_paths_to_jsonl(
    sources: Sequence[str | Path],
    output_dest: Optional[str | Path] = None,
    status_filter: Optional[str] = "all",
) -> int:
    """Convert action item JSON exports into JSONL format with optional deduplication and status filtering."""
    all_items: List[Dict[str, Any]] = []

    for src in sources:
        if str(src) == "-":
            content = sys.stdin.read()
            all_items.extend(extract_action_items(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_items.extend(extract_action_items(content, str(p)))

    seen_ids = set()
    deduped: List[Dict[str, Any]] = []
    for item in all_items:
        iid = str(item.get("id"))
        if iid not in seen_ids:
            seen_ids.add(iid)
            is_completed = parse_boolean(item.get("completed"))
            if status_filter == "open" and is_completed:
                continue
            if status_filter == "completed" and not is_completed:
                continue
            deduped.append(item)

    lines = [json.dumps(normalize_record(t), ensure_ascii=False) for t in deduped]
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
        description="Convert Omi action items JSON exports into JSON Lines (JSONL / NDJSON) format."
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
        "--status",
        choices=["all", "open", "completed"],
        default="all",
        help="Filter action items by status (default: all)",
    )
    args = parser.parse_args()

    try:
        count = convert_paths_to_jsonl(args.inputs, args.output, status_filter=args.status)
        if args.output != "-":
            print(f"Exported {count} action item(s) to {args.output}", file=sys.stderr)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
