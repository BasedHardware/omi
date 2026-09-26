import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def sanitize_filename(name):
    """Clean string to be safe for filenames across Linux, macOS, and Windows."""
    clean = re.sub(r'[\\/*?:"<>|]', "", name)
    clean = clean.strip().replace(" ", "_")
    return clean[:80] or "untitled"


def format_transcript_segment(seg):
    text = (seg.get("text") or "").strip()
    if not text:
        return ""
    speaker = seg.get("speaker") or ("User" if seg.get("is_user", True) else "Speaker")
    start = seg.get("start")
    time_prefix = f"`[{start:.1f}s]` " if isinstance(start, (int, float)) else ""
    return f"{time_prefix}**{speaker}**: {text}\n"


def convert(source, output_dir):
    content = Path(source).read_bytes().decode("utf-8-sig")
    items = json.loads(content)
    if isinstance(items, dict):
        items = items.get("conversations") or items.get("items") or items.get("data") or [items]
    if not isinstance(items, list):
        raise ValueError("Expected a JSON array of conversations")

    dest_dir = Path(output_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        conv_id = item.get("id") or f"conv_{count}"
        structured = item.get("structured") or {}
        title = structured.get("title") or "Untitled Conversation"
        category = structured.get("category") or "general"
        started_at = item.get("started_at") or ""
        finished_at = item.get("finished_at") or ""
        
        duration_min = None
        if started_at and finished_at:
            try:
                t1 = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                t2 = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
                duration_min = round((t2 - t1).total_seconds() / 60, 1)
            except ValueError:
                pass

        frontmatter = [
            "---",
            f"id: \"{conv_id}\"",
            f"title: \"{title}\"",
            f"category: \"{category}\"",
            f"started_at: \"{started_at}\"",
            f"finished_at: \"{finished_at}\"",
            f"duration_minutes: {duration_min if duration_min is not None else 'null'}",
            f"tags:",
            f"  - omi",
            f"  - conversation",
            f"  - {category.lower().replace(' ', '-')}",
            "---\n"
        ]

        body = [f"# {title}\n"]
        overview = structured.get("overview")
        if overview:
            body.append(f"## Overview\n\n{overview}\n")

        action_items = structured.get("action_items") or []
        if action_items:
            body.append("## Action Items\n")
            for act in action_items:
                act_desc = act.get("description") if isinstance(act, dict) else str(act)
                body.append(f"- [ ] {act_desc}")
            body.append("\n")

        segments = item.get("transcript_segments") or []
        if segments:
            body.append("## Transcript\n")
            for seg in segments:
                if isinstance(seg, dict):
                    formatted = format_transcript_segment(seg)
                    if formatted:
                        body.append(formatted)
            body.append("\n")

        note_content = "\n".join(frontmatter) + "\n" + "\n".join(body)
        filename = f"{started_at[:10]}_{sanitize_filename(title)}_{conv_id[:6]}.md" if started_at else f"{sanitize_filename(title)}_{conv_id[:6]}.md"
        note_path = dest_dir / filename
        note_path.write_text(note_content, encoding="utf-8")
        count += 1

    sys.stderr.write(f"Successfully generated {count} Obsidian notes in {output_dir}\n")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python conversations_to_obsidian.py INPUT.json OUTPUT_DIRECTORY")
    try:
        convert(sys.argv[1], sys.argv[2])
    except (OSError, ValueError) as exc:
        sys.exit(f"Export failed: {exc}")
