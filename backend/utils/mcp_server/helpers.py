"""Parsing and projection helpers shared by hosted MCP tool handlers."""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from utils.conversations.render import redact_conversation_for_list
from utils.mcp_data import parse_date_only_utc
from utils.mcp_server.errors import ToolExecutionError


def parse_mcp_date(value: Optional[str], field: str) -> Optional[datetime]:
    """Parse a yyyy-mm-dd MCP argument into a UTC-anchored datetime, or None when absent.

    Data stores (Firestore conversation ``created_at``/action-item ``due_at``, the vector
    index, screen-activity timestamps) all operate in UTC. A naive parse would be
    interpreted in the server's local timezone and shift the filter window by the UTC
    offset, so anchor to UTC midnight (matching the integration-router convention).
    """
    if not value:
        return None
    try:
        return parse_date_only_utc(value)
    except ValueError:
        raise ToolExecutionError(f"Invalid {field} format: '{value}'. Expected YYYY-MM-DD.", code=-32602)


_parse_mcp_date = parse_mcp_date


def conversation_participants(conversation: Dict[str, Any]) -> Dict[str, Any]:
    """Expose stored speaker mappings, without guessing names from prose."""
    segments = conversation.get("transcript_segments")
    if conversation.get("is_locked") or not isinstance(segments, list):
        return {"participants_included": False}
    participants = []
    seen = set()
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        speaker_id = segment.get("speaker_id")
        person_id = segment.get("person_id")
        speaker_id = speaker_id if isinstance(speaker_id, (str, int)) and not isinstance(speaker_id, bool) else None
        person_id = person_id if isinstance(person_id, str) and person_id else None
        key = (speaker_id, person_id, segment.get("is_user") is True)
        if key == (None, None, False):
            continue
        if key in seen:
            continue
        seen.add(key)
        participants.append({"speaker_id": key[0], "person_id": key[1], "is_user": key[2]})
    return {
        "participants_included": True,
        "participants": participants,
        "person_ids": sorted(
            {p["person_id"] for p in participants if isinstance(p["person_id"], str) and p["person_id"]}
        ),
    }


def conversation_card(conversation: Dict[str, Any]) -> Dict[str, Any]:
    redact_conversation_for_list(conversation)
    structured_raw = conversation.get("structured")
    structured = structured_raw if isinstance(structured_raw, dict) else {}
    return {
        **conversation_participants(conversation),
        "id": conversation.get("id"),
        "created_at": conversation.get("created_at"),
        "started_at": conversation.get("started_at"),
        "finished_at": conversation.get("finished_at"),
        "language": conversation.get("language"),
        "structured": {
            key: structured.get(key) for key in ("title", "overview", "category", "emoji") if key in structured
        },
    }


_conversation_card = conversation_card


def bounded_transcript_segments(
    segments: Any,
    *,
    max_segments: int,
    max_chars: int,
    extra_keys: Tuple[str, ...] = (),
) -> Tuple[List[Dict[str, Any]], bool]:
    source = [segment for segment in segments if isinstance(segment, dict)] if isinstance(segments, list) else []
    bounded: List[Dict[str, Any]] = []
    used_chars = 0
    truncated = False
    allowed_keys = ("id", "text", "original_text", "speaker_id", "is_user", "person_id", "start", "end") + tuple(
        extra_keys
    )

    for index, segment in enumerate(source):
        if index >= max_segments or used_chars >= max_chars:
            truncated = True
            break
        text = str(segment.get("text") or "")
        remaining_chars = max_chars - used_chars
        if len(text) > remaining_chars:
            if remaining_chars > 3:
                text = text[: remaining_chars - 3].rstrip() + "..."
            else:
                text = text[:remaining_chars]
            truncated = True
        item = {key: segment.get(key) for key in allowed_keys if key in segment}
        if item.get('original_text') is not None:
            item['original_text'] = str(item['original_text'])[:remaining_chars]
        item["text"] = text
        bounded.append(item)
        used_chars += len(text)
        if truncated:
            break

    if len(bounded) < len(source):
        truncated = True
    return bounded, truncated


_bounded_transcript_segments = bounded_transcript_segments
