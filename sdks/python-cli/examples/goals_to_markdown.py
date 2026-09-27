#!/usr/bin/env python3
"""Convert Omi goals JSON exports to clean Markdown progress dashboards for Obsidian, Notion, or personal tracking vaults.

Usage:
    # Pipe directly from omi CLI
    omi --json goal list | python goals_to_markdown.py -

    # Export to a dedicated single Markdown note (e.g. for an Obsidian vault)
    omi --json goal list | python goals_to_markdown.py - --output ~/vault/Goals.md

    # Export into type-specific or status-specific notes in a folder
    python goals_to_markdown.py goals.json --output-dir ./vault/goals/ --group-by type

    # Filter only active goals
    omi --json goal list | python goals_to_markdown.py - --active-only
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

TYPE_LABELS: Dict[str, Dict[str, str]] = {
    "numeric": {"label": "Numeric Goals", "emoji": "📊"},
    "boolean": {"label": "Daily Habits & Boolean Targets", "emoji": "🎯"},
    "scale": {"label": "Scale & Quality Metrics", "emoji": "📈"},
    "other": {"label": "Other Goals", "emoji": "📌"},
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


def render_progress_bar(percentage: float, width: int = 10) -> str:
    """Render an ASCII progress bar from a 0.0 to 100.0 percentage."""
    clamped = max(0.0, min(100.0, percentage))
    filled = int(round((clamped / 100.0) * width))
    empty = width - filled
    return f"[{'█' * filled}{'░' * empty}] {clamped:.0f}%"


def calculate_progress(item: Dict[str, Any]) -> tuple[float, str]:
    """Calculate progress percentage and human-readable progress string."""
    goal_type = str(item.get("goal_type") or "numeric").lower()
    current = float(item.get("current_value") or 0.0)
    target = float(item.get("target_value") or 0.0)
    min_val = float(item.get("min_value") or 0.0)
    unit = str(item.get("unit") or "").strip()

    unit_str = f" {unit}" if unit else ""

    if goal_type == "boolean":
        is_done = current >= target if target > 0 else bool(current)
        pct = 100.0 if is_done else 0.0
        label = "Done" if is_done else "In Progress"
        return pct, label

    # Numeric or Scale
    span = target - min_val
    if span <= 0:
        pct = 100.0 if current >= target else 0.0
    else:
        pct = max(0.0, min(100.0, ((current - min_val) / span) * 100.0))

    # Format values concisely
    def fmt_num(val: float) -> str:
        return f"{val:g}"

    detail = f"{fmt_num(current)}/{fmt_num(target)}{unit_str}"
    return pct, detail


def format_goal_item(item: Dict[str, Any], include_metadata: bool = True) -> str:
    """Format a single goal dictionary into a Markdown task line."""
    is_active = bool(item.get("is_active", True))
    title = str(item.get("title") or "").strip().replace("\r\n", " ").replace("\n", " ")
    if not title:
        title = "Untitled Goal"

    pct, progress_detail = calculate_progress(item)
    is_completed = pct >= 100.0 or not is_active
    box = "[x]" if is_completed else "[ ]"

    bar = render_progress_bar(pct)
    line = f"- {box} **{title}** — {bar} ({progress_detail})"

    if include_metadata:
        meta_tags: List[str] = []
        goal_type = item.get("goal_type")
        if goal_type:
            meta_tags.append(f"`#{goal_type}`")

        updated_at = parse_datetime(item.get("updated_at") or item.get("created_at"))
        if updated_at:
            meta_tags.append(f"🕒 {updated_at.strftime('%Y-%m-%d UTC')}")

        gid = item.get("id")
        if gid:
            meta_tags.append(f"🆔 `{gid}`")

        if meta_tags:
            line += f" <!-- {' · '.join(meta_tags)} -->"

    return line


def unwrap_goals(data: Any) -> List[Dict[str, Any]]:
    """Unwrap a list of goals from various payload envelopes."""
    if isinstance(data, list):
        return [g for g in data if isinstance(g, dict)]
    if isinstance(data, dict):
        for key in ("goals", "items", "data", "results"):
            val = data.get(key)
            if isinstance(val, list):
                return [g for g in val if isinstance(g, dict)]
    return []


def generate_frontmatter(goals: List[Dict[str, Any]], title: str = "Omi Goals") -> str:
    """Generate YAML frontmatter summarizing the goals collection."""
    total = len(goals)
    active = sum(1 for g in goals if bool(g.get("is_active", True)))
    completed = total - active

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

    return f"""---
title: "{title}"
type: goals
total: {total}
active: {active}
completed: {completed}
tags:
  - omi
  - goals
  - habits
