"""
Convert Omi conversation JSON exports to clean Markdown notes for Obsidian, Notion, or personal archives.

Usage:
  python conversations_to_markdown.py input.json --output-dir ./notes/
  omi --json conversation list --include-transcript | python conversations_to_markdown.py - --output-dir ./vault/
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Union


def format_timestamp(seconds: float | int | None) -> str:
    """Format seconds into MM:SS or HH:MM:SS format."""
    if seconds is None:
        return "00:00"
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def slugify(text: str) -> str:
    """Create a filesystem-safe filename slug."""
    text = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[-\s]+", "_", text)[:50] or "conversation"


def conversation_to_markdown(conv: Dict[str, Any]) -> str:
    """Convert a single Omi conversation dictionary into formatted Markdown."""
    conv_id = conv.get("id", "unknown")
    started_at = conv.get("started_at") or ""
    source = conv.get("source") or "omi"

    # Extract structured summary if available
    structured = conv.get("structured") or {}
    if not isinstance(structured, dict):
        structured = {}

    title = structured.get("title") or "Untitled Conversation"
    category = structured.get("category") or "general"
    overview = structured.get("overview") or ""
    action_items = structured.get("action_items") or []

    # Transcript segments
    transcript_segments = conv.get("transcript_segments") or []

    # Clean date representation normalized to UTC
    date_str = ""
    if started_at:
        try:
            dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            date_str = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except Exception:
            date_str = started_at

    category_tag = category.lower().replace(" ", "-")

    # Serialize YAML frontmatter scalars safely using json.dumps to prevent injection and Python 3.10/3.11 SyntaxError
    lines: List[str] = [
        "---",
        f"id: {json.dumps(str(conv_id))}",
        f"title: {json.dumps(str(title))}",
        f"category: {json.dumps(str(category))}",
        f"date: {json.dumps(str(started_at))}",
        f"source: {json.dumps(str(source))}",
        "tags:",
        "  - omi",
        "  - conversation",
        f"  - {json.dumps(category_tag)}",
        "---",
        "",
        f"# {title}",
        "",
        f"**Date:** {date_str or 'N/A'} | **Category:** `{category}` | **Source:** `{source}`",
        "",
    ]

    # Overview / Summary section
    if overview:
        lines.extend([
            "## Summary",
            "",
            overview.strip(),
            "",
        ])

    # Action items checklist
    if action_items:
        lines.extend([
            "## Action Items",
            "",
        ])
        for item in action_items:
            if isinstance(item, dict):
                desc = item.get("description") or item.get("title") or ""
                completed = item.get("completed", False)
                box = "[x]" if completed else "[ ]"
                lines.append(f"- {box} {desc.strip()}")
            elif isinstance(item, str):
                lines.append(f"- [ ] {item.strip()}")
        lines.append("")

    # Transcript section
    if transcript_segments:
        lines.extend([
            "## Transcript",
            "",
        ])
        for seg in transcript_segments:
            if not isinstance(seg, dict):
                continue
            speaker = seg.get("speaker", "Speaker")
            if isinstance(speaker, int):
                speaker_label = f"Speaker {speaker}"
            else:
                speaker_label = str(speaker) if speaker else "Speaker"

            start_time = format_timestamp(seg.get("start"))
            text = (seg.get("text") or "").strip()
            if text:
                lines.append(f"> **[{start_time}] {speaker_label}:** {text}")
                lines.append(">")
        if lines[-1] == ">":
            lines.pop()
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def export_conversations(
    items: List[Dict[str, Any]],
    output_dir: Path,
    overwrite: bool = False,
) -> List[Path]:
    """Convert a list of conversation dicts to Markdown files in output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    exported_paths: List[Path] = []
    used_paths: set[Path] = set()

    for count, conv in enumerate(items):
        if not isinstance(conv, dict):
            continue
        conv_id = conv.get("id", f"conv_{count}")
        started_at = conv.get("started_at") or ""

        # Validate date_prefix strictly against YYYY-MM-DD to avoid path traversal
        date_match = re.match(r"^(\d{4}-\d{2}-\d{2})", str(started_at))
        date_prefix = date_match.group(1) if date_match else "undated"

        structured = conv.get("structured") or {}
        title = structured.get("title") if isinstance(structured, dict) else ""
        slug = slugify(title or "conversation")

        # Sanitize unique suffix to avoid silent overwrites for duplicate title/date pairs
        short_id = re.sub(r"[^\w-]", "", str(conv_id))[:8] or f"{count:03d}"

        base_name = f"{date_prefix}_{slug}_{short_id}"
        filepath = output_dir / f"{base_name}.md"

        if not overwrite:
            counter = 1
            while filepath in used_paths or filepath.exists():
                counter += 1
                filepath = output_dir / f"{base_name}_{counter}.md"

        used_paths.add(filepath)

        md_content = conversation_to_markdown(conv)
        filepath.write_text(md_content, encoding="utf-8")
        print(f"Exported: {filepath}")
        exported_paths.append(filepath)

    return exported_paths


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi conversation JSON exports to Markdown files."
    )
    parser.add_argument(
        "input",
        help="Path to JSON file (or '-' for stdin).",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=Path("./conversations_md"),
        help="Directory to write markdown files (default: ./conversations_md).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        default=False,
        help="Overwrite existing markdown files if filenames collide (default: False).",
    )
    args = parser.parse_args()

    # Read input with UTF-8 BOM protection
    if args.input == "-":
        raw_data = sys.stdin.read().lstrip("\ufeff")
    else:
        raw_data = Path(args.input).read_text(encoding="utf-8-sig")

    data = json.loads(raw_data)
    items: List[Dict[str, Any]]
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = [data]
    else:
        sys.exit("Error: Expected JSON object or array.")

    exported = export_conversations(
        items,
        output_dir=args.output_dir,
        overwrite=args.overwrite,
    )

    print(f"\nSuccessfully exported {len(exported)} conversation(s) to {args.output_dir}/")


if __name__ == "__main__":
    main()

