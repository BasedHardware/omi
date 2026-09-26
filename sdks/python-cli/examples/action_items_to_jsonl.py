#!/usr/bin/env python3
"""
Convert Omi action items JSON export to JSON Lines (.jsonl) for AI task management, LLMs, and databases.

Usage:
    python action_items_to_jsonl.py action_items.json -o tasks.jsonl
    omi --json action-item list | python action_items_to_jsonl.py - -o tasks.jsonl --filter pending
    python action_items_to_jsonl.py action_items.json -o agent_tasks.jsonl --mode task_agent

Supported Modes:
    standard    - Structured fields: id, description, completed, due_at, created_at, conversation_id
    task_agent  - Formatted prompt schema for autonomous agent task execution and backlog ingestion
    minimal     - Clean key-value pairs of pending/completed tasks
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


def parse_boolean(val: Any) -> bool:
    """Normalize completion state to a strict boolean."""
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes", "completed")
    return False


def read_action_items(inputs: Sequence[str]) -> List[Dict[str, Any]]:
    """Read and unwrap action item records across one or more files or stdin."""
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
            for key in ("action_items", "items", "data", "tasks"):
                if isinstance(parsed.get(key), list):
                    parsed = parsed[key]
                    break

        if not isinstance(parsed, list):
            raise ValueError(f"{src_name}: expected a JSON array of action items")

        for item in parsed:
            if not isinstance(item, dict):
                raise ValueError(f"{src_name}: each record must be a JSON object")
            if not item.get("id"):
                raise ValueError(f"{src_name}: record missing required 'id' field")
            all_items.append(item)

    return all_items


def format_record(item: Dict[str, Any], mode: str = "standard") -> Dict[str, Any]:
    """Format an action item according to selected output mode."""
    task_id = str(item.get("id"))
    description = str(item.get("description") or item.get("title") or "").strip()
    completed = parse_boolean(item.get("completed"))
    due_at = parse_datetime(item.get("due_at"))
    created_at = parse_datetime(item.get("created_at"))
    updated_at = parse_datetime(item.get("updated_at"))
    conversation_id = str(item.get("conversation_id")) if item.get("conversation_id") else None

    if mode == "task_agent":
        status = "COMPLETED" if completed else "PENDING"
        due_str = f" [Due: {due_at}]" if due_at else ""
        return {
            "task_id": task_id,
            "instruction": description,
            "status": status,
            "context": {
                "due_at": due_at,
                "conversation_id": conversation_id,
                "created_at": created_at,
            },
            "prompt": f"Task ({status}){due_str}: {description}",
        }

    if mode == "minimal":
        return {
            "id": task_id,
            "task": description,
            "completed": completed,
            "due": due_at,
        }

    # standard mode
    return {
        "id": task_id,
        "description": description,
        "completed": completed,
        "due_at": due_at,
        "created_at": created_at,
        "updated_at": updated_at,
        "conversation_id": conversation_id,
    }


def convert(
    inputs: Sequence[str],
    output_path: str,
    mode: str = "standard",
    status_filter: Optional[str] = None,
    dedupe: bool = True,
) -> int:
    """Read action item inputs and write formatted lines to output_path. Returns count written."""
    out = Path(output_path)
    if ".." in out.parts:
        raise ValueError(f"Output path {output_path!r} contains '..'; refusing to write.")

    items = read_action_items(inputs)
    seen_ids: Set[str] = set()
    written_count = 0

    lines: List[str] = []
    for item in items:
        task_id = str(item.get("id"))
        if dedupe and task_id in seen_ids:
            continue
        seen_ids.add(task_id)

        completed = parse_boolean(item.get("completed"))
        if status_filter == "pending" and completed:
            continue
        if status_filter == "completed" and not completed:
            continue

        record = format_record(item, mode=mode)
        lines.append(json.dumps(record, ensure_ascii=False))
        written_count += 1

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return written_count


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi action items JSON exports into JSON Lines (.jsonl)."
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        metavar="JSON_FILE",
        help="One or more action items JSON files (or '-' for stdin).",
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
        choices=["standard", "task_agent", "minimal"],
        default="standard",
        help="Output JSONL formatting mode (default: standard).",
    )
    parser.add_argument(
        "--filter",
        choices=["all", "pending", "completed"],
        default="all",
        help="Filter items by completion status (default: all).",
    )
    parser.add_argument(
        "--no-dedupe",
        action="store_true",
        help="Disable deduplication across input files.",
    )

    args = parser.parse_args(argv)

    filter_val = None if args.filter == "all" else args.filter

    try:
        count = convert(
            inputs=args.inputs,
            output_path=args.output,
            mode=args.mode,
            status_filter=filter_val,
            dedupe=not args.no_dedupe,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Exported {count} action items to {args.output} in '{args.mode}' mode.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
