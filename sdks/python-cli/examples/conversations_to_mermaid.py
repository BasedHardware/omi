#!/usr/bin/env python3
"""Convert Omi conversations into Mermaid diagram markdown (timeline & sequence diagrams).

Usage:
    # Generate timeline diagram across conversation history
    python conversations_to_mermaid.py conversations.json -o timeline.md
    omi --json conversation list | python conversations_to_mermaid.py - --type timeline -o timeline.md

    # Generate sequence diagram of speaker dialogue for a conversation
    python conversations_to_mermaid.py conversations.json --type sequence -o sequence.md

Outputs native Mermaid code blocks ready to paste directly into GitHub issues/PRs,
Obsidian vaults, and Notion pages.
Requires only the Python standard library.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List


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


def clean_mermaid_text(text: str) -> str:
    """Sanitize text to avoid breaking Mermaid syntax."""
    if not text:
        return ""
    text = re.sub(r'[\r\n]+', ' ', text)
    text = text.replace('"', "'").replace(":", " - ")
    return text.strip()


def generate_timeline(conversations: List[Dict[str, Any]], title: str = "Conversation Timeline") -> str:
    """Generate Mermaid timeline grouping conversations by date."""
    date_groups: Dict[str, List[str]] = defaultdict(list)

    for conv in conversations:
        raw_date = str(conv.get("started_at") or conv.get("created_at") or "Undated")
        day = raw_date[:10] if len(raw_date) >= 10 else "Undated"

        st = conv.get("structured") or {}
        ctitle = str(st.get("title") or conv.get("title") or "Conversation").strip()
        cleaned = clean_mermaid_text(ctitle)
        if cleaned:
            date_groups[day].append(cleaned)

    lines = [
        "```mermaid",
        "timeline",
        f"    title {clean_mermaid_text(title)}",
    ]

    for day in sorted(date_groups.keys()):
        titles = date_groups[day]
        items_str = " : ".join(titles[:5])  # cap at 5 per day for readable timeline
        lines.append(f"    {day} : {items_str}")

    lines.append("```")
    return "\n".join(lines) + "\n"


def generate_sequence(conv: Dict[str, Any]) -> str:
    """Generate Mermaid sequence diagram from dialogue turns between speakers."""
    segments = conv.get("transcript_segments") or []
    st = conv.get("structured") or {}
    title = str(st.get("title") or conv.get("title") or "Conversation Dialogue").strip()

    lines = [
        "```mermaid",
        "sequenceDiagram",
        "    autonumber",
        f"    %% Title: {clean_mermaid_text(title)}",
    ]

    speakers_seen: List[str] = []
    dialogue_events: List[tuple[str, str]] = []

    last_speaker = None
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        spk = re.sub(r"\W+", "_", str(seg.get("speaker") or seg.get("speaker_id") or "User")).strip("_")
        if not spk:
            spk = "Speaker"
        if spk not in speakers_seen:
            speakers_seen.append(spk)

        txt = clean_mermaid_text(str(seg.get("text") or ""))
        if txt:
            # Shorten message preview if long
            snippet = (txt[:80] + "...") if len(txt) > 80 else txt
            dialogue_events.append((spk, snippet))

    if len(speakers_seen) < 2:
        speakers_seen.append("Participant")

    for i, (speaker, msg) in enumerate(dialogue_events[:30]):  # cap at 30 exchanges
        # determine receiver
        other_speakers = [s for s in speakers_seen if s != speaker]
        receiver = other_speakers[0] if other_speakers else "Participant"
        lines.append(f"    {speaker}->>{receiver}: {msg}")

    lines.append("```")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi conversations into Mermaid diagram markdown (timeline & sequence diagrams)."
    )
    parser.add_argument("inputs", nargs="*", help="Input JSON files or '-' for stdin")
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Destination markdown file (defaults to stdout)",
    )
    parser.add_argument(
        "--type",
        choices=["timeline", "sequence"],
        default="timeline",
        help="Diagram type: 'timeline' (daily history) or 'sequence' (speaker dialogue)",
    )
    parser.add_argument(
        "--title",
        default="Omi Conversation Timeline",
        help="Title for the timeline diagram",
    )
    args = parser.parse_args()

    if not args.inputs:
        parser.print_help()
        sys.exit(1)

    all_conversations: List[Dict[str, Any]] = []
    for src in args.inputs:
        if str(src) == "-":
            content = sys.stdin.read()
            all_conversations.extend(extract_conversations(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_conversations.extend(extract_conversations(content, str(p)))

    if args.type == "sequence":
        if not all_conversations:
            print("Error: No conversations available to render sequence diagram.", file=sys.stderr)
            sys.exit(1)
        output_text = generate_sequence(all_conversations[0])
    else:
        output_text = generate_timeline(all_conversations, title=args.title)

    if args.output != "-":
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_text, encoding="utf-8")
        print(f"Generated Mermaid {args.type} diagram at {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(output_text)


if __name__ == "__main__":
    main()
