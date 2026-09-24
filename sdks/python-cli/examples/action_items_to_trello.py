#!/usr/bin/env python3
"""Convert Omi action items JSON export into a Trello board import JSON file.

Usage:
    python action_items_to_trello.py action_items.json -o trello_board.json
    omi --json action-item list | python action_items_to_trello.py - --board-name "Sprint Tasks" -o trello.json

Generates a standard Trello board JSON structure containing:
- Lists: "To Do" (open items) and "Completed" (done items)
- Cards: action item descriptions, due dates, completion state, and conversation references.
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


def transform_to_trello_board(
    action_items: List[Dict[str, Any]], board_name: str = "Omi Action Items"
) -> Dict[str, Any]:
    """Transform action items into standard Trello board JSON schema."""
    list_todo_id = "list_todo_001"
    list_done_id = "list_done_002"

    lists = [
        {"id": list_todo_id, "name": "To Do", "closed": False, "pos": 1},
        {"id": list_done_id, "name": "Completed", "closed": False, "pos": 2},
    ]

    cards: List[Dict[str, Any]] = []

    for idx, item in enumerate(action_items, start=1):
        aid = str(item.get("id"))
        desc = str(item.get("description") or item.get("content") or item.get("text") or "").strip()
        status = str(item.get("status") or "").lower()
        completed = item.get("completed") is True or status in ("completed", "done", "closed")

        card_list_id = list_done_id if completed else list_todo_id

        # Description / details
        notes = []
        if item.get("conversation_id"):
            notes.append(f"Conversation: {item['conversation_id']}")
        if item.get("created_at"):
            notes.append(f"Created: {item['created_at']}")
        if item.get("notes"):
            notes.append(f"Notes: {item['notes']}")

        card = {
            "id": f"card_{aid}",
            "name": desc,
            "desc": "\n".join(notes),
            "idList": card_list_id,
            "closed": False,
            "due": item.get("due_at") or item.get("due_date"),
            "dueComplete": completed,
            "pos": idx * 65536,
        }
        cards.append(card)

    return {
        "name": board_name,
        "desc": "Imported from Omi action items",
        "closed": False,
        "lists": lists,
        "cards": cards,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi action items JSON export into a Trello board import JSON file."
    )
    parser.add_argument("inputs", nargs="*", help="Input JSON files or '-' for stdin")
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Destination file (defaults to stdout)",
    )
    parser.add_argument(
        "--board-name",
        default="Omi Action Items",
        help="Custom board title (default: 'Omi Action Items')",
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

    trello_data = transform_to_trello_board(all_items, args.board_name)
    output_text = json.dumps(trello_data, indent=2, ensure_ascii=False)

    if args.output != "-":
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_text, encoding="utf-8")
        print(
            f"Wrote Trello board '{args.board_name}' with {len(trello_data['cards'])} cards to {args.output}",
            file=sys.stderr,
        )
    else:
        sys.stdout.write(output_text + "\n")


if __name__ == "__main__":
    main()
