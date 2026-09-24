#!/usr/bin/env python3
"""Export Omi conversations into an Obsidian notes vault with frontmatter and backlinks.

Usage:
    python conversations_to_obsidian.py conversations.json --output-dir ./OmiVault
    omi --json conversation list | python conversations_to_obsidian.py - -o ./OmiVault

Builds a fully organized Obsidian vault containing:
- Monthly subdirectories (`Conversations/YYYY-MM/`)
- YAML frontmatter metadata (dates, categories, speakers, tags)
- Obsidian callout blocks (`> [!summary]`)
- Master index note (`Conversations_Index.md`) with wiki-links (`[[...]]`)
Requires only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set


def extract_conversations(content: str, source_label: str = "<input>") -> List[Dict[str, Any]]:
    """Parse JSON and extract list of conversation items."""
    raw = content.lstrip("\ufeff")
    items = json.loads(raw)

    if isinstance(items, dict):
        for key in ("conversations", "items", "data"):
            if isinstance(items.get(key), list):
                items = items[key]
                break
        else:
            items = [items]

    if not isinstance(items, list):
        raise ValueError(f"{source_label}: expected a JSON array or wrapped conversations object")

    return items


def slugify(text: str) -> str:
    """Create a URL/filename-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text[:40].strip("-") or "conversation"


def render_obsidian_note(conv: Dict[str, Any]) -> tuple[str, str, Dict[str, Any]]:
    """Render conversation as an Obsidian markdown note with YAML frontmatter."""
    cid = str(conv.get("id") or "unknown")
    st = conv.get("structured") or {}
    title = str(st.get("title") or conv.get("title") or f"Conversation {cid}").strip()
    overview = str(st.get("overview") or conv.get("overview") or "").strip()
    category = str(st.get("category") or conv.get("category") or "general").strip()

    raw_date = str(conv.get("started_at") or conv.get("created_at") or "")
    date_day = raw_date[:10] if len(raw_date) >= 10 else "undated"
    month_folder = date_day[:7] if date_day != "undated" else "undated"

    slug = slugify(title)
    filename = f"{date_day}-{slug}.md" if date_day != "undated" else f"{slug}-{cid[:6]}.md"

    # Extract speakers
    speakers: Set[str] = set()
    segments = conv.get("transcript_segments") or []
    dialogue_lines: List[str] = []

    if isinstance(segments, list) and segments:
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            spk = str(seg.get("speaker") or seg.get("speaker_id") or "Speaker").strip()
            txt = str(seg.get("text") or "").strip()
            if spk:
                speakers.add(spk)
            if txt:
                dialogue_lines.append(f"**{spk}**: {txt}\n")
    elif conv.get("transcript"):
        dialogue_lines.append(str(conv["transcript"]))

    speakers_list = sorted(list(speakers))

    # Build Frontmatter
    fm = [
        "---",
        f'id: "{cid}"',
        f'title: "{title.replace(chr(34), chr(92) + chr(34))}"',
        f"date: {date_day}",
        f"category: {category}",
    ]
    if speakers_list:
        fm.append("speakers:")
        for s in speakers_list:
            fm.append(f'  - "{s}"')
    fm.extend([
        "tags:",
        "  - omi",
        "  - conversation",
        f"  - omi/{category}",
        "---",
        "",
    ])

    body = [f"# {title}", ""]
    if overview:
        body.extend([
            "> [!summary] Overview",
            f"> {overview}",
            "",
        ])

    body.append("## Transcript\n")
    body.extend(dialogue_lines)

    note_content = "\n".join(fm) + "\n".join(body)
    meta = {
        "id": cid,
        "title": title,
        "date": date_day,
        "filename": filename,
        "month_folder": month_folder,
    }
    return filename, note_content, meta


def export_obsidian_vault(conversations: List[Dict[str, Any]], output_dir: Path) -> None:
    """Build and write Obsidian notes vault directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    conv_dir = output_dir / "Conversations"
    conv_dir.mkdir(parents=True, exist_ok=True)

    index_entries: List[Dict[str, Any]] = []

    for conv in conversations:
        fname, content, meta = render_obsidian_note(conv)
        month_dir = conv_dir / meta["month_folder"]
        month_dir.mkdir(parents=True, exist_ok=True)

        note_path = month_dir / fname
        note_path.write_text(content, encoding="utf-8")
        index_entries.append(meta)

    # Generate master index
    index_lines = [
        "# Omi Conversations Index",
        "",
        "Welcome to your Omi conversation vault. Notes are organized chronologically.",
        "",
        "| Date | Title | Note |",
        "| :--- | :--- | :--- |",
    ]
    for e in sorted(index_entries, key=lambda x: x["date"], reverse=True):
        wiki_link = f"[[{e['month_folder']}/{e['filename'].replace('.md', '')}|{e['title']}]]"
        index_lines.append(f"| {e['date']} | {e['title']} | {wiki_link} |")

    index_path = output_dir / "Conversations_Index.md"
    index_path.write_text("\n".join(index_lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export Omi conversations into an Obsidian notes vault with frontmatter and backlinks."
    )
    parser.add_argument("inputs", nargs="*", help="Input JSON files or '-' for stdin")
    parser.add_argument(
        "-o",
        "--output-dir",
        required=True,
        help="Destination directory for the Obsidian vault",
    )
    args = parser.parse_args()

    all_conversations: List[Dict[str, Any]] = []
    for src in args.inputs:
        if str(src) == "-":
            content = sys.stdin.read()
            all_conversations.extend(extract_conversations(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_conversations.extend(extract_conversations(content, str(p)))

    out_dir = Path(args.output_dir)
    export_obsidian_vault(all_conversations, out_dir)
    print(f"Exported {len(all_conversations)} conversation notes into Obsidian vault at {out_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