updated_at: "{now_iso}"
---
"""


def goals_to_markdown(
    goals: List[Dict[str, Any]],
    title: str = "Omi Goals",
    group_by: Optional[str] = None,
) -> str:
    """Convert a list of goals into a formatted Markdown document."""
    fm = generate_frontmatter(goals, title=title)
    lines: List[str] = [fm, f"# {title}\n"]

    if not goals:
        lines.append("_No goals found._\n")
        return "".join(lines)

    if group_by == "type":
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for g in goals:
            gtype = str(g.get("goal_type") or "other").lower()
            groups.setdefault(gtype, []).append(g)

        for gtype, items in sorted(groups.items()):
            meta = TYPE_LABELS.get(gtype, TYPE_LABELS["other"])
            lines.append(f"## {meta['emoji']} {meta['label']} ({len(items)})\n")
            for item in items:
                lines.append(format_goal_item(item))
            lines.append("")

    elif group_by == "status":
        active_items = [g for g in goals if bool(g.get("is_active", True))]
        completed_items = [g for g in goals if not bool(g.get("is_active", True))]

        if active_items:
            lines.append(f"## 🎯 Active Goals ({len(active_items)})\n")
            for item in active_items:
                lines.append(format_goal_item(item))
            lines.append("")

        if completed_items:
            lines.append(f"## ✅ Completed / Inactive ({len(completed_items)})\n")
            for item in completed_items:
                lines.append(format_goal_item(item))
            lines.append("")
    else:
        # Default: list all active first, then completed
        active_items = [g for g in goals if bool(g.get("is_active", True))]
        completed_items = [g for g in goals if not bool(g.get("is_active", True))]

        for item in active_items:
            lines.append(format_goal_item(item))
        if completed_items:
            lines.append("\n### Completed & Inactive\n")
            for item in completed_items:
                lines.append(format_goal_item(item))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def sanitize_filename(name: str) -> str:
    """Sanitize a string into a safe file name, preventing directory traversal."""
    cleaned = re.sub(r'[/\\?%*:|"<>]', "_", name)
    cleaned = re.sub(r"\.\.+", "_", cleaned)
    return cleaned.strip(" ._") or "goals"


def write_directory_export(
    goals: List[Dict[str, Any]],
    output_dir: Path,
    group_by: str,
) -> None:
    """Write grouped goals into separate Markdown files in output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)

    if group_by == "type":
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for g in goals:
            gtype = str(g.get("goal_type") or "other").lower()
            groups.setdefault(gtype, []).append(g)

        for gtype, items in groups.items():
            meta = TYPE_LABELS.get(gtype, TYPE_LABELS["other"])
            fname = sanitize_filename(f"{gtype}_goals.md")
            content = goals_to_markdown(items, title=f"{meta['label']}")
            (output_dir / fname).write_text(content, encoding="utf-8")

    elif group_by == "status":
        active_items = [g for g in goals if bool(g.get("is_active", True))]
        completed_items = [g for g in goals if not bool(g.get("is_active", True))]

        if active_items:
            fname = sanitize_filename("active_goals.md")
            content = goals_to_markdown(active_items, title="Active Goals")
            (output_dir / fname).write_text(content, encoding="utf-8")

        if completed_items:
            fname = sanitize_filename("completed_goals.md")
            content = goals_to_markdown(completed_items, title="Completed Goals")
            (output_dir / fname).write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi goals JSON exports to clean Markdown progress notes.",
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="-",
        help="Input JSON file path, or '-' to read from standard input (default: -)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Path to single output Markdown file",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory to write grouped Markdown notes into",
    )
    parser.add_argument(
        "--group-by",
        choices=["type", "status"],
        help="Group goals by goal_type or active status",
    )
    parser.add_argument(
        "--active-only",
        action="store_true",
        help="Filter and export only active goals",
    )
    parser.add_argument(
        "--title",
        default="Omi Goals",
        help="Custom document title (default: Omi Goals)",
    )

    args = parser.parse_args()

    if args.input == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(args.input).read_text(encoding="utf-8-sig")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"Error parsing JSON input: {exc}", file=sys.stderr)
        sys.exit(1)

    goals = unwrap_goals(data)

    if args.active_only:
        goals = [g for g in goals if bool(g.get("is_active", True))]

    if args.output_dir:
        write_directory_export(goals, args.output_dir, group_by=args.group_by or "type")
        print(f"Exported {len(goals)} goals to directory: {args.output_dir}")
        return

    md_output = goals_to_markdown(goals, title=args.title, group_by=args.group_by)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(md_output, encoding="utf-8")
        print(f"Exported {len(goals)} goals to {args.output}")
    else:
        sys.stdout.write(md_output)


if __name__ == "__main__":
    main()
