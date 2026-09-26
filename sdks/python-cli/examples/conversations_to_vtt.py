#!/usr/bin/env python3
"""Convert Omi conversation transcripts into WebVTT (.vtt) subtitle files.

Usage:
    python conversations_to_vtt.py conversation.json -o transcript.vtt
    omi --json conversation get <id> | python conversations_to_vtt.py - -o audio_track.vtt
    python conversations_to_vtt.py conversations.json --output-dir ./subtitles/

Outputs standard WebVTT (W3C Web Video Text Tracks) subtitles with cue timings
and speaker voice tags (<v Speaker>...</v>) compatible with VLC, HTML5 <video>/<audio>,
YouTube, and podcast media players.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def format_vtt_timestamp(seconds: float) -> str:
    """Format seconds into WebVTT timestamp string 'HH:MM:SS.mmm'."""
    if seconds < 0:
        seconds = 0.0
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        secs += 1
        millis -= 1000
    return f"{hrs:02d}:{mins:02d}:{secs:02d}.{millis:03d}"


def parse_seconds(value: Any, default: float = 0.0) -> float:
    """Safely convert various timestamp formats into float seconds."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    val_str = str(value).strip()
    if not val_str:
        return default
    # If format is HH:MM:SS or MM:SS
    parts = val_str.split(":")
    if len(parts) == 3:
        try:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        except ValueError:
            pass
    elif len(parts) == 2:
        try:
            return float(parts[0]) * 60 + float(parts[1])
        except ValueError:
            pass
    try:
        return float(val_str)
    except ValueError:
        return default


def extract_conversations(content: str, source_label: str = "<input>") -> List[Dict[str, Any]]:
    """Parse JSON content and extract a list of conversation dictionaries."""
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

    results: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(f"{source_label}: each conversation must be a JSON object")
        if not item.get("id") or str(item.get("id")).strip() == "":
            raise ValueError(f"{source_label}: conversation missing required 'id' field")
        results.append(item)

    return results


def render_vtt(conversation: Dict[str, Any]) -> str:
    """Render a single conversation into a WebVTT formatted string."""
    cid = str(conversation.get("id"))
    structured = conversation.get("structured") or {}
    title = structured.get("title") or conversation.get("title") or "Conversation"

    lines: List[str] = [
        "WEBVTT",
        f"NOTE Conversation ID: {cid}",
        f"NOTE Title: {title}",
        "",
    ]

    segments = conversation.get("transcript_segments") or []
    if isinstance(segments, list) and segments:
        for idx, seg in enumerate(segments, start=1):
            if not isinstance(seg, dict):
                continue
            text = str(seg.get("text") or "").strip()
            if not text:
                continue

            start_sec = parse_seconds(seg.get("start") if seg.get("start") is not None else seg.get("start_time"), 0.0)
            end_sec = parse_seconds(seg.get("end") if seg.get("end") is not None else seg.get("end_time"), start_sec + 2.0)
            if end_sec <= start_sec:
                end_sec = start_sec + 2.0

            speaker = str(seg.get("speaker") or seg.get("speaker_id") or "").strip()
            time_line = f"{format_vtt_timestamp(start_sec)} --> {format_vtt_timestamp(end_sec)}"
            lines.append(str(idx))
            lines.append(time_line)
            if speaker:
                lines.append(f"<v {speaker}>{text}</v>")
            else:
                lines.append(text)
            lines.append("")
    else:
        # Fallback to monolithic transcript if present
        transcript = str(conversation.get("transcript") or "").strip()
        if transcript:
            lines.append("1")
            lines.append("00:00:00.000 --> 00:00:30.000")
            lines.append(transcript)
            lines.append("")
        else:
            lines.append("NOTE No transcript available for this conversation")
            lines.append("")

    return "\n".join(lines)


def convert_conversations_to_vtt(
    sources: Sequence[str | Path],
    output_dest: Optional[str | Path] = None,
    output_dir: Optional[str | Path] = None,
) -> int:
    """Convert conversations to WebVTT format."""
    all_conversations: List[Dict[str, Any]] = []

    for src in sources:
        if str(src) == "-":
            content = sys.stdin.read()
            all_conversations.extend(extract_conversations(content, "<stdin>"))
        else:
            p = Path(src)
            content = p.read_text(encoding="utf-8")
            all_conversations.extend(extract_conversations(content, str(p)))

    if output_dir:
        out_dir_path = Path(output_dir)
        out_dir_path.mkdir(parents=True, exist_ok=True)
        count = 0
        for conv in all_conversations:
            cid = str(conv.get("id"))
            safe_cid = re.sub(r"[^\w-]", "_", cid)
            vtt_content = render_vtt(conv)
            file_path = out_dir_path / f"{safe_cid}.vtt"
            file_path.write_text(vtt_content, encoding="utf-8")
            count += 1
        return count

    # Combine into single stream / file
    combined_vtt = "\n\n".join(render_vtt(c) for c in all_conversations)
    if output_dest and str(output_dest) != "-":
        out_path = Path(output_dest)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(combined_vtt, encoding="utf-8")
    else:
        sys.stdout.write(combined_vtt + "\n")

    return len(all_conversations)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi conversation transcripts into WebVTT (.vtt) subtitle files."
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
        help="Destination WebVTT file (defaults to stdout)",
    )
    parser.add_argument(
        "--output-dir",
        "-d",
        default=None,
        help="Directory to save individual .vtt files per conversation",
    )
    args = parser.parse_args()

    try:
        count = convert_conversations_to_vtt(args.inputs, args.output, args.output_dir)
        if args.output != "-" or args.output_dir:
            dest = args.output_dir if args.output_dir else args.output
            print(f"Exported {count} conversation(s) to WebVTT at {dest}", file=sys.stderr)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
