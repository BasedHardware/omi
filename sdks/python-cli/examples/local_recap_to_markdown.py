#!/usr/bin/env python3
"""Convert Omi local recap JSON output to structured Markdown for Obsidian or notes.

Reads local recap data emitted by `omi --json local recap` (from file or stdin),
extracts summary, app usage, tasks, focus sessions, and conversations from the
real `sections` and `totals` schema, and outputs clean Markdown with optional
YAML frontmatter.

Zero external dependencies - uses Python 3 standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


def parse_recap_data(data: Any) -> List[Dict[str, Any]]:
    """Unwrap daily recap objects from JSON string, dict, or list.

    Supports:
    - Dict emitted by `omi --json local recap` with `sections` and `totals`
    - Dict with a list under 'recaps', 'items', 'data', or 'result'
    - List of recap objects
    """
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON data: {exc}") from exc
    else:
        parsed = data

    if isinstance(parsed, dict):
        if "sections" in parsed or "totals" in parsed or "tool" in parsed:
            # Native 'omi local recap' payload
            return [parsed]
        for key in ("recaps", "items", "data", "result"):
            val = parsed.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]
        return [parsed]
    elif isinstance(parsed, list):
        return [x for x in parsed if isinstance(x, dict)]
    else:
        raise ValueError(f"Unexpected JSON root type: {type(parsed).__name__}")


def extract_sections_map(recap: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Map section names to their item lists from the real Omi recap schema."""
    result: Dict[str, List[Dict[str, Any]]] = {}

    sections_list = recap.get("sections")
    if isinstance(sections_list, list):
        for sec in sections_list:
            if isinstance(sec, dict) and "name" in sec:
                name = str(sec["name"]).strip().lower()
                items = sec.get("items") or []
                if isinstance(items, list):
                    result[name] = [it for it in items if isinstance(it, dict)]

    # Fallback to direct top-level keys if present
    for key in ("apps", "tasks", "focus", "conversations", "memories", "observations", "summary"):
        if key not in result and key in recap and isinstance(recap[key], list):
            result[key] = [it for it in recap[key] if isinstance(it, dict)]

    return result


def render_frontmatter(recap: Dict[str, Any], date_str: str) -> str:
    """Generate YAML frontmatter for Obsidian / static-site daily notes."""
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    totals = recap.get("totals") or {}
    sec_map = extract_sections_map(recap)

    apps_count = totals.get("apps", len(sec_map.get("apps", [])))
    tasks_count = totals.get("tasks", len(sec_map.get("tasks", [])))
    convs_count = totals.get("conversations", len(sec_map.get("conversations", [])))
    focus_count = totals.get("focus", len(sec_map.get("focus", [])))

    lines = [
        "---",
        f"date: \"{date_str}\"",
        "type: \"omi-daily-recap\"",
        f"apps_count: {apps_count}",
        f"tasks_count: {tasks_count}",
        f"conversations_count: {convs_count}",
        f"focus_count: {focus_count}",
        f"generated_at: \"{now_utc}\"",
        "tags:",
        "  - omi/recap",
        "  - journal/daily",
        "---",
        "",
    ]
    return "\n".join(lines)


