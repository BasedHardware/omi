#!/usr/bin/env python3
"""Convert Omi Desktop local daily recap JSON exports into structured Markdown notes.

Usage:
    # From a saved recap JSON:
    python local_recap_to_markdown.py recap.json -o 2026-09-24.md

    # Piped directly from omi-cli local recap:
    omi --json local recap --days-ago 0 | python local_recap_to_markdown.py - -o today.md

    # Yesterday's recap with custom title and no frontmatter:
    omi --json local recap --days-ago 1 | python local_recap_to_markdown.py - --no-frontmatter -o yesterday.md

Converts local desktop activity recaps into Obsidian-ready Markdown notes with:
    - YAML frontmatter (date, type, highlights_count, apps_count)
    - Executive narrative summary
    - Key highlights & accomplishments
    - Application focus & screen time breakdown
    - Activity chronological timeline

Key features:
    - Pure Python 3.10+ standard library (zero external dependencies).
    - Multi-day support: renders individual reports or merged daily journal entries.
    - Streaming standard input (-) for seamless UNIX CLI piping.
    - Safe overwrite guard (--force required to replace existing files).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def parse_recap_data(data: Any) -> List[Dict[str, Any]]:
    """Parse raw JSON input into a list of daily recap dictionaries."""
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON data: {exc}") from exc
    else:
        parsed = data

    if isinstance(parsed, dict):
        # Could be wrapped in a payload key
        if "recaps" in parsed and isinstance(parsed["recaps"], list):
            items = parsed["recaps"]
        elif "result" in parsed and isinstance(parsed["result"], dict):
            items = [parsed["result"]]
        else:
            items = [parsed]
    elif isinstance(parsed, list):
        items = parsed
    else:
        raise ValueError(f"Unexpected JSON root type: {type(parsed).__name__}")

    recaps: List[Dict[str, Any]] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"Item at index {idx} is not a valid JSON object")
        recaps.append(item)
    return recaps


def render_frontmatter(recap: Dict[str, Any], date_str: str) -> str:
    """Generate YAML frontmatter for Obsidian / static-site generators."""
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    highlights = recap.get("highlights") or []
    apps = recap.get("apps") or recap.get("applications") or []

    lines = [
        "---",
        f"date: \"{date_str}\"",
        "type: \"omi-daily-recap\"",
        f"highlights_count: {len(highlights)}",
        f"apps_count: {len(apps)}",
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
    # Determine date
    date_str = str(recap.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")).strip()
    title = custom_title or f"Daily Recap — {date_str}"

    sections: List[str] = []

    if include_frontmatter:
        sections.append(render_frontmatter(recap, date_str))

    sections.append(f"# {title}\n")

    # 1. Summary
    summary = recap.get("summary") or recap.get("recap") or recap.get("overview")
    if summary:
        sections.append("## Overview\n")
        sections.append(f"{str(summary).strip()}\n")

    # 2. Key Highlights
    highlights = recap.get("highlights") or recap.get("key_points") or []
    if highlights and isinstance(highlights, list):
        sections.append("## Key Highlights\n")
        for h in highlights:
            text = str(h).strip()
            if text:
                sections.append(f"- [x] {text}")
        sections.append("")

    # 3. Application Focus
    apps = recap.get("apps") or recap.get("applications") or []
    if apps and isinstance(apps, list):
        sections.append("## App Usage & Focus\n")
        sections.append("| Application | Duration | Notes |")
        sections.append("| :--- | :--- | :--- |")
        for app in apps:
            if isinstance(app, dict):
                name = str(app.get("name") or app.get("app") or "Unknown").strip()
                dur = app.get("duration") or app.get("duration_minutes") or app.get("time") or "-"
                dur_str = f"{dur}m" if isinstance(dur, (int, float)) else str(dur)
                notes = str(app.get("notes") or app.get("category") or "-").strip()
                sections.append(f"| **{name}** | {dur_str} | {notes} |")
            elif isinstance(app, str) and app.strip():
                sections.append(f"| **{app.strip()}** | - | - |")
        sections.append("")

    # 4. Timeline
    timeline = recap.get("timeline") or recap.get("activities") or []
    if timeline and isinstance(timeline, list):
        sections.append("## Activity Timeline\n")
        for item in timeline:
            if isinstance(item, dict):
                time_val = str(item.get("time") or item.get("timestamp") or "").strip()
                desc = str(item.get("description") or item.get("activity") or item.get("text") or "").strip()
                if time_val and desc:
                    sections.append(f"* **{time_val}**: {desc}")
                elif desc:
                    sections.append(f"* {desc}")
            elif isinstance(item, str) and item.strip():
                sections.append(f"* {item.strip()}")
        sections.append("")

    return "\n".join(sections).rstrip() + "\n"


def convert_recaps_to_markdown(
    recaps: Sequence[Dict[str, Any]],
    include_frontmatter: bool = True,
    custom_title: Optional[str] = None,
) -> str:
    """Convert sequence of recaps into concatenated Markdown document."""
    if not recaps:
        return "# Daily Recap\n\n*(No local activity recap data provided)*\n"

    parts = []
    for r in recaps:
        parts.append(format_single_recap(r, include_frontmatter=include_frontmatter, custom_title=custom_title))
    return "\n\n---\n\n".join(parts)


def load_input_sources(inputs: Sequence[str]) -> List[Dict[str, Any]]:
    """Load recaps from files or stdin."""
    all_recaps: List[Dict[str, Any]] = []
    for src in inputs:
        if src == "-":
            raw = sys.stdin.read()
            if raw.strip():
                all_recaps.extend(parse_recap_data(raw))
        else:
            path = Path(src)
            if not path.is_file():
                raise FileNotFoundError(f"Input file not found: {path}")
            raw = path.read_text(encoding="utf-8")
            if raw.strip():
                all_recaps.extend(parse_recap_data(raw))
    return all_recaps


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Convert Omi Desktop local daily recap JSON exports into structured Markdown notes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        default=["-"],
        help="Input JSON file path(s), or '-' to read from standard input (default: -).",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output destination path for the Markdown note (default: stdout).",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing output file if it already exists.",
    )
    parser.add_argument(
        "--no-frontmatter",
        action="store_true",
        help="Omit YAML frontmatter from generated Markdown note.",
    )
    parser.add_argument(
        "--title",
        type=str,
        default=None,
        help="Custom note title heading (default: Daily Recap — YYYY-MM-DD).",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.output and args.output.exists() and not args.force:
        sys.stderr.write(f"Error: Output file '{args.output}' already exists. Use --force to overwrite.\n")
        return 1

    try:
        recaps = load_input_sources(args.inputs)
    except Exception as exc:
        sys.stderr.write(f"Error reading input: {exc}\n")
        return 1

    markdown_text = convert_recaps_to_markdown(
        recaps=recaps,
        include_frontmatter=not args.no_frontmatter,
        custom_title=args.title,
    )

    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(markdown_text, encoding="utf-8")
        except OSError as exc:
            sys.stderr.write(f"Error writing output file: {exc}\n")
            return 1
    else:
        sys.stdout.write(markdown_text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
