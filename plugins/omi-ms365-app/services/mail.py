"""Outlook / Exchange mail operations via Microsoft Graph."""
from __future__ import annotations

import re
from typing import Any

from services.graph_client import GraphClient


def _normalize_email_list(emails: Any) -> list[str]:
    """Normalize a recipient input (single string, comma/semicolon-separated string, or list) into a list of emails."""
    if not emails:
        return []
    if isinstance(emails, str):
        return [p.strip() for p in re.split(r"[,;]", emails) if p.strip()]
    if isinstance(emails, (list, tuple, set)):
        result: list[str] = []
        for item in emails:
            if isinstance(item, str):
                for p in re.split(r"[,;]", item):
                    if p.strip():
                        result.append(p.strip())
            elif isinstance(item, dict):
                addr = item.get("address")
                if not addr and isinstance(item.get("emailAddress"), dict):
                    addr = item["emailAddress"].get("address")
                if addr and str(addr).strip():
                    result.append(str(addr).strip())
        return result
    return []


def _slim_message(m: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(m, dict):
        return {}
    from_dict = m.get("from") if isinstance(m.get("from"), dict) else {}
    from_addr = from_dict.get("emailAddress") if isinstance(from_dict.get("emailAddress"), dict) else {}
    return {
        "id": m.get("id"),
        "subject": m.get("subject"),
        "from": from_addr,
        "received": m.get("receivedDateTime"),
        "preview": m.get("bodyPreview"),
        "is_read": m.get("isRead"),
        "has_attachments": m.get("hasAttachments"),
        "web_link": m.get("webLink"),
    }


def _extract_recipients(recipients: Any) -> list[dict[str, Any]]:
    if not isinstance(recipients, list):
        return []
    result: list[dict[str, Any]] = []
    for r in recipients:
        if isinstance(r, dict):
            addr = r.get("emailAddress")
            if isinstance(addr, dict):
                result.append(addr)
            elif isinstance(addr, str):
                result.append({"address": addr})
    return result


async def list_recent(user_id: str, limit: int = 10, unread_only: bool = False) -> list[dict[str, Any]]:
    try:
        safe_limit = max(1, min(int(limit), 50))
    except (ValueError, TypeError):
        safe_limit = 10
    async with GraphClient(user_id) as g:
        params: dict[str, Any] = {
            "$top": safe_limit,
            "$orderby": "receivedDateTime desc",
            "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead,hasAttachments,webLink",
        }
        if unread_only:
            params["$filter"] = "isRead eq false"
        data = await g.get("/me/messages", params=params)
        raw_items = (data.get("value") or []) if isinstance(data, dict) else []
        return [_slim_message(m) for m in raw_items if isinstance(m, dict)]


async def search(user_id: str, query: str, limit: int = 10) -> list[dict[str, Any]]:
    try:
        safe_limit = max(1, min(int(limit), 50))
    except (ValueError, TypeError):
        safe_limit = 10
    safe_query = str(query or "").replace('"', "")
    async with GraphClient(user_id) as g:
        data = await g.get(
            "/me/messages",
            params={
                "$search": f'"{safe_query}"',
                "$top": safe_limit,
                "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead,hasAttachments,webLink",
            },
        )
        raw_items = (data.get("value") or []) if isinstance(data, dict) else []
        return [_slim_message(m) for m in raw_items if isinstance(m, dict)]


async def read(user_id: str, message_id: str) -> dict[str, Any]:
    async with GraphClient(user_id) as g:
        m = await g.get(f"/me/messages/{message_id}")
        if not isinstance(m, dict):
            return {}
        body_dict = m.get("body") if isinstance(m.get("body"), dict) else {}
        return {
            **_slim_message(m),
            "body": body_dict.get("content"),
            "body_type": body_dict.get("contentType"),
            "to": _extract_recipients(m.get("toRecipients")),
            "cc": _extract_recipients(m.get("ccRecipients")),
        }


async def send(
    user_id: str,
    to: list[str] | str,
    subject: str,
    body: str,
    *,
    body_type: str = "Text",
    cc: list[str] | str | None = None,
) -> dict[str, Any]:
    norm_to = _normalize_email_list(to)
    norm_cc = _normalize_email_list(cc)

    payload: dict[str, Any] = {
        "message": {
            "subject": subject,
            "body": {"contentType": body_type, "content": body},
            "toRecipients": [{"emailAddress": {"address": e}} for e in norm_to],
        },
        "saveToSentItems": True,
    }
    if norm_cc:
        payload["message"]["ccRecipients"] = [{"emailAddress": {"address": e}} for e in norm_cc]

    async with GraphClient(user_id) as g:
        await g.post("/me/sendMail", json=payload, expect_json=False)
        return {"status": "sent", "to": norm_to, "subject": subject}
