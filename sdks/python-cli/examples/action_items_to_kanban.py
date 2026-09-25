#!/usr/bin/env python3
"""Convert Omi action items into a Markdown Kanban board.

Usage:
    python action_items_to_kanban.py action_items.json -o Kanban.md
    omi --json action-item list | python action_items_to_kanban.py - -o ~/vault/Tasks.md
    python action_items_to_kanban.py page1.json page2.json -o Board.md

Outputs a clean Markdown Kanban board with YAML frontmatter fully compatible
with the Obsidian Kanban plugin, Logseq, and GitHub Markdown checklists.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def parse_boolean(value: Any) -> bool:
    """Normalize completion status to a strict boolean."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "completed", "done")
    return False


def format_due_date(iso_str: Optional[str]) -> Optional[str]:
    """Extract clean YYYY-MM-DD date text for Kanban cards."""
    if not iso_str or not isinstance(iso_str, str):
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return iso_str[:10] if len(iso_str) >= 10 else iso_str


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


def render_kanban(items: List[Dict[str, Any]], title: str = "Omi Action Items Board") -> str:
    """Format action items into an Obsidian-compatible Markdown Kanban board."""
    todo_items: List[str] = []
    due_items: List[str] = []
    done_items: List[str] = []

    seen_ids = set()
    for item in items:
        iid = str(item.get("id"))
        if iid in seen_ids:
            continue
        seen_ids.add(iid)

        desc = str(item.get("description") or item.get("title") or "Untitled task").strip()
        desc = re.sub(r"\r\n|\r|\n", " ", desc)
        # Strip existing @YYYY-MM-DD date tag from description text to prevent duplicate due dates
        desc = re.sub(r"\s*@\d{4}-\d{2}-\d{2}\b", "", desc).strip()

        completed = parse_boolean(item.get("completed"))
        due = format_due_date(item.get("due_at"))

        card_parts = [f"- [{'x' if completed else ' '}] {desc}"]
        if due:
            card_parts.append(f"@{due}")
        card_parts.append(f"#{iid[:8]}")

        card_line = " ".join(card_parts)

        if completed:
            done_items.append(card_line)
        elif due:
            due_items.append(card_line)
        else:
            todo_items.append(card_line)

    lines: List[str] = [
        "---",
        "kanban-plugin: basic",
        f"total_tasks: {len(seen_ids)}",
        f"open_tasks: {len(todo_items) + len(due_items)}",
        f"completed_tasks: {len(done_items)}",
        "---",
        "",
        f"# {title}",
        "",
        "## 📅 Due / Scheduled",
        "",
    ]
    lines.extend(due_items if due_items else ["_No scheduled tasks._"])
    lines.extend([
        "",
        "## 📋 To Do",
        "",
    ])
    lines.extend(todo_items if todo_items else ["_No backlog tasks._"])
    lines.extend([
        "",
        "## ✅ Done",
        "",
    ])
    lines.extend(done_items if done_items else ["_No completed tasks._"])
    lines.append("")

    return "\n".join(lines)


def convert_to_kanban(
    sources: Sequence[str | Path],
    output_dest: Optional[str | Path] = None,
    title: str = "Omi Action Items Board",
) -> int:
    """Convert action items to Markdown Kanban board."""
    all_items: List[Dict[str, Any]] = []

    for src in sources:
        if str(src) == "-":
            content = sys.stdin.read()
            all_items.extend(extract_action_items(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_items.extend(extract_action_items(content, str(p)))

    board_md = render_kanban(all_items, title=title)

    if output_dest and str(output_dest) != "-":
        out_path = Path(output_dest)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(board_md, encoding="utf-8")
    else:
        sys.stdout.write(board_md)

    return len(all_items)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi action items into a Markdown Kanban board."
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
        help="Destination Markdown file (defaults to stdout)",
    )
    parser.add_argument(
        "-t",
        "--title",
        default="Omi Action Items Board",
        help="Title for the Kanban board",
    )
    args = parser.parse_args()

    try:
        count = convert_to_kanban(args.inputs, args.output, title=args.title)
        if args.output != "-":
            print(f"Exported {count} action item(s) to Kanban board at {args.output}", file=sys.stderr)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
