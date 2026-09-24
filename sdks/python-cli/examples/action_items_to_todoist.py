#!/usr/bin/env python3
"""Convert Omi action items JSON export into Todoist REST API task payloads.

Usage:
    python action_items_to_todoist.py action_items.json -o todoist_tasks.json
    omi --json action-item list | python action_items_to_todoist.py - --label omi-tasks -o tasks.json

Formats action items into standard Todoist task creation payloads compatible with:
    POST https://api.todoist.com/rest/v2/tasks
Requires only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def extract_action_items(content: str, source_label: str = "<input>") -> List[Dict[str, Any]]:
    """Parse JSON and extract list of action item objects."""
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
        raise ValueError(f"{source_label}: expected a JSON array or wrapped action-items object")

    results = []
    for item in items:
        if not isinstance(item, dict):
            continue
        desc = str(item.get("description") or item.get("content") or item.get("text") or "").strip()
        aid = str(item.get("id") or "").strip()
        if desc and aid:
            results.append(item)

    return results


def transform_to_todoist(
    action_items: List[Dict[str, Any]],
    label: str = "omi",
    project_id: str | None = None,
    include_completed: bool = False,
) -> List[Dict[str, Any]]:
    """Transform action items into Todoist task payloads."""
    tasks: List[Dict[str, Any]] = []

    for item in action_items:
        status = str(item.get("status") or "").lower()
        completed = item.get("completed") is True or status in ("completed", "done", "closed")
        if completed and not include_completed:
            continue

        desc = str(item.get("description") or item.get("content") or item.get("text") or "").strip()

        # Build description metadata notes
        notes = []
        if item.get("conversation_id"):
            notes.append(f"Conversation: {item['conversation_id']}")
        if item.get("created_at"):
            notes.append(f"Recorded: {str(item['created_at'])[:10]}")
        if item.get("notes"):
            notes.append(f"Notes: {item['notes']}")

        task: Dict[str, Any] = {
            "content": desc,
            "description": "\n".join(notes),
            "labels": [label] if label else [],
            "priority": 1,
        }

        if project_id:
            task["project_id"] = project_id

        due = item.get("due_at") or item.get("due_date")
        if due:
            # Todoist accepts YYYY-MM-DD for due_date or full ISO string
            due_str = str(due)
            task["due_date"] = due_str[:10]

        tasks.append(task)

    return tasks


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi action items JSON export into Todoist REST API task payloads."
    )
    parser.add_argument("inputs", nargs="*", help="Input JSON files or '-' for stdin")
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Destination JSON file (defaults to stdout)",
    )
    parser.add_argument(
        "--label",
        default="omi",
        help="Label tag to apply in Todoist (default: 'omi')",
    )
    parser.add_argument(
        "--project-id",
        help="Optional Todoist project ID to assign tasks to",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Include completed action items (default: only open items)",
    )
    args = parser.parse_args()

    if not args.inputs:
        parser.print_help()
        sys.exit(1)

    all_items: List[Dict[str, Any]] = []
    for src in args.inputs:
        if str(src) == "-":
            content = sys.stdin.read()
            all_items.extend(extract_action_items(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_items.extend(extract_action_items(content, str(p)))

    todoist_tasks = transform_to_todoist(
        all_items,
        label=args.label,
        project_id=args.project_id,
        include_completed=args.all,
    )
    output_text = json.dumps(todoist_tasks, indent=2, ensure_ascii=False)

    if args.output != "-":
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_text, encoding="utf-8")
        print(f"Generated {len(todoist_tasks)} Todoist task payload(s) at {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(output_text + "\n")


if __name__ == "__main__":
    main()
