"""Outlook / Exchange mail operations via Microsoft Graph."""
from __future__ import annotations

from typing import Any

from services.graph_client import GraphClient

# Microsoft Graph caps $top at 1000 for message collections; keep a sane floor too.
_MAX_LIMIT = 1000


def _bound_limit(limit: int, default: int = 10) -> int:
    """Clamp a caller-supplied limit into [1, _MAX_LIMIT].

    Guards against unbounded ``$top`` values (0, negative, or absurdly large)
    that Graph would reject or that would fetch far more than intended.
    """
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return default
    if limit < 1:
        return 1
    return min(limit, _MAX_LIMIT)


def _iter_dicts(value: Any) -> list[dict[str, Any]]:
    """Return only the dict items of a Graph collection.

    Graph may return ``{"value": null}`` (``None``), a non-list, or a list that
    contains non-dict entries. This normalises all of those to a list of dicts
    instead of crashing with ``TypeError``/``AttributeError``.
    """
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _extract_recipients(recipients: Any) -> list[dict[str, Any]]:
    """Pull the ``emailAddress`` dict out of a recipients collection safely.

    Handles ``null`` collections, non-list values, non-dict items, and items
    missing (or with a non-dict) ``emailAddress`` field.
    """
    out: list[dict[str, Any]] = []
    for r in _iter_dicts(recipients):
        addr = r.get("emailAddress")
        if isinstance(addr, dict):
            out.append(addr)
    return out


def _slim_message(m: Any) -> dict[str, Any]:
    if not isinstance(m, dict):
        return {}
    frm = m.get("from")
    from_addr = frm.get("emailAddress", {}) if isinstance(frm, dict) else {}
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


async def list_recent(user_id: str, limit: int = 10, unread_only: bool = False) -> list[dict[str, Any]]:
    limit = _bound_limit(limit)
    async with GraphClient(user_id) as g:
        params: dict[str, Any] = {
            "$top": limit,
            "$orderby": "receivedDateTime desc",
            "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead,hasAttachments,webLink",
        }
        if unread_only:
            params["$filter"] = "isRead eq false"
        data = await g.get("/me/messages", params=params)
        value = data.get("value") if isinstance(data, dict) else None
        return [_slim_message(m) for m in _iter_dicts(value)]


async def search(user_id: str, query: str, limit: int = 10) -> list[dict[str, Any]]:
    limit = _bound_limit(limit)
    async with GraphClient(user_id) as g:
        data = await g.get(
            "/me/messages",
            params={
                "$search": f'"{query}"',
                "$top": limit,
                "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead,hasAttachments,webLink",
            },
        )
        value = data.get("value") if isinstance(data, dict) else None
        return [_slim_message(m) for m in _iter_dicts(value)]


async def read(user_id: str, message_id: str) -> dict[str, Any]:
    async with GraphClient(user_id) as g:
        m = await g.get(f"/me/messages/{message_id}")
        if not isinstance(m, dict):
            m = {}
        body = m.get("body")
        body = body if isinstance(body, dict) else {}
        return {
            **_slim_message(m),
            "body": body.get("content"),
            "body_type": body.get("contentType"),
            "to": _extract_recipients(m.get("toRecipients")),
            "cc": _extract_recipients(m.get("ccRecipients")),
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