def format_single_recap(
    recap: Dict[str, Any],
    include_frontmatter: bool = True,
    custom_title: Optional[str] = None,
) -> str:
    """Format a single daily recap object into structured Markdown."""
    date_str = str(recap.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")).strip()
    title = custom_title or f"Daily Recap — {date_str}"

    sec_map = extract_sections_map(recap)
    out_lines: List[str] = []

    if include_frontmatter:
        out_lines.append(render_frontmatter(recap, date_str))

    out_lines.append(f"# {title}\n")

    # 1. Summary / Overview
    summary_items = sec_map.get("summary") or []
    summary_text = ""
    if summary_items:
        first = summary_items[0]
        summary_text = str(first.get("content") or first.get("text") or first.get("summary") or "").strip()
    elif recap.get("summary"):
        summary_text = str(recap["summary"]).strip()

    if summary_text:
        out_lines.append("## Overview\n")
        out_lines.append(f"{summary_text}\n")

    # 2. Tasks
    tasks = sec_map.get("tasks") or []
    if tasks:
        out_lines.append("## Tasks & Action Items\n")
        for t in tasks:
            task_title = str(t.get("title") or t.get("description") or "Untitled task").strip()
            completed = bool(t.get("completed"))
            box = "[x]" if completed else "[ ]"
            priority = str(t.get("priority") or "").strip()
            prio_tag = f" `[{priority.upper()}]`" if priority else ""
            summary_desc = str(t.get("summary") or "").strip()

            line = f"- {box} {task_title}{prio_tag}"
            if summary_desc and summary_desc != task_title:
                line += f" — {summary_desc}"
            out_lines.append(line)
        out_lines.append("")

    # 3. Application Focus
    apps = sec_map.get("apps") or []
    if apps:
        out_lines.append("## App Usage & Focus\n")
        out_lines.append("| Application | Active Time | Captures | First / Last Seen |")
        out_lines.append("| :--- | :--- | :--- | :--- |")
        for a in apps:
            app_title = str(a.get("title") or a.get("name") or a.get("app") or "Unknown").strip()
            mins = a.get("minutes") or a.get("duration") or a.get("duration_minutes")
            if isinstance(mins, (int, float)):
                time_str = f"{mins:.1f}m"
            else:
                time_str = str(mins or "-")
            caps = a.get("captures", "-")
            first = str(a.get("firstSeenAt") or "").strip()
            last = str(a.get("lastSeenAt") or "").strip()
            window = f"{first} - {last}" if first and last else (first or last or "-")
            out_lines.append(f"| **{app_title}** | {time_str} | {caps} | {window} |")
        out_lines.append("")

    # 4. Focus Sessions
    focus_items = sec_map.get("focus") or []
    if focus_items:
        out_lines.append("## Focus Sessions\n")
        for f in focus_items:
            f_title = str(f.get("title") or "Focus Block").strip()
            f_status = str(f.get("status") or "").strip()
            dur_sec = f.get("durationSeconds") or f.get("duration")
            dur_str = f"{dur_sec // 60}m" if isinstance(dur_sec, (int, float)) else str(dur_sec or "")
            extra = f" ({dur_str})" if dur_str else ""
            status_tag = f" — *{f_status}*" if f_status else ""
            out_lines.append(f"- **{f_title}**{extra}{status_tag}")
        out_lines.append("")

    # 5. Conversations & Meetings
    conv_items = sec_map.get("conversations") or []
    if conv_items:
        out_lines.append("## Conversations & Discussions\n")
        for c in conv_items:
            c_title = str(c.get("title") or "Conversation").strip()
            c_sum = str(c.get("summary") or "").strip()
            dur_sec = c.get("durationSeconds") or c.get("duration")
            dur_str = f"{dur_sec // 60}m" if isinstance(dur_sec, (int, float)) else ""
            tag = f" ({dur_str})" if dur_str else ""
            desc = f": {c_sum}" if c_sum else ""
            out_lines.append(f"- **{c_title}**{tag}{desc}")
        out_lines.append("")

    # 6. Memories & Observations
    mems = sec_map.get("memories") or []
    if mems:
        out_lines.append("## Key Insights & Memories\n")
        for m in mems:
            content = str(m.get("content") or m.get("title") or "").strip()
            if content:
                out_lines.append(f"- {content}")
        out_lines.append("")

    return "\n".join(out_lines).strip() + "\n"


def convert_recap_to_markdown(
    inputs: Sequence[str],
    include_frontmatter: bool = True,
    title: Optional[str] = None,
) -> Tuple[str, int]:
    """Convert input files or stdin into a combined Markdown document."""
    all_recaps: List[Dict[str, Any]] = []

    for inp in inputs:
        if inp == "-":
            raw_text = sys.stdin.read()
        else:
            p = Path(inp)
            if not p.is_file():
                raise FileNotFoundError(f"File not found: {inp}")
            raw_text = p.read_bytes().decode("utf-8-sig")

        all_recaps.extend(parse_recap_data(raw_text))

    if not all_recaps:
        return "", 0

    formatted_parts: List[str] = []
    for r in all_recaps:
        formatted_parts.append(
            format_single_recap(r, include_frontmatter=include_frontmatter, custom_title=title)
        )

    return "\n\n---\n\n".join(formatted_parts), len(all_recaps)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi local recap JSON output to structured Markdown for Obsidian or notes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  omi --json local recap --days-ago 0 | python local_recap_to_markdown.py - -o Daily.md
  python local_recap_to_markdown.py recap.json -o ~/Vault/Daily/2026-09-24.md --force
  python local_recap_to_markdown.py recap.json --no-frontmatter
""",
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        metavar="INPUT",
        help="One or more JSON files exported from 'omi local recap', or '-' for stdin.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        metavar="FILE",
        help="Destination Markdown file (default: write to stdout).",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Custom document title (default: 'Daily Recap — YYYY-MM-DD').",
    )
    parser.add_argument(
        "--no-frontmatter",
        action="store_true",
        help="Omit YAML frontmatter metadata block.",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite destination file if it already exists.",
    )

    args = parser.parse_args(argv)

    out_path = Path(args.output) if args.output else None
    if out_path and out_path.exists() and not args.force:
        print(f"Error: Output file '{args.output}' already exists. Use --force to overwrite.", file=sys.stderr)
        return 1

    try:
        markdown, count = convert_recap_to_markdown(
            args.inputs,
            include_frontmatter=not args.no_frontmatter,
            title=args.title,
        )
    except (FileNotFoundError, ValueError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(markdown, encoding="utf-8")
        print(f"Converted {count} daily recap(s) to Markdown: '{args.output}'.")
    else:
        sys.stdout.write(markdown)

    return 0


if __name__ == "__main__":
    sys.exit(main())
