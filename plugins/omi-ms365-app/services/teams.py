"""Microsoft Teams operations: chats, messages, online meetings."""
from __future__ import annotations

from typing import Any

from services.graph_client import GraphClient

_MAX_LIMIT = 1000


def _bound_limit(limit: int, default: int = 15) -> int:
    """Clamp a caller-supplied limit into [1, _MAX_LIMIT]."""
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return default
    if limit < 1:
        return 1
    return min(limit, _MAX_LIMIT)


def _iter_dicts(value: Any) -> list[dict[str, Any]]:
    """Return only the dict items of a Graph collection (``value`` may be null/non-list)."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


async def list_recent_chats(user_id: str, limit: int = 15) -> list[dict[str, Any]]:
    limit = _bound_limit(limit)
    async with GraphClient(user_id) as g:
        data = await g.get("/me/chats", params={"$top": limit, "$orderby": "lastMessagePreview/createdDateTime desc"})
        value = data.get("value") if isinstance(data, dict) else None
        return [
            {
                "id": c.get("id"),
                "topic": c.get("topic"),
                "chat_type": c.get("chatType"),
                "last_updated": c.get("lastUpdatedDateTime"),
                "web_url": c.get("webUrl"),
            }
            for c in _iter_dicts(value)
        ]


async def send_chat_message(user_id: str, chat_id: str, message: str) -> dict[str, Any]:
    payload = {"body": {"contentType": "text", "content": message}}
    async with GraphClient(user_id) as g:
        data = await g.post(f"/chats/{chat_id}/messages", json=payload)
        if not isinstance(data, dict):
            data = {}
        return {"id": data.get("id"), "chat_id": chat_id, "status": "sent"}


async def list_my_teams(user_id: str) -> list[dict[str, Any]]:
    async with GraphClient(user_id) as g:
        data = await g.get("/me/joinedTeams")
        value = data.get("value") if isinstance(data, dict) else None
        return [
            {
                "id": t.get("id"),
                "name": t.get("displayName"),
                "description": t.get("description"),
            }
            for t in _iter_dicts(value)
        ]


async def create_online_meeting(
    user_id: str,
    subject: str,
    start_iso: str,
    end_iso: str,
) -> dict[str, Any]:
    payload = {
        "subject": subject,
        "startDateTime": start_iso,
        "endDateTime": end_iso,
    }
    async with GraphClient(user_id) as g:
        data = await g.post("/me/onlineMeetings", json=payload)
        if not isinstance(data, dict):
            data = {}
        return {
            "id": data.get("id"),
            "subject": data.get("subject"),
            "join_url": data.get("joinWebUrl"),
            "start": data.get("startDateTime"),
            "end": data.get("endDateTime"),
        }
