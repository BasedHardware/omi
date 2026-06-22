"""Shared response shaping for the MCP data surface.

These helpers normalize Firestore documents into the lean shapes returned by
both the REST endpoints (``routers/mcp.py``) and the MCP tools
(``routers/mcp_sse.py``). They live in ``utils`` so both routers reuse the
exact same shapes without cross-importing each other (routers must never
import from other routers).
"""

from typing import List


def clean_action_item(item: dict) -> dict:
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


def clean_chat_message(message: dict) -> dict:
    """Shape a chat message doc (drops file/conversation join noise)."""
    return {
        "id": message.get("id", ""),
        "text": message.get("text", "") or "",
        "sender": message.get("sender", ""),
        "type": message.get("type"),
        "created_at": message.get("created_at"),
    }


def clean_person(person: dict) -> dict:
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


def clean_screen_activity_row(row: dict) -> dict:
    """Shape a screen_activity doc into snake_case fields."""
    return {
        "id": row.get("id"),
        "timestamp": row.get("timestamp"),
        "app_name": row.get("appName"),
        "window_title": row.get("windowTitle"),
        "ocr_text": row.get("ocrText"),
    }
