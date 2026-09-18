"""
Convert Omi memories JSON exports to clean Markdown notes for Obsidian, Notion, Logseq, or personal knowledge bases.

Usage:
    # Pipe directly from omi CLI
    omi --json memory list | python memories_to_markdown.py -

    # Export to a specific Markdown file (single vault note)
    omi --json memory list | python memories_to_markdown.py - --output ~/vault/Memories.md

    # Export into category-specific or daily notes in a directory
    python memories_to_markdown.py memories.json --output-dir ./vault/memories/ --group-by category

    # Filter specific categories (e.g. work and learnings)
    omi --json memory list | python memories_to_markdown.py - --category work,learnings
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


CATEGORY_META: Dict[str, Dict[str, str]] = {
    "work": {"label": "Work", "emoji": "💼"},
    "skills": {"label": "Skills", "emoji": "🎯"},
    "learnings": {"label": "Learnings", "emoji": "🧠"},
    "interests": {"label": "Interests", "emoji": "💡"},
    "habits": {"label": "Habits", "emoji": "⚡"},
    "lifestyle": {"label": "Lifestyle", "emoji": "🌿"},
    "hobbies": {"label": "Hobbies", "emoji": "🎨"},
    "core": {"label": "Core Facts", "emoji": "📌"},
    "interesting": {"label": "Interesting", "emoji": "✨"},
    "manual": {"label": "Manual Notes", "emoji": "✍️"},
    "workflow": {"label": "Workflow", "emoji": "🔄"},
    "system": {"label": "System", "emoji": "⚙️"},
    "other": {"label": "Other Facts", "emoji": "📝"},
}


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


def get_category_header(cat: str) -> str:
    """Return formatted header string with emoji for a given category name."""
    cat_lower = (cat or "").strip().lower()
    meta = CATEGORY_META.get(cat_lower)
    if meta:
        return f"## {meta['emoji']} {meta['label']}"
    formatted_label = cat.replace("_", " ").title() if cat else "Uncategorized"
    return f"## 📁 {formatted_label}"


def format_memory_item(item: Dict[str, Any], include_metadata: bool = True) -> str:
    """Format a single memory dictionary into a Markdown list entry."""
    content = str(item.get("content") or "").strip().replace("\r\n", " ").replace("\n", " ")
    if not content:
        content = "_Untitled memory_"

    parts = [f"- {content}"]

    if include_metadata:
        meta_tags: List[str] = []

        cat = str(item.get("category") or "").strip().lower()
        if cat:
            meta_tags.append(f"📁 `{cat}`")

        tags = item.get("tags")
        if isinstance(tags, list):
            for t in tags:
                if t:
                    safe_tag = re.sub(r"[^\w-]", "", str(t)).strip()
                    if safe_tag:
                        meta_tags.append(f"#{safe_tag}")

        vis = item.get("visibility")
        if vis and str(vis).strip().lower() == "private":
            meta_tags.append("🔒 `private`")

        created_dt = parse_datetime(item.get("created_at"))
        if created_dt:
            meta_tags.append(f"📅 {created_dt.strftime('%Y-%m-%d')}")

        mem_id = item.get("id")
        if mem_id:
            safe_id = re.sub(r"[^\w-]", "", str(mem_id))
            if safe_id:
                meta_tags.append(f"`#{safe_id}`")

        if meta_tags:
            parts.append(f"  *({' · '.join(meta_tags)})*")

    return "\n".join(parts)


def memories_to_markdown(
    items: List[Dict[str, Any]],
    title: str = "Omi Memories & Knowledge Base",
    group_by: str = "category",
) -> str:
    """Render a list of memories into a structured Markdown document with YAML frontmatter."""
    total = len(items)
    categories_found: Set[str] = set()
    for it in items:
        cat = str(it.get("category") or "").strip().lower()
        if cat:
            categories_found.add(cat)

    now_iso = datetime.now(timezone.utc).isoformat()

    lines: List[str] = [
        "---",
        "type: omi-memories",
        f"total: {total}",
        f"categories_count: {len(categories_found)}",
        "categories:",
    ]
    for c in sorted(categories_found):
        lines.append(f"  - {c}")

    lines.extend([
        f"exported_at: {json.dumps(now_iso)}",
        "tags:",
        "  - omi",
        "  - memories",
        "  - second-brain",
        "  - knowledge-base",
        "---",
        "",
        f"# {title}",
        "",
        f"> **Summary:** {total} memories across {len(categories_found)} categories. Exported from Omi CLI.",
        "",
    ])

    if not items:
        lines.append("_No memories found matching criteria._")
        lines.append("")
        return "\n".join(lines)

    if group_by == "category":
        category_groups: Dict[str, List[Dict[str, Any]]] = {}
        for it in items:
            cat = str(it.get("category") or "").strip().lower()
            key = cat if cat else "other"
            category_groups.setdefault(key, []).append(it)

        known_order = [
            "work", "skills", "learnings", "interests", "habits",
            "lifestyle", "hobbies", "core", "interesting", "workflow",
            "manual", "system", "other",
        ]
        ordered_keys = [k for k in known_order if k in category_groups]
        for k in sorted(category_groups.keys()):
            if k not in ordered_keys:
                ordered_keys.append(k)

        for cat_key in ordered_keys:
            group_items = category_groups[cat_key]
            lines.append(get_category_header(cat_key))
            lines.append("")
            for it in group_items:
                lines.append(format_memory_item(it))
            lines.append("")

    elif group_by == "date":
        date_groups: Dict[str, List[Dict[str, Any]]] = {}
        for it in items:
            created_dt = parse_datetime(it.get("created_at"))
            key = created_dt.strftime("%Y-%m-%d") if created_dt else "Undated"
            date_groups.setdefault(key, []).append(it)

        for date_key in sorted(date_groups.keys(), reverse=True):
            lines.append(f"## 📅 {date_key}")
            lines.append("")
            for it in date_groups[date_key]:
                lines.append(format_memory_item(it))
            lines.append("")

    else:
        for it in items:
            lines.append(format_memory_item(it))
        lines.append("")

    return "\n".join(lines)


def filter_memories(
    items: List[Dict[str, Any]],
    category_filter: Optional[str] = None,
    visibility_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Filter memories by category and/or visibility."""
    filtered = items

    if category_filter:
        target_cats = {c.strip().lower() for c in category_filter.split(",") if c.strip()}
        filtered = [
            it for it in filtered
            if str(it.get("category") or "").strip().lower() in target_cats
        ]

    if visibility_filter:
        target_vis = visibility_filter.strip().lower()
        if target_vis in {"public", "private"}:
            filtered = [
                it for it in filtered
                if str(it.get("visibility") or "").strip().lower() == target_vis
            ]

    return filtered


