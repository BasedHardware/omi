"""Shared response shaping for the MCP data surface.

These helpers normalize Firestore documents into the lean shapes returned by
both the REST endpoints (``routers/mcp.py``) and the MCP tools
(``routers/mcp_sse.py``). They live in ``utils`` so both routers reuse the
exact same shapes without cross-importing each other (routers must never
import from other routers).
"""

from datetime import datetime, time
from typing import Any, Dict, List, Optional


def inclusive_end_of_day(dt: Optional[datetime]) -> Optional[datetime]:
    """Extend a date-range end at midnight to the end of that day.

    A date-only ``end_date`` parses to midnight, so a ``start_time <= end_date``
    filter would drop everything later on the requested day. When the value has no
    time component, bump it to 23:59:59.999999 so the day is included; a value with
    an explicit time is left untouched.
    """
    if dt is not None and dt.time() == time(0, 0, 0, 0):
        return dt.replace(hour=23, minute=59, second=59, microsecond=999999)
    return dt


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


def clean_meeting(meeting: dict) -> dict:
    """Shape a calendar-meeting doc for MCP output."""
    participants = meeting.get("participants") or []
    return {
        "id": meeting.get("id", ""),
        "title": meeting.get("title", "") or "",
        "start_time": meeting.get("start_time"),
        "duration_minutes": meeting.get("duration_minutes"),
        "platform": meeting.get("platform"),
        "meeting_link": meeting.get("meeting_link"),
        "participants": [{"name": p.get("name"), "email": p.get("email")} for p in participants if isinstance(p, dict)],
        "notes": meeting.get("notes"),
        "calendar_source": meeting.get("calendar_source"),
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
