"""
Convert Omi tracked goals JSON exports to clean Markdown notes and dashboards
optimized for Obsidian Dataview, Notion, and Logseq.

Usage:
    # Export individual goal notes into an Obsidian vault directory
    python goals_to_markdown.py goals.json --output-dir ./vault/goals/

    # Pipe directly from omi CLI and generate a consolidated dashboard
    omi --json goal list | python goals_to_markdown.py - --dashboard -o ./goals_dashboard.md
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def render_progress_bar(current: Any, target: Any, width: int = 10) -> str:
    """Render a clean Unicode text progress bar [████░░░░░░] 40%."""
    try:
        c = float(current)
        t = float(target)
        if t <= 0:
            return "[░░░░░░░░░░] N/A"
        ratio = max(0.0, min(1.0, c / t))
        filled = int(round(ratio * width))
        bar = "█" * filled + "░" * (width - filled)
        return f"[{bar}] {ratio * 100:.1f}%"
    except (ValueError, TypeError, ZeroDivisionError):
        return "[░░░░░░░░░░] N/A"


def slugify(text: str) -> str:
    """Create a filesystem-safe filename slug."""
    text = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[-\s]+", "_", text)[:50] or "goal"


def format_iso_datetime(iso_str: Optional[str]) -> str:
    """Normalize ISO-8601 timestamps to readable UTC YYYY-MM-DD HH:MM:SS format."""
    if not iso_str or not isinstance(iso_str, str):
        return "N/A"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return str(iso_str)


def goal_to_markdown(goal: Dict[str, Any]) -> str:
    """Convert a single goal dict to formatted Markdown with YAML frontmatter."""
    goal_id = goal.get("id", "unknown")
    title = goal.get("title") or "Untitled Goal"
    goal_type = goal.get("goal_type") or "numeric"
    current = goal.get("current_value", 0)
    target = goal.get("target_value", 0)
    unit = goal.get("unit") or ""
    is_active = bool(goal.get("is_active", True))
    created_at = goal.get("created_at") or ""
    updated_at = goal.get("updated_at") or ""

    status_str = "Active" if is_active else "Completed / Inactive"
    status_tag = "active" if is_active else "completed"
    progress = render_progress_bar(current, target)

    unit_suffix = f" {unit}" if unit else ""

    lines = [
        "---",
        f"id: {json.dumps(str(goal_id))}",
        f"title: {json.dumps(str(title))}",
        f"goal_type: {json.dumps(str(goal_type))}",
        f"current_value: {current}",
        f"target_value: {target}",
        f"unit: {json.dumps(str(unit))}",
        f"is_active: {'true' if is_active else 'false'}",
        "tags:",
        "  - omi",
        "  - goal",
        f"  - {status_tag}",
        "---",
        "",
        f"# {title}",
        "",
        f"**Status:** `{status_str}` | **Type:** `{goal_type}`",
        f"**Progress:** `{progress}`",
        f"**Current:** `{current}{unit_suffix}` / **Target:** `{target}{unit_suffix}`",
        "",
        "## Details",
        "",
        f"- **Min Value:** {goal.get('min_value', 0)}",
        f"- **Max Value:** {goal.get('max_value', 100)}",
        f"- **Created:** {format_iso_datetime(created_at)}",
        f"- **Last Updated:** {format_iso_datetime(updated_at)}",
        "",
    ]
    return "\n".join(lines)


def generate_dashboard(items: List[Dict[str, Any]]) -> str:
    """Generate a single dashboard markdown file summarizing all goals."""
    active_goals = [g for g in items if g.get("is_active", True)]
    inactive_goals = [g for g in items if not g.get("is_active", True)]

    lines = [
        "# Omi Goals Dashboard",
        "",
        f"**Active Goals:** {len(active_goals)} | **Completed / Inactive:** {len(inactive_goals)}",
        "",
        "## Active Goals",
        "",
        "| Goal | Type | Current | Target | Progress |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]

    for g in active_goals:
        title = g.get("title", "Untitled")
        g_type = g.get("goal_type", "numeric")
        current = g.get("current_value", 0)
        target = g.get("target_value", 0)
        unit = f" {g.get('unit')}" if g.get("unit") else ""
        bar = render_progress_bar(current, target, width=8)
        lines.append(f"| **{title}** | `{g_type}` | {current}{unit} | {target}{unit} | `{bar}` |")

    if inactive_goals:
        lines.extend([
            "",
            "## Completed / Inactive Goals",
            "",
            "| Goal | Type | Final Value | Target |",
            "| :--- | :--- | :--- | :--- |",
        ])
        for g in inactive_goals:
            title = g.get("title", "Untitled")
            g_type = g.get("goal_type", "numeric")
            current = g.get("current_value", 0)
            target = g.get("target_value", 0)
            unit = f" {g.get('unit')}" if g.get("unit") else ""
            lines.append(f"| {title} | `{g_type}` | {current}{unit} | {target}{unit} |")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi goals JSON exports to structured Markdown notes or dashboard."
    )
    parser.add_argument(
        "input",
        help="Path to JSON file (or '-' for stdin).",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=None,
        help="Directory to write individual goal markdown files.",
    )
    parser.add_argument(
        "--dashboard",
        "-d",
        type=Path,
        default=None,
        help="Path to generate a single consolidated dashboard markdown file.",
    )

    args = parser.parse_args()

    if not args.output_dir and not args.dashboard:
        args.output_dir = Path("./goals_md")

    try:
        if args.input == "-":
            raw_data = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
        else:
            raw_data = Path(args.input).read_bytes().decode("utf-8-sig", errors="replace")

        items = json.loads(raw_data)
        if isinstance(items, dict):
            items = (
                items.get("goals")
                or items.get("items")
                or items.get("data")
                or [items]
            )
        if not isinstance(items, list):
            sys.stderr.write("Error: Expected a JSON array of goals.\n")
            return 1
    except Exception as exc:
        sys.stderr.write(f"Error reading JSON: {exc}\n")
        return 1

    if args.dashboard:
        args.dashboard.parent.mkdir(parents=True, exist_ok=True)
        content = generate_dashboard(items)
        args.dashboard.write_text(content, encoding="utf-8")
        sys.stderr.write(f"Generated goals dashboard: {args.dashboard}\n")

    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        for g in items:
            if not isinstance(g, dict):
                continue
            gid = g.get("id", f"goal_{count}")
            slug = slugify(g.get("title") or "goal")
            filepath = args.output_dir / f"{slug}_{str(gid)[:8]}.md"
            filepath.write_text(goal_to_markdown(g), encoding="utf-8")
            count += 1
        sys.stderr.write(f"Exported {count} goal notes to {args.output_dir}/\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