def write_grouped_directory(
    items: List[Dict[str, Any]],
    output_dir: Path,
    group_by: str = "category",
    title_prefix: str = "Omi Memories",
) -> List[Path]:
    """Write memories into separate Markdown files in an output directory safely."""
    output_dir.mkdir(parents=True, exist_ok=True)
    resolved_dir = output_dir.resolve()
    written_files: List[Path] = []

    groups: Dict[str, List[Dict[str, Any]]] = {}
    if group_by == "date":
        for it in items:
            created_dt = parse_datetime(it.get("created_at"))
            date_str = created_dt.strftime("%Y-%m-%d") if created_dt else "undated"
            groups.setdefault(date_str, []).append(it)
    else:
        for it in items:
            cat = str(it.get("category") or "").strip().lower()
            key = cat if cat else "other"
            groups.setdefault(key, []).append(it)

    for group_key, group_items in sorted(groups.items()):
        safe_key = re.sub(r"[^\w-]", "_", group_key).strip("_") or "memories"
        filename = f"{safe_key}_memories.md"
        target_path = (output_dir / filename).resolve()

        if not str(target_path).startswith(str(resolved_dir)):
            continue

        doc_title = f"{title_prefix} — {group_key.replace('_', ' ').title()}"
        content = memories_to_markdown(group_items, title=doc_title, group_by="none")
        target_path.write_text(content, encoding="utf-8")
        written_files.append(target_path)

    return written_files


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi memories JSON exports to clean Markdown notes for Obsidian, Notion, and second brains."
    )
    parser.add_argument(
        "input",
        help="Path to JSON file containing memories, or '-' to read from stdin.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Path to single output Markdown file. Defaults to stdout if omitted and --output-dir is not set.",
    )
    parser.add_argument(
        "--output-dir",
        "-d",
        type=Path,
        default=None,
        help="Directory to write separated Markdown files (grouped by category or date).",
    )
    parser.add_argument(
        "--category",
        "-c",
        type=str,
        default=None,
        help="Filter by category (comma-separated list, e.g. 'work,skills,learnings').",
    )
    parser.add_argument(
        "--visibility",
        type=str,
        choices=["all", "public", "private"],
        default="all",
        help="Filter by visibility (default: all).",
    )
    parser.add_argument(
        "--group-by",
        "-g",
        choices=["category", "date", "none"],
        default="category",
        help="Grouping strategy for notes (default: category).",
    )
    parser.add_argument(
        "--title",
        "-t",
        type=str,
        default="Omi Memories & Knowledge Base",
        help="Custom header title for the generated document.",
    )

    args = parser.parse_args()

    # Ensure stdout handles UTF-8 (e.g. on Windows default cp1252 consoles)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # Read input payload
    try:
        if args.input == "-":
            raw_data = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
        else:
            input_path = Path(args.input)
            if not input_path.exists():
                sys.stderr.write(f"Error: Input file does not exist: {args.input}\n")
                return 1
            raw_data = input_path.read_bytes().decode("utf-8-sig", errors="replace")

        if not raw_data.strip():
            sys.stderr.write("Error: Input payload is empty.\n")
            return 1

        payload = json.loads(raw_data)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"Error: Invalid JSON input: {exc}\n")
        return 1
    except Exception as exc:
        sys.stderr.write(f"Error reading input: {exc}\n")
        return 1

    if isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict):
        raw_items = payload.get("memories") or payload.get("items") or [payload]
    else:
        sys.stderr.write("Error: Expected a JSON array of memories or object containing 'memories'.\n")
        return 1

    items = filter_memories(
        raw_items,
        category_filter=args.category,
        visibility_filter=args.visibility if args.visibility != "all" else None,
    )

    try:
        if args.output_dir:
            written = write_grouped_directory(
                items,
                args.output_dir,
                group_by=args.group_by,
                title_prefix=args.title,
            )
            sys.stderr.write(f"Successfully wrote {len(written)} file(s) into {args.output_dir}\n")
            return 0

        markdown_doc = memories_to_markdown(
            items,
            title=args.title,
            group_by=args.group_by,
        )

        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(markdown_doc, encoding="utf-8")
            sys.stderr.write(f"Successfully exported {len(items)} memory/memories to {args.output}\n")
        else:
            try:
                sys.stdout.write(markdown_doc)
            except UnicodeEncodeError:
                sys.stdout.buffer.write(markdown_doc.encode("utf-8", errors="replace"))

        return 0
    except Exception as exc:
        sys.stderr.write(f"Error during export: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
