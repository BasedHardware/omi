"""
Convert Omi conversation JSON exports to JSONL format for LLM fine-tuning, RAG indexing, and dataset building.

Usage:
  python conversations_to_jsonl.py input.json --output ./conversations.jsonl
  omi --json conversation list --include-transcript | python conversations_to_jsonl.py - -o ./dataset.jsonl --format chat
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

FormatType = Literal["chat", "rag", "raw"]


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


def normalize_utc_date(started_at: Optional[str]) -> str:
    """Normalize ISO date string to UTC format."""
    if not started_at:
        return ""
    try:
        dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return started_at


def build_chat_format(conv: Dict[str, Any], system_prompt: str) -> Optional[Dict[str, Any]]:
    """Convert conversation into OpenAI/Standard Chat fine-tuning format (messages array)."""
    conv_id = conv.get("id", "unknown")
    structured = conv.get("structured") or {}
    if not isinstance(structured, dict):
        structured = {}

    title = structured.get("title") or "Conversation"
    overview = structured.get("overview") or ""
    transcript_segments = conv.get("transcript_segments") or []

    if not transcript_segments:
        return None

    # Construct dialogue text
    messages: List[Dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt.strip()})

    user_lines: List[str] = []
    for seg in transcript_segments:
        if not isinstance(seg, dict):
            continue
        speaker = seg.get("speaker", "Speaker")
        speaker_label = f"Speaker {speaker}" if isinstance(speaker, int) else (str(speaker) if speaker else "Speaker")
        start_time = format_timestamp(seg.get("start"))
        text = (seg.get("text") or "").strip()
        if text:
            user_lines.append(f"[{start_time}] {speaker_label}: {text}")

    if not user_lines:
        return None

    user_content = f"Transcript of '{title}':\n" + "\n".join(user_lines)
    assistant_content = overview.strip() if overview else f"Summary and analysis of {title}."

    messages.append({"role": "user", "content": user_content})
    messages.append({"role": "assistant", "content": assistant_content})

    return {
        "id": conv_id,
        "title": title,
        "messages": messages,
    }


def build_rag_format(conv: Dict[str, Any]) -> Dict[str, Any]:
    """Convert conversation into document text chunk format suitable for RAG & embeddings."""
    conv_id = conv.get("id", "unknown")
    started_at = conv.get("started_at") or ""
    source = conv.get("source") or "omi"

    structured = conv.get("structured") or {}
    if not isinstance(structured, dict):
        structured = {}

    title = structured.get("title") or "Untitled Conversation"
    category = structured.get("category") or "general"
    overview = structured.get("overview") or ""
    action_items = structured.get("action_items") or []
    transcript_segments = conv.get("transcript_segments") or []

    # Build full document text
    text_blocks = [f"Title: {title}", f"Category: {category}", f"Date: {normalize_utc_date(started_at)}"]
    if overview:
        text_blocks.append(f"Summary: {overview.strip()}")
    if action_items:
        actions = []
        for a in action_items:
            if isinstance(a, dict):
                actions.append(a.get("description") or a.get("title") or "")
            elif isinstance(a, str):
                actions.append(a)
        if actions:
            text_blocks.append("Action Items:\n- " + "\n- ".join(actions))

    if transcript_segments:
        transcript_lines = []
        for seg in transcript_segments:
            if not isinstance(seg, dict):
                continue
            speaker = seg.get("speaker", "Speaker")
            speaker_label = f"Speaker {speaker}" if isinstance(speaker, int) else (str(speaker) if speaker else "Speaker")
            t = (seg.get("text") or "").strip()
            if t:
                transcript_lines.append(f"{speaker_label}: {t}")
        if transcript_lines:
            text_blocks.append("Transcript:\n" + "\n".join(transcript_lines))

    full_text = "\n\n".join(text_blocks)

    return {
        "id": conv_id,
        "text": full_text,
        "metadata": {
            "title": title,
            "category": category,
            "source": source,
            "started_at": started_at,
            "segment_count": len(transcript_segments),
        }
    }


def build_raw_format(conv: Dict[str, Any]) -> Dict[str, Any]:
    """Clean single-line raw JSON record preserving all core fields."""
    return conv


def export_to_jsonl(
    items: List[Dict[str, Any]],
    output_path: Path,
    export_format: FormatType = "chat",
    system_prompt: str = "You are an intelligent assistant analyzing conversational meeting transcripts.",
) -> int:
    """Convert a list of conversation dicts to a JSONL file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0

    with open(output_path, "w", encoding="utf-8") as f:
        for conv in items:
            if not isinstance(conv, dict):
                continue

            record = None
            if export_format == "chat":
                record = build_chat_format(conv, system_prompt=system_prompt)
            elif export_format == "rag":
                record = build_rag_format(conv)
            elif export_format == "raw":
                record = build_raw_format(conv)

            if record is not None:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1

    return count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Omi conversation JSON exports to JSONL for LLM fine-tuning and RAG."
    )
    parser.add_argument(
        "input",
        help="Path to JSON file (or '-' for stdin).",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("./conversations.jsonl"),
        help="Output JSONL file path (default: ./conversations.jsonl).",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=["chat", "rag", "raw"],
        default="chat",
        help="JSONL export format: 'chat' (fine-tuning messages), 'rag' (document text + metadata), 'raw' (default: chat).",
    )
    parser.add_argument(
        "--system-prompt",
        default="You are an intelligent assistant analyzing conversational meeting transcripts.",
        help="Optional system prompt when format is 'chat'.",
    )
    args = parser.parse_args()

    if args.input == "-":
        raw_data = sys.stdin.read().lstrip("\ufeff")
    else:
        raw_data = Path(args.input).read_text(encoding="utf-8-sig")

    try:
        data = json.loads(raw_data)
    except json.JSONDecodeError as e:
        sys.exit(f"Error: Invalid JSON input: {e}")

    items: List[Dict[str, Any]]
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = [data]
    else:
        sys.exit("Error: Expected JSON object or array.")

    total_exported = export_to_jsonl(
        items,
        output_path=args.output,
        export_format=args.format,
        system_prompt=args.system_prompt,
    )

    print(f"Successfully exported {total_exported} conversation(s) to JSONL: {args.output}")


if __name__ == "__main__":
    main()
