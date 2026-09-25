"""
Convert Omi conversation exports to standard JSON Lines (JSONL) datasets.
Supports multi-turn conversational SFT (OpenAI/Anthropic messages format) and structured transcript extraction.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


DEFAULT_SYSTEM_PROMPT = "You are a helpful personal assistant with detailed knowledge of the user's recorded conversations, meetings, and discussions."


def normalize_conversation(record: Any) -> Optional[Dict[str, Any]]:
    """Validate and normalize a raw conversation object from omi conversation export."""
    if not isinstance(record, dict):
        return None

    conv_id = record.get("id")
    if not conv_id or not isinstance(conv_id, str):
        return None

    # Check for structured metadata block
    structured = record.get("structured")
    if not isinstance(structured, dict):
        structured = {}

    title = structured.get("title") or record.get("title") or "Untitled Conversation"
    title = str(title).strip()

    overview = structured.get("overview") or record.get("overview") or ""
    overview = str(overview).strip()

    category = structured.get("category") or record.get("category") or "general"
    category = str(category).strip()

    started_at = record.get("started_at") or record.get("created_at")
    if started_at is not None and not isinstance(started_at, str):
        started_at = str(started_at)

    source = record.get("source")
    if source is not None and not isinstance(source, str):
        source = str(source)

    # Extract transcript segments if present
    segments: List[Dict[str, Any]] = []
    raw_segments = record.get("transcript_segments") or record.get("segments") or []
    if isinstance(raw_segments, list):
        for seg in raw_segments:
            if isinstance(seg, dict):
                text = str(seg.get("text", "")).strip()
                if not text:
                    continue
                speaker = seg.get("speaker") or seg.get("speaker_id") or "SPEAKER"
                is_user = bool(seg.get("is_user", False))
                segments.append({
                    "speaker": str(speaker),
                    "is_user": is_user,
                    "text": text,
                    "start": seg.get("start"),
                    "end": seg.get("end"),
                })

    # Require either transcript segments, an overview, or non-empty content
    if not segments and not overview:
        return None

    return {
        "id": conv_id,
        "title": title,
        "overview": overview,
        "category": category,
        "started_at": started_at,
        "source": source,
        "segments": segments,
    }


def format_chat_entry(item: Dict[str, Any], system_prompt: str) -> Dict[str, Any]:
    """Convert conversation into standard multi-turn chat messages format."""
    messages: List[Dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    segments = item.get("segments", [])
    if segments:
        # Build turns from transcript segments
        for seg in segments:
            role = "user" if seg["is_user"] else "assistant"
            speaker_prefix = f"[{seg['speaker']}]: " if not seg["is_user"] and seg.get("speaker") else ""
            content = f"{speaker_prefix}{seg['text']}"

            # Merge consecutive turns from the same role if appropriate
            if len(messages) > 1 and messages[-1]["role"] == role:
                messages[-1]["content"] += f"\n{content}"
            else:
                messages.append({"role": role, "content": content})
    else:
        # Fallback to topic inquiry & summary pair when only structured overview exists
        title = item.get("title", "the conversation")
        user_prompt = f"Can you summarize what was discussed in '{title}'?"
        messages.append({"role": "user", "content": user_prompt})
        messages.append({"role": "assistant", "content": item["overview"]})

    # Ensure valid alternating conversation starting with user after system
    final_messages: List[Dict[str, str]] = []
    for msg in messages:
        if not final_messages and msg["role"] == "system":
            final_messages.append(msg)
        elif not final_messages or (len(final_messages) == 1 and final_messages[0]["role"] == "system"):
            if msg["role"] != "user":
                final_messages.append({"role": "user", "content": f"Context for {item['title']}:"})
            final_messages.append(msg)
        else:
            final_messages.append(msg)

    return {
        "id": item["id"],
        "title": item["title"],
        "messages": final_messages,
    }


def format_transcript_entry(item: Dict[str, Any]) -> Dict[str, Any]:
    """Convert conversation into structured transcript document format for RAG/search."""
    transcript_lines = []
    for seg in item.get("segments", []):
        transcript_lines.append(f"{seg['speaker']}: {seg['text']}")
    full_transcript = "\n".join(transcript_lines)

    return {
        "id": item["id"],
        "title": item["title"],
        "category": item["category"],
        "overview": item["overview"],
        "transcript": full_transcript,
        "started_at": item["started_at"],
        "metadata": {
            "source": item["source"],
            "segment_count": len(item.get("segments", [])),
        },
    }


def convert_conversations(
    sources: List[str | Path],
    destination: str | Path,
    output_format: str = "chat",
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    force: bool = False,
) -> Tuple[int, int]:
    """
    Read conversations from JSON source files and stream to output JSONL.
    Returns (total_records_processed, unique_records_written).
    """
    seen_ids: Set[str] = set()
    rows_to_write: List[str] = []
    total_processed = 0

    for src in sources:
        if str(src) == "-":
            raw_text = sys.stdin.read()
            src_desc = "stdin"
        else:
            path = Path(src)
            if not path.is_file():
                raise FileNotFoundError(f"Input file not found: {path}")
            raw_text = path.read_text(encoding="utf-8")
            src_desc = str(path)

        try:
            content = json.loads(raw_text)
        except Exception as err:
            raise ValueError(f"Malformed JSON in {src_desc}: {err}") from err

        # Normalize single-object vs array export
        items = content if isinstance(content, list) else [content]

        for raw_item in items:
            total_processed += 1
            item = normalize_conversation(raw_item)
            if not item:
                continue

            conv_id = item["id"]
            if conv_id in seen_ids:
                continue
            seen_ids.add(conv_id)

            if output_format == "chat":
                entry = format_chat_entry(item, system_prompt)
            else:
                entry = format_transcript_entry(item)

            rows_to_write.append(json.dumps(entry, ensure_ascii=False))

    payload = ("\n".join(rows_to_write) + ("\n" if rows_to_write else "")).encode("utf-8")
    dest_path = Path(destination)

    mode = "wb" if force else "xb"
    try:
        with dest_path.open(mode) as f:
            f.write(payload)
    except FileExistsError:
        raise FileExistsError(f"Refusing to overwrite existing file '{dest_path}'. Use --force to overwrite.") from None
    except OSError:
        dest_path.unlink(missing_ok=True)
        raise

    return total_processed, len(rows_to_write)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert Omi conversation JSON exports to JSON Lines (.jsonl) for LLM fine-tuning or RAG datasets."
    )
    parser.add_argument("inputs", nargs="+", help="One or more JSON files exported from omi conversation list --json, or '-' for stdin")
    parser.add_argument("-o", "--output", required=True, help="Destination .jsonl output file")
    parser.add_argument(
        "--format",
        choices=["chat", "transcript"],
        default="chat",
        help="Target schema: 'chat' (multi-turn conversational SFT messages) or 'transcript' (structured text + metadata)",
    )
    parser.add_argument(
        "--system-prompt",
        default=DEFAULT_SYSTEM_PROMPT,
        help="System instruction for conversational messages",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite output file if it already exists",
    )

    args = parser.parse_args(argv)

    try:
        total, written = convert_conversations(
            sources=args.inputs,
            destination=args.output,
            output_format=args.format,
            system_prompt=args.system_prompt,
            force=args.force,
        )
        print(f"Successfully converted {written} conversations ({total} processed) into '{args.output}'")
        return 0
    except (FileNotFoundError, ValueError, FileExistsError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    except Exception as err:
        print(f"Unexpected error: {err}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
