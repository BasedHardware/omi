"""
Convert Omi goals JSON exports to clean Markdown progress reports and task boards for Obsidian, Notion, or personal dashboards.

Usage:
    # Pipe directly from omi CLI
    omi --json goal list | python goals_to_markdown.py -

    # Export to a specific Markdown file
    omi --json goal list | python goals_to_markdown.py - --output ~/vault/Goals.md

    # Export into type-grouped or status-grouped notes in a directory
    python goals_to_markdown.py goals.json --output-dir ./vault/goals/ --group-by type

    # Filter only active goals
    omi --json goal list | python goals_to_markdown.py - --status active
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


GOAL_TYPE_META: Dict[str, Dict[str, str]] = {
    "target": {"label": "Target Milestone", "emoji": "🎯"},
    "metric": {"label": "Metric Tracker", "emoji": "📊"},
    "habit": {"label": "Habit / Consistency", "emoji": "⚡"},
    "boolean": {"label": "Yes/No Check", "emoji": "✅"},
    "custom": {"label": "Custom Goal", "emoji": "📌"},
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


def format_progress_bar(current: Optional[float], target: Optional[float], length: int = 10) -> str:
    """Render a text-based progress bar and completion percentage."""
    if target is None or target <= 0 or current is None:
        return ""
    ratio = min(max(current / target, 0.0), 1.0)
    filled = int(round(ratio * length))
    bar = "█" * filled + "░" * (length - filled)
    percent = int(ratio * 100)
    return f"[{bar}] {percent}%"


def format_goal(goal: Dict[str, Any], include_metadata: bool = True) -> str:
    """Format a single goal dictionary into Markdown."""
    title = str(goal.get("title") or "Untitled Goal").strip()
    goal_type = str(goal.get("goal_type") or "target").lower()
    is_active = bool(goal.get("is_active", True))

    type_info = GOAL_TYPE_META.get(goal_type, {"label": goal_type.capitalize(), "emoji": "🎯"})
    emoji = type_info["emoji"]

    status_tag = "🟢 Active" if is_active else "⚪ Completed"

    lines = [f"### {emoji} {title}"]

    current_val = goal.get("current_value")
    target_val = goal.get("target_value")
    unit = str(goal.get("unit") or "").strip()

    metrics: List[str] = [f"**Status:** {status_tag}", f"**Type:** {type_info['label']}"]

    if target_val is not None:
        unit_str = f" {unit}" if unit else ""
        curr_str = f"{current_val:g}" if isinstance(current_val, (int, float)) else str(current_val or 0)
        targ_str = f"{target_val:g}" if isinstance(target_val, (int, float)) else str(target_val)
        metrics.append(f"**Progress:** {curr_str} / {targ_str}{unit_str}")

        progress_bar = format_progress_bar(current_val, target_val)
        if progress_bar:
            metrics.append(f"`{progress_bar}`")

    lines.append(" • ".join(metrics))

    desc = str(goal.get("description") or "").strip()
    if desc:
        lines.append(f"\n{desc}")

    if include_metadata:
        created_at = parse_datetime(goal.get("created_at"))
        updated_at = parse_datetime(goal.get("updated_at"))
        meta_parts: List[str] = []
        if created_at:
            meta_parts.append(f"Created: {created_at.strftime('%Y-%m-%d')}")
        if updated_at:
            meta_parts.append(f"Updated: {updated_at.strftime('%Y-%m-%d')}")
        if goal.get("id"):
            meta_parts.append(f"ID: `{goal['id']}`")
        if meta_parts:
            lines.append(f"> *{' | '.join(meta_parts)}*")

    return "\n".join(lines)


def build_markdown_document(goals: List[Dict[str, Any]], title: str = "Omi Tracked Goals") -> str:
    """Generate a complete Markdown document from a list of goals."""
    active_goals = [g for g in goals if bool(g.get("is_active", True))]
    completed_goals = [g for g in goals if not bool(g.get("is_active", True))]

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    doc = [
        f"# {title}",
        "",
        "---",
        f"**Generated:** `{now}`  ",
        f"**Total Goals:** `{len(goals)}` (`{len(active_goals)} active`, `{len(completed_goals)} completed`)  ",
        "---",
        "",
        "## Active Goals",
        ""
    ]

    if active_goals:
        for g in active_goals:
            doc.append(format_goal(g))
            doc.append("")
    else:
        doc.append("*No active goals at this time.*")
        doc.append("")

    if completed_goals:
        doc.extend([
            "---",
            "",
            "## Completed / Inactive Goals",
            ""
        ])
        for g in completed_goals:
            doc.append(format_goal(g))
            doc.append("")

    return "\n".join(doc)


def main():
    parser = argparse.ArgumentParser(
        description="Convert Omi goals JSON exports to clean Markdown for Obsidian, Notion, or personal dashboards."
    )
    parser.add_argument("input", help="Path to JSON file, or '-' to read from standard input.")
    parser.add_argument("-o", "--output", help="Write Markdown to output file path instead of stdout.")
    parser.add_argument("--status", choices=["all", "active", "completed"], default="all", help="Filter by goal status.")
    parser.add_argument("--output-dir", help="Directory to save individual Markdown notes into.")
    parser.add_argument("--group-by", choices=["none", "type"], default="none", help="Group goals into separate notes.")

    args = parser.parse_args()

    # Read payload
    if args.input == "-":
        raw_text = sys.stdin.read()
    else:
        raw_text = Path(args.input).read_text(encoding="utf-8")

    if not raw_text.strip():
        print("Error: Empty input provided.", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(raw_text)
    except Exception as e:
        print(f"Error parsing JSON input: {e}", file=sys.stderr)
        sys.exit(1)

    goals = data if isinstance(data, list) else data.get("goals", [data])

    if args.status == "active":
        goals = [g for g in goals if bool(g.get("is_active", True))]
    elif args.status == "completed":
        goals = [g for g in goals if not bool(g.get("is_active", True))]

    if args.output_dir:
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        if args.group_by == "type":
            grouped: Dict[str, List[Dict[str, Any]]] = {}
            for g in goals:
                t = str(g.get("goal_type") or "custom").lower()
                grouped.setdefault(t, []).append(g)

            for gtype, items in grouped.items():
                label = GOAL_TYPE_META.get(gtype, {}).get("label", gtype.capitalize())
                content = build_markdown_document(items, title=f"Omi Goals - {label}")
                (out_dir / f"Goals_{gtype.capitalize()}.md").write_text(content, encoding="utf-8")
            print(f"Exported {len(goals)} goals grouped into {len(grouped)} category notes in {out_dir}")
        else:
            for g in goals:
                gid = str(g.get("id") or "goal")
                gtitle = re.sub(r'[\\/*?:"<>| ]', '_', str(g.get("title") or "Goal"))[:30]
                content = build_markdown_document([g], title=str(g.get("title") or "Goal"))
                (out_dir / f"{gtitle}_{gid[:8]}.md").write_text(content, encoding="utf-8")
            print(f"Exported {len(goals)} individual goal notes into {out_dir}")
        return

    content = build_markdown_document(goals)

    if args.output:
        out_file = Path(args.output)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(content, encoding="utf-8")
        print(f"Successfully exported {len(goals)} goals to {out_file}")
    else:
        sys.stdout.write(content + "\n")


if __name__ == "__main__":
    main()
