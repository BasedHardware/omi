"""
Convert Omi action items JSON exports to clean Markdown task lists for Obsidian, Notion, or personal task managers.

Usage:
    # Pipe directly from omi CLI
    omi --json action-item list | python action_items_to_markdown.py -

    # Export to a specific Markdown file
    omi --json action-item list | python action_items_to_markdown.py - --output ~/vault/Tasks.md

    # Export into daily / grouped notes in a folder
    python action_items_to_markdown.py action_items.json --output-dir ./vault/tasks/ --group-by date

    # Filter only open/pending tasks
    omi --json action-item list --open | python action_items_to_markdown.py - --status open
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional



def parse_datetime(iso_str: Optional[str]) -> Optional[datetime]:
    """Safely parse an ISO-8601 datetime string and normalize to UTC."""
    if not iso_str or not isinstance(iso_str, str):
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception:
        return None


def format_action_item(item: Dict[str, Any], include_metadata: bool = True) -> str:
    """Format a single action item dictionary into a Markdown task line."""
    completed = bool(item.get("completed", False))
    desc = str(item.get("description") or "").strip().replace("\r\n", " ").replace("\n", " ")
    if not desc:
        desc = "Untitled action item"

    box = "[x]" if completed else "[ ]"
    parts = [f"- {box} {desc}"]

    if include_metadata:
        meta_tags: List[str] = []
        due_at = parse_datetime(item.get("due_at"))
        if due_at:
            meta_tags.append(f"📅 Due: {due_at.strftime('%Y-%m-%d %H:%M UTC')}")

        conv_id = item.get("conversation_id")
        if conv_id:
            safe_conv_id = re.sub(r"[^\w-]", "", str(conv_id))
            link_target = safe_conv_id if (safe_conv_id.startswith("conversation") or safe_conv_id.startswith("conv_")) else f"conversation_{safe_conv_id}"
            meta_tags.append(f"🔗 [[{link_target}]]")

        item_id = item.get("id")
        if item_id:
            safe_id = re.sub(r"[^\w-]", "", str(item_id))
            meta_tags.append(f"`#{safe_id}`")

        if meta_tags:
            parts.append(f"  *({' · '.join(meta_tags)})*")

    return "\n".join(parts)


def items_to_markdown(
    items: List[Dict[str, Any]],
    title: str = "Omi Action Items",
    group_by: str = "status",
) -> str:
    """Render a list of action items into a structured Markdown document with YAML frontmatter."""
    total = len(items)
    completed_count = sum(1 for it in items if it.get("completed"))
    open_count = total - completed_count

    now_iso = datetime.now(timezone.utc).isoformat()

    lines: List[str] = [
        "---",
        "type: action-items",
        f"total: {total}",
        f"open: {open_count}",
        f"completed: {completed_count}",
        f"exported_at: {json.dumps(now_iso)}",
        "tags:",
        "  - omi",
        "  - action-items",
        "  - tasks",
        "---",
        "",
        f"# {title}",
        "",
        f"> **Summary:** {open_count} open, {completed_count} completed ({total} total). Exported from Omi CLI.",
        "",
    ]

    if group_by == "status":
        open_items = [it for it in items if not it.get("completed")]
        done_items = [it for it in items if it.get("completed")]

        lines.append("## 📌 Pending Tasks")
        lines.append("")
        if open_items:
            for it in open_items:
                lines.append(format_action_item(it))
        else:
            lines.append("_No pending action items._")
        lines.append("")

        lines.append("## ✅ Completed Tasks")
        lines.append("")
        if done_items:
            for it in done_items:
                lines.append(format_action_item(it))
        else:
            lines.append("_No completed action items._")
        lines.append("")

    elif group_by == "date":
        # Group by due date (or creation date if due date is absent)
        dated_groups: Dict[str, List[Dict[str, Any]]] = {}
        for it in items:
            due_dt = parse_datetime(it.get("due_at"))
            created_dt = parse_datetime(it.get("created_at"))
            if due_dt:
                key = due_dt.strftime("%Y-%m-%d (Due)")
            elif created_dt:
                key = created_dt.strftime("%Y-%m-%d (Created)")
            else:
                key = "Undated"
            dated_groups.setdefault(key, []).append(it)

        for date_key in sorted(dated_groups.keys(), reverse=True):
            lines.append(f"## 📅 {date_key}")
            lines.append("")
            for it in dated_groups[date_key]:
                lines.append(format_action_item(it))
            lines.append("")

    else:
        # Flat list
        for it in items:
            lines.append(format_action_item(it))
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def load_input_data(input_src: str) -> List[Dict[str, Any]]:
    """Load and normalize action items from stdin or file."""
    if input_src == "-":
        raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
    else:
        path = Path(input_src)
        if not path.is_file():
            print(f"Error: file not found: {path}", file=sys.stderr)
            sys.exit(1)
        raw = path.read_text(encoding="utf-8-sig", errors="replace")

    raw = raw.strip().lstrip("\ufeff")
    if not raw:
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Error: Invalid JSON input: {exc}", file=sys.stderr)
        sys.exit(1)

    if isinstance(data, list):
        return [it for it in data if isinstance(it, dict)]
    elif isinstance(data, dict):
        if "items" in data and isinstance(data["items"], list):
            return [it for it in data["items"] if isinstance(it, dict)]
        if "action_items" in data and isinstance(data["action_items"], list):
            return [it for it in data["action_items"] if isinstance(it, dict)]
        # Single action item
        return [data]
    return []


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi action items JSON export to structured Markdown checklists."
    )
    parser.add_argument(
        "input",
        help="Path to JSON file, or '-' to read from stdin.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Path to output Markdown file. Defaults to stdout if not specified.",
    )
    parser.add_argument(
        "--output-dir",
        "-d",
        type=Path,
        default=None,
        help="Directory to write individual Markdown files (e.g. into an Obsidian vault).",
    )
    parser.add_argument(
        "--status",
        choices=["all", "open", "completed"],
        default="all",
        help="Filter items by status (default: all).",
    )
    parser.add_argument(
        "--group-by",
        choices=["status", "date", "none"],
        default="status",
        help="Grouping strategy for Markdown task sections (default: status).",
    )
    parser.add_argument(
        "--title",
        default="Omi Action Items",
        help="Document title header.",
    )

    args = parser.parse_args()

    items = load_input_data(args.input)

    # Filter by status if requested
    if args.status == "open":
        items = [it for it in items if not it.get("completed")]
    elif args.status == "completed":
        items = [it for it in items if it.get("completed")]

    if not items:
        msg = f"No action items found matching filter (status={args.status})."
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(f"# {args.title}\n\n_{msg}_\n", encoding="utf-8")
            print(f"Wrote empty checklist to {args.output}", file=sys.stderr)
        elif args.output_dir:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            empty_file = args.output_dir / "action_items.md"
            empty_file.write_text(f"# {args.title}\n\n_{msg}_\n", encoding="utf-8")
            print(f"Wrote empty checklist to {empty_file}", file=sys.stderr)
        else:
            sys.stdout.buffer.write(f"# {args.title}\n\n_{msg}_\n".encode("utf-8"))
        return

    # Handle output-dir mode (split into individual dates or files)
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        if args.group_by == "date":
            # Group items by date and save separate files
            groups: Dict[str, List[Dict[str, Any]]] = {}
            for it in items:
                due_dt = parse_datetime(it.get("due_at"))
                created_dt = parse_datetime(it.get("created_at"))
                dt = due_dt or created_dt
                date_str = dt.strftime("%Y-%m-%d") if dt else "undated"
                # Validate date prefix against regex to prevent traversal
                date_prefix = date_str if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str) else "undated"
                groups.setdefault(date_prefix, []).append(it)

            count = 0
            for date_key, group_items in sorted(groups.items()):
                filename = f"{date_key}_action_items.md"
                filepath = args.output_dir / filename
                content = items_to_markdown(
                    group_items,
                    title=f"Omi Action Items — {date_key}",
                    group_by="status",
                )
                filepath.write_text(content, encoding="utf-8")
                count += 1
            print(f"Exported {len(items)} action items into {count} date file(s) in {args.output_dir}", file=sys.stderr)
            return
        else:
            filepath = args.output_dir / "action_items.md"
            content = items_to_markdown(items, title=args.title, group_by=args.group_by)
            filepath.write_text(content, encoding="utf-8")
            print(f"Exported {len(items)} action items to {filepath}", file=sys.stderr)
            return

    # Single output or stdout
    content = items_to_markdown(items, title=args.title, group_by=args.group_by)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
        print(f"Exported {len(items)} action items to {args.output}", file=sys.stderr)
    else:
        sys.stdout.buffer.write(content.encode("utf-8"))


if __name__ == "__main__":
    main()
