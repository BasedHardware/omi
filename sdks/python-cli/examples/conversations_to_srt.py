#!/usr/bin/env python3
"""Convert Omi conversation transcripts into SubRip (.srt) subtitle files.

Usage:
    python conversations_to_srt.py conversation.json -o transcript.srt
    omi --json conversation get <id> | python conversations_to_srt.py - -o video.srt
    python conversations_to_srt.py conversations.json --output-dir ./subtitles/

Outputs standard SubRip (.srt) subtitles compatible with Adobe Premiere, DaVinci Resolve,
Final Cut Pro, VLC, and all major video editing software.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def format_srt_timestamp(seconds: float) -> str:
    """Format seconds into SubRip timestamp string 'HH:MM:SS,mmm'."""
    if seconds < 0:
        seconds = 0.0
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        secs += 1
        millis -= 1000
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def parse_seconds(value: Any, default: float = 0.0) -> float:
    """Safely convert various timestamp formats into float seconds."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    val_str = str(value).strip()
    if not val_str:
        return default
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


def render_srt(conversation: Dict[str, Any]) -> str:
    """Render a single conversation into an SRT formatted string."""
    segments = conversation.get("transcript_segments") or []
    cues: List[str] = []

    if isinstance(segments, list) and segments:
        cue_idx = 1
        for seg in segments:
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
            time_line = f"{format_srt_timestamp(start_sec)} --> {format_srt_timestamp(end_sec)}"

            cue_text = f"[{speaker}] {text}" if speaker else text
            cues.append(f"{cue_idx}\n{time_line}\n{cue_text}\n")
            cue_idx += 1
    else:
        transcript = str(conversation.get("transcript") or "").strip()
        if transcript:
            cues.append(f"1\n00:00:00,000 --> 00:00:30,000\n{transcript}\n")

    return "\n".join(cues)


def convert_conversations_to_srt(
    sources: Sequence[str | Path],
    output_dest: Optional[str | Path] = None,
    output_dir: Optional[str | Path] = None,
) -> int:
    """Convert conversations to SubRip (.srt) format."""
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
            srt_content = render_srt(conv)
            file_path = out_dir_path / f"{safe_cid}.srt"
            file_path.write_text(srt_content, encoding="utf-8")
            count += 1
        return count

    combined_srt = "\n\n".join(render_srt(c) for c in all_conversations)
    if output_dest and str(output_dest) != "-":
        out_path = Path(output_dest)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(combined_srt, encoding="utf-8")
    else:
        sys.stdout.write(combined_srt + "\n")

    return len(all_conversations)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi conversation transcripts into SubRip (.srt) subtitle files."
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
        help="Destination SubRip (.srt) file (defaults to stdout)",
    )
    parser.add_argument(
        "--output-dir",
        "-d",
        default=None,
        help="Directory to save individual .srt files per conversation",
    )
    args = parser.parse_args()

    try:
        count = convert_conversations_to_srt(args.inputs, args.output, args.output_dir)
        if args.output != "-" or args.output_dir:
            dest = args.output_dir if args.output_dir else args.output
            print(f"Exported {count} conversation(s) to SRT at {dest}", file=sys.stderr)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
