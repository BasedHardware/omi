"""Microsoft Teams operations: chats, messages, online meetings."""
from __future__ import annotations

from typing import Any

from services.graph_client import GraphClient


async def list_recent_chats(user_id: str, limit: int = 15) -> list[dict[str, Any]]:
    try:
        safe_limit = max(1, min(int(limit), 50))
    except (ValueError, TypeError):
        safe_limit = 15
    async with GraphClient(user_id) as g:
        data = await g.get("/me/chats", params={"$top": safe_limit, "$orderby": "lastMessagePreview/createdDateTime desc"})
        raw_items = (data.get("value") or []) if isinstance(data, dict) else []
        return [
            {
                "id": c.get("id"),
                "topic": c.get("topic"),
                "chat_type": c.get("chatType"),
                "last_updated": c.get("lastUpdatedDateTime"),
                "web_url": c.get("webUrl"),
            }
            for c in raw_items
            if isinstance(c, dict)
        ]


async def send_chat_message(user_id: str, chat_id: str, message: str) -> dict[str, Any]:
    payload = {"body": {"contentType": "text", "content": message}}
    async with GraphClient(user_id) as g:
        data = await g.post(f"/chats/{chat_id}/messages", json=payload)
        data_dict = data if isinstance(data, dict) else {}
        return {"id": data_dict.get("id"), "chat_id": chat_id, "status": "sent"}


async def list_my_teams(user_id: str) -> list[dict[str, Any]]:
    async with GraphClient(user_id) as g:
        data = await g.get("/me/joinedTeams")
        raw_items = (data.get("value") or []) if isinstance(data, dict) else []
        return [
            {
                "id": t.get("id"),
                "name": t.get("displayName"),
                "description": t.get("description"),
            }
            for t in raw_items
            if isinstance(t, dict)
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
        data_dict = data if isinstance(data, dict) else {}
        return {
            "id": data_dict.get("id"),
            "subject": data_dict.get("subject", subject),
            "join_url": data_dict.get("joinWebUrl"),
            "start": data_dict.get("startDateTime", start_iso),
            "end": data_dict.get("endDateTime", end_iso),
        }
