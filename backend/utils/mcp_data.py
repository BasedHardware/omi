"""Shared response shaping for the MCP data surface.

These helpers normalize Firestore documents into the lean shapes returned by
both the REST endpoints (``routers/mcp.py``) and the MCP tools
(``routers/mcp_sse.py``). They live in ``utils`` so both routers reuse the
exact same shapes without cross-importing each other (routers must never
import from other routers).
"""

from typing import Any, Dict, List

from datetime import datetime, timezone


def parse_date_only_utc(value: str) -> datetime:
    """Parse a YYYY-MM-DD string into a UTC-anchored datetime (start-of-day).

    Conversation vectors are stored with a UTC epoch ``created_at`` and Firestore
    conversation/action-item timestamps are timezone-aware UTC, so a date-only
    filter must be anchored to UTC — a naive ``datetime.strptime(...)`` would be
    interpreted in the server's local timezone and shift the window by the UTC
    offset. Callers apply the end-of-day increment (``end_of_day_utc``) when the
    bound must include the full end day.
    """
    parsed = datetime.strptime(value, '%Y-%m-%d')
    return parsed.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)


def end_of_day_utc(dt: datetime) -> datetime:
    """Return the inclusive end of the day for a UTC-anchored boundary.

    Matches the integration-router convention: an end date covers the full day
    through 23:59:59.999999 UTC, not just up to its midnight.
    """
    return dt.replace(hour=23, minute=59, second=59, microsecond=999999)


def date_only_to_utc_epoch(value: str, *, end_of_day: bool = False) -> float:
    """Parse a YYYY-MM-DD string into a UTC epoch seconds boundary.

    Returns the UTC start-of-day (or inclusive end-of-day when ``end_of_day`` is
    true) as epoch seconds, for comparison against the vector index's UTC epoch
    ``created_at``.
    """
    parsed = parse_date_only_utc(value)
    if end_of_day:
        parsed = end_of_day_utc(parsed)
    return parsed.timestamp()


def clean_action_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Shape an action_item doc for MCP output (locked descriptions truncated)."""
    description = item.get("description", "") or ""
    if item.get("is_locked", False) and len(description) > 70:
        description = description[:70] + "..."
    return {
        "id": item.get("id", ""),
        "description": description,
        "completed": bool(item.get("completed", False)),
        "created_at": item.get("created_at"),
        "due_at": item.get("due_at"),
        "completed_at": item.get("completed_at"),
        "conversation_id": item.get("conversation_id"),
    }


def clean_chat_message(message: Dict[str, Any]) -> Dict[str, Any]:
    """Shape a chat message doc (drops file/conversation join noise)."""
    return {
        "id": message.get("id", ""),
        "text": message.get("text", "") or "",
        "sender": message.get("sender", ""),
        "type": message.get("type"),
        "created_at": message.get("created_at"),
    }


def clean_person(person: Dict[str, Any]) -> Dict[str, Any]:
    """Shape a person/contact doc.

    Drops raw speech-sample audio URLs and speaker embeddings (not useful to an
    AI and high-sensitivity); keeps a capped sample of transcripts so the model
    can recognize how the person speaks.
    """
    transcripts: List[str] = person.get("speech_sample_transcripts") or []
    return {
        "id": person.get("id", ""),
        "name": person.get("name", ""),
        "created_at": person.get("created_at"),
        "speech_sample_transcripts": transcripts[:5],
    }


def clean_screen_activity_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Shape a screen_activity doc into snake_case fields."""
    return {
        "id": row.get("id"),
        "timestamp": row.get("timestamp"),
        "app_name": row.get("appName"),
        "window_title": row.get("windowTitle"),
        "ocr_text": row.get("ocrText"),
    }
