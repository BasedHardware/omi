"""Outlook / Exchange mail operations via Microsoft Graph."""
from __future__ import annotations

from typing import Any

from services.graph_client import GraphClient


def _slim_message(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": m.get("id"),
        "subject": m.get("subject"),
        "from": (m.get("from") or {}).get("emailAddress", {}),
        "received": m.get("receivedDateTime"),
        "preview": m.get("bodyPreview"),
        "is_read": m.get("isRead"),
        "has_attachments": m.get("hasAttachments"),
        "web_link": m.get("webLink"),
    }


async def list_recent(user_id: str, limit: int = 10, unread_only: bool = False) -> list[dict[str, Any]]:
    async with GraphClient(user_id) as g:
        params: dict[str, Any] = {
            "$top": limit,
            "$orderby": "receivedDateTime desc",
            "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead,hasAttachments,webLink",
        }
        if unread_only:
            params["$filter"] = "isRead eq false"
        data = await g.get("/me/messages", params=params)
        return [_slim_message(m) for m in data.get("value", [])]


async def search(user_id: str, query: str, limit: int = 10) -> list[dict[str, Any]]:
    async with GraphClient(user_id) as g:
        data = await g.get(
            "/me/messages",
            params={
                "$search": f'"{query}"',
                "$top": limit,
                "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead,hasAttachments,webLink",
            },
        )
        return [_slim_message(m) for m in data.get("value", [])]


async def read(user_id: str, message_id: str) -> dict[str, Any]:
    async with GraphClient(user_id) as g:
        m = await g.get(f"/me/messages/{message_id}")
        return {
            **_slim_message(m),
            "body": (m.get("body") or {}).get("content"),
            "body_type": (m.get("body") or {}).get("contentType"),
            "to": [r["emailAddress"] for r in m.get("toRecipients", [])],
            "cc": [r["emailAddress"] for r in m.get("ccRecipients", [])],
        }


async def send(
    user_id: str,
    to: list[str],
    subject: str,
    body: str,
    *,
    body_type: str = "Text",
    cc: list[str] | None = None,
) -> dict[str, Any]:
    def addr_list(emails: list[str]) -> list[dict[str, Any]]:
        return [{"emailAddress": {"address": e}} for e in emails]

    payload: dict[str, Any] = {
        "message": {
            "subject": subject,
            "body": {"contentType": body_type, "content": body},
            "toRecipients": addr_list(to),
        },
        "saveToSentItems": True,
    }
    if cc:
        payload["message"]["ccRecipients"] = addr_list(cc)

    async with GraphClient(user_id) as g:
        await g.post("/me/sendMail", json=payload, expect_json=False)
        return {"status": "sent", "to": to, "subject": subject}
