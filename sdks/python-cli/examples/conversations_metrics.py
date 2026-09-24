#!/usr/bin/env python3
"""Calculate speaker talk time share, speech rate (WPM), and turn metrics from Omi conversations.

Usage:
    python conversations_metrics.py conversations.json -o metrics.json
    python conversations_metrics.py conversations.json --format markdown -o report.md
    omi --json conversation list | python conversations_metrics.py - --format markdown

Analyzes transcript segments to produce meeting analytics:
- Speaker talk time distribution (seconds and percentage share)
- Word counts and speech rate (Words Per Minute / WPM)
- Speaker turn counts and average utterance duration
Requires only the Python standard library.
"""

from __future__ import annotations

import argparse
import json
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


def analyze_conversation_speakers(conv: Dict[str, Any]) -> Dict[str, Any]:
    """Calculate speaker metrics for a single conversation."""
    cid = str(conv.get("id") or "unknown")
    title = str(
        (conv.get("structured") or {}).get("title")
        or conv.get("title")
        or f"Conversation {cid}"
    )

    segments = conv.get("transcript_segments") or []
    if not isinstance(segments, list) or not segments:
        return {
            "id": cid,
            "title": title,
            "total_duration_sec": 0.0,
            "total_words": 0,
            "speakers": {},
            "total_turns": 0,
        }

    speakers: Dict[str, Dict[str, Any]] = {}
    total_talk_sec = 0.0
    total_words = 0
    turns = 0
    last_speaker = None

    for seg in segments:
        if not isinstance(seg, dict):
            continue
        speaker = str(seg.get("speaker") or seg.get("speaker_id") or "Speaker ?")
        text = str(seg.get("text") or "").strip()
        words = len(text.split()) if text else 0

        # Duration
        start = float(seg.get("start") or 0.0)
        end = float(seg.get("end") or start)
        dur = max(0.0, end - start)

        if speaker not in speakers:
            speakers[speaker] = {
                "total_sec": 0.0,
                "words": 0,
                "turns": 0,
            }

        speakers[speaker]["total_sec"] += dur
        speakers[speaker]["words"] += words
        total_talk_sec += dur
        total_words += words

        if speaker != last_speaker:
            speakers[speaker]["turns"] += 1
            turns += 1
            last_speaker = speaker

    # Calculate percentages and speech rate (WPM)
    formatted_speakers: Dict[str, Dict[str, Any]] = {}
    for spk, stats in speakers.items():
        dur_min = stats["total_sec"] / 60.0 if stats["total_sec"] > 0 else 0.0
        wpm = round(stats["words"] / dur_min, 1) if dur_min > 0 else 0.0
        share_pct = round((stats["total_sec"] / total_talk_sec * 100.0), 1) if total_talk_sec > 0 else 0.0

        formatted_speakers[spk] = {
            "talk_time_sec": round(stats["total_sec"], 2),
            "talk_share_pct": share_pct,
            "words": stats["words"],
            "speech_rate_wpm": wpm,
            "turns": stats["turns"],
        }

    return {
        "id": cid,
        "title": title,
        "total_duration_sec": round(total_talk_sec, 2),
        "total_words": total_words,
        "total_turns": turns,
        "speakers": formatted_speakers,
    }


def to_markdown_report(metrics: List[Dict[str, Any]]) -> str:
    """Render conversation metrics into a clean Markdown table."""
    lines = ["# Omi Conversation Speaker & Speech Metrics", ""]
    for m in metrics:
        lines.append(f"## {m['title']} (`{m['id']}`)")
        lines.append(
            f"**Total Talk Time**: {m['total_duration_sec']}s | **Total Words**: {m['total_words']} | **Turns**: {m['total_turns']}"
        )
        lines.append("")
        lines.append("| Speaker | Talk Time (s) | Share (%) | Words | Speech Rate (WPM) | Turns |")
        lines.append("| :--- | :---: | :---: | :---: | :---: | :---: |")

        for spk, data in m.get("speakers", {}).items():
            lines.append(
                f"| {spk} | {data['talk_time_sec']}s | {data['talk_share_pct']}% | "
                f"{data['words']} | {data['speech_rate_wpm']} | {data['turns']} |"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calculate speaker talk time share, speech rate (WPM), and turn metrics from Omi conversations."
    )
    parser.add_argument("inputs", nargs="*", help="Input JSON files or '-' for stdin")
    parser.add_argument(
        "-o",
        "--output",
        default="-",
        help="Destination file (defaults to stdout)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="Output format (json or markdown)",
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

    results = [analyze_conversation_speakers(c) for c in all_conversations]

    if args.format == "markdown":
        output_text = to_markdown_report(results)
    else:
        output_text = json.dumps(results, indent=2, ensure_ascii=False)

    if args.output != "-":
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_text, encoding="utf-8")
        print(f"Wrote metrics for {len(results)} conversation(s) to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(output_text + "\n")


if __name__ == "__main__":
    main()
