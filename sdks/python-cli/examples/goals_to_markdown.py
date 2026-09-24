#!/usr/bin/env python3
"""Convert Omi goals JSON exports to clean Markdown notes for Obsidian, Notion, or personal dashboards.

Usage:
    # Pipe directly from omi CLI
    omi --json goal list | python goals_to_markdown.py -

    # Export to a single Markdown dashboard file
    omi --json goal list | python goals_to_markdown.py - -o ~/vault/Goals.md

    # Export into individual notes in an Obsidian/Notion vault
    python goals_to_markdown.py goals.json --output-dir ./vault/goals/

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
from typing import Any, Dict, List, Optional, Sequence


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


def format_progress_bar(current: Any, target: Any, width: int = 10) -> str:
    """Render a visual Unicode progress bar with percentage."""
    if current is None or target is None:
        return f"[{'░' * width}] 0.0%"
    try:
        c = float(current)
        t = float(target)
        if t <= 0:
            return f"[{'░' * width}] 0.0%"
        pct = min(max(c / t, 0.0), 1.0)
        filled = int(round(pct * width))
        empty = width - filled
        pct_display = round((c / t) * 100.0, 1)
        return f"[{'█' * filled}{'░' * empty}] {pct_display}%"
    except (ValueError, TypeError, ZeroDivisionError):
        return f"[{'░' * width}] 0.0%"


def get_status_badge(item: Dict[str, Any]) -> str:
    """Return an emoji status badge for a goal item."""
    is_active = item.get("is_active")
    curr = item.get("current_value")
    target = item.get("target_value")

    try:
        if curr is not None and target is not None and float(target) > 0 and float(curr) >= float(target):
            return "🏁 Completed"
    except (ValueError, TypeError):
        pass

    if is_active in (True, 1, "true", "1", "yes", "active"):
        return "🟢 Active"
    return "⚪ Inactive"


def slugify(text: str) -> str:
    """Create a safe filename slug."""
    text = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[-\s]+", "_", text)[:50] or "goal"


def extract_goals(content: str, source_label: str = "<input>") -> List[Dict[str, Any]]:
    """Parse JSON content and extract a list of goal dictionaries."""
    raw = content.lstrip("\ufeff")
    items = json.loads(raw)

    if isinstance(items, dict):
        for key in ("goals", "items", "data"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError(f"{source_label}: expected a JSON array or wrapped goals object")

    results: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source_label}: each goal must be a JSON object")
        if not item.get("id") or str(item.get("id")).strip() == "":
            raise ValueError(f"{source_label}: goal missing required 'id' field")
        results.append(item)

    return results


def goal_to_markdown_note(goal: Dict[str, Any]) -> str:
    """Format a single goal as a standalone Markdown note with YAML frontmatter."""
    goal_id = str(goal.get("id", "unknown"))
    title = goal.get("title") or goal.get("name") or goal.get("description") or "Untitled Goal"
    goal_type = goal.get("goal_type") or "general"
    unit = goal.get("unit") or ""
    curr = goal.get("current_value")
    target = goal.get("target_value")
    status = get_status_badge(goal)
    progress_bar = format_progress_bar(curr, target)

    created_dt = parse_datetime(goal.get("created_at"))
    updated_dt = parse_datetime(goal.get("updated_at"))
    created_str = created_dt.strftime("%Y-%m-%d %H:%M:%S UTC") if created_dt else ""

    lines: List[str] = [
        "---",
        f"id: {json.dumps(goal_id, ensure_ascii=False)}",
        f"title: {json.dumps(title, ensure_ascii=False)}",
        f"type: {json.dumps(goal_type, ensure_ascii=False)}",
        f"status: {json.dumps(status, ensure_ascii=False)}",
        f"current: {json.dumps(curr, ensure_ascii=False)}",
        f"target: {json.dumps(target, ensure_ascii=False)}",
        f"unit: {json.dumps(unit, ensure_ascii=False)}",
        f"created_at: {json.dumps(created_str, ensure_ascii=False)}",
        "tags:",
        "  - omi/goal",
        f"  - omi/goal/{slugify(goal_type)}",
        "---",
        "",
        f"# {title}",
        "",
        f"**Status**: {status}  ",
        f"**Type**: `{goal_type}`  ",
        f"**Progress**: `{progress_bar}`  ",
    ]

    if curr is not None or target is not None:
        unit_str = f" {unit}" if unit else ""
        c_disp = curr if curr is not None else 0
        t_disp = target if target is not None else "N/A"
        lines.append(f"**Target**: {c_disp} / {t_disp}{unit_str}")

    if goal.get("description") and goal.get("description") != title:
        lines.extend(["", "## Description", "", goal["description"]])

    return "\n".join(lines) + "\n"


def generate_dashboard(goals: Sequence[Dict[str, Any]]) -> str:
    """Generate a combined Markdown dashboard overview of all goals."""
    active_goals = [g for g in goals if "🟢" in get_status_badge(g)]
    completed_goals = [g for g in goals if "🏁" in get_status_badge(g)]
    inactive_goals = [g for g in goals if "⚪" in get_status_badge(g)]

    lines: List[str] = [
        "# 🎯 Goals Dashboard",
        "",
        f"Total: **{len(goals)}** | Active: **{len(active_goals)}** | Completed: **{len(completed_goals)}** | Inactive: **{len(inactive_goals)}**",
        "",
        "---",
        "",
    ]

    def render_section(heading: str, items: Sequence[Dict[str, Any]]) -> None:
        if not items:
            return
        lines.append(f"## {heading} ({len(items)})")
        lines.append("")
        for g in items:
            title = g.get("title") or g.get("name") or g.get("description") or "Untitled Goal"
            curr = g.get("current_value")
            target = g.get("target_value")
            unit = f" {g.get('unit')}" if g.get("unit") else ""
            progress = format_progress_bar(curr, target)
            val_text = f" ({curr}/{target}{unit})" if curr is not None and target is not None else ""
            lines.append(f"- **{title}** `{progress}`{val_text}")
        lines.append("")

    render_section("🟢 Active Goals", active_goals)
    render_section("🏁 Completed Goals", completed_goals)
    render_section("⚪ Inactive Goals", inactive_goals)

    return "\n".join(lines).strip() + "\n"


def convert_goals_to_markdown(
    sources: Sequence[str | Path],
    output_dest: Optional[str | Path] = None,
    output_dir: Optional[str | Path] = None,
    active_only: bool = False,
) -> int:
    """Process goal inputs and write Markdown output."""
    all_goals: List[Dict[str, Any]] = []

    for src in sources:
        if str(src) == "-":
            content = sys.stdin.read()
            all_goals.extend(extract_goals(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_goals.extend(extract_goals(content, str(p)))

    if active_only:
        all_goals = [g for g in all_goals if "🟢" in get_status_badge(g)]

    if output_dir:
        out_dir_path = Path(output_dir)
        out_dir_path.mkdir(parents=True, exist_ok=True)
        for g in all_goals:
            title = g.get("title") or g.get("name") or g.get("description") or "goal"
            filename = f"{slugify(title)}_{str(g.get('id'))[:8]}.md"
            note_content = goal_to_markdown_note(g)
            (out_dir_path / filename).write_text(note_content, encoding="utf-8")
        return len(all_goals)

    dashboard_text = generate_dashboard(all_goals)
    if output_dest and str(output_dest) != "-":
        out_path = Path(output_dest)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(dashboard_text, encoding="utf-8")
    else:
        sys.stdout.write(dashboard_text)

    return len(all_goals)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi goals JSON exports to clean Markdown notes and dashboards."
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
        "--output-dir",
        help="Directory to write individual Markdown notes per goal",
    )
    parser.add_argument(
        "--active-only",
        action="store_true",
        help="Filter and include only active goals",
    )
    args = parser.parse_args()

    try:
        count = convert_goals_to_markdown(
            args.inputs,
            output_dest=args.output,
            output_dir=args.output_dir,
            active_only=args.active_only,
        )
        if args.output != "-" or args.output_dir:
            dest = args.output_dir if args.output_dir else args.output
            print(f"Exported {count} goal(s) to {dest}", file=sys.stderr)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
