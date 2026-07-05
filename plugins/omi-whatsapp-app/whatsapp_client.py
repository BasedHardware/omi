"""Async HTTP client for the Meta WhatsApp Business Cloud API.

Mirrors plugins/omi-telegram-app/telegram_client.py in shape: a shared
httpx.AsyncClient with a module-level `aclose()` for graceful shutdown.

Endpoints used (graph.facebook.com/v22.0):
- POST /{phone_number_id}/messages            send a text message
- POST /{phone_number_id}/subscribed_apps     register webhook subscription
- GET  /{phone_number_id}                     fetch the phone's display number

All endpoints require `Authorization: Bearer {access_token}`. We never put
the access_token in the URL — only in the Authorization header.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger("whatsapp_client")

META_GRAPH_BASE = "https://graph.facebook.com/v22.0"

# Shared client with connection pooling. timeout applies per call.
_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=10.0)
    return _client


async def aclose() -> None:
    """Close the shared client on shutdown (called from FastAPI lifespan)."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _auth_headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


async def send_message(
    phone_number_id: str,
    access_token: str,
    to: str,
    text: str,
) -> Optional[dict]:
    """Send a text message via the Cloud API. Returns parsed JSON or None on error.

    Cloud API caps text at 4096 chars; we truncate with a trailing ellipsis
    if needed (matches Telegram's behavior in plugins/omi-telegram-app/telegram_client.py).
    """
    MAX_LEN = 4096
    if text and len(text) > MAX_LEN:
        original_len = len(text)
        text = text[: MAX_LEN - 1].rstrip() + "…"
        logger.warning(
            "send_message: truncated reply for to=%s (%d -> %d chars)",
            to,
            original_len,
            len(text),
        )

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    try:
        client = _get_client()
        resp = await client.post(
            f"{META_GRAPH_BASE}/{phone_number_id}/messages",
            json=payload,
            headers=_auth_headers(access_token),
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        # httpx.HTTPStatusError.__str__ includes the request URL — but our URL
        # contains the phone_number_id (NOT the access_token; the token is in
        # the Authorization header). Still, log only the status code to keep
        # the logs predictable.
        logger.error(
            "send_message failed for to=%s: HTTP %s",
            to,
            e.response.status_code,
        )
        return None
    except httpx.HTTPError as e:
        logger.error("send_message failed for to=%s: %s", to, type(e).__name__)
        return None


async def subscribe_app(phone_number_id: str, access_token: str) -> dict:
    """Register the app subscription so Meta delivers webhook updates to us.

    The Meta Graph API `subscribed_apps` edge lives on the WhatsApp
    Business Account (WABA), NOT directly on the phone number. Posting
    to /{phone_number_id}/subscribed_apps returns a 400 / "no edge
    found" error from Meta — the correct URL is
    /{waba_id}/subscribed_apps.

    We resolve waba_id from the phone number first via the
    `?fields=whatsapp_business_account{id}` lookup (one extra round
    trip, but keeps the SetupRequest API stable — the user still
    only provides a phone_number_id, not a separate WABA id).

    Returns the parsed JSON response. Raises httpx.HTTPStatusError on
    failure (e.g. if the access_token doesn't have the right scopes
    or the phone number isn't on a WABA the token can manage).
    """
    client = _get_client()

    # Step 1: resolve WABA id from phone number.
    lookup = await client.get(
        f"{META_GRAPH_BASE}/{phone_number_id}",
        params={"fields": "whatsapp_business_account{id}"},
        headers=_auth_headers(access_token),
    )
    lookup.raise_for_status()
    waba = (lookup.json().get("whatsapp_business_account") or {}).get("id")
    if not waba:
        # Meta returns "whatsapp_business_account": {"id": "..."} on success;
        # an empty/missing value means the token can't see the WABA for
        # this phone (wrong scopes or phone not on any WABA the token
        # manages).
        #
        # P2 (cubic follow-up on PR #8528): don't raise HTTPStatusError
        # here — the response was 2xx, so HTTPStatusError would be
        # misleading for downstream error handling and logging. Use the
        # base HTTPError which is what generic transport failures raise;
        # the caller's `except httpx.HTTPError` branch picks it up
        # cleanly and logs the type name ("HTTPError"), not a fake
        # status code.
        raise httpx.HTTPError(
            "phone number is not linked to a WhatsApp Business Account "
            "the access_token can manage"
        )

    # Step 2: subscribe to the WABA's webhook edge.
    resp = await client.post(
        f"{META_GRAPH_BASE}/{waba}/subscribed_apps",
        headers=_auth_headers(access_token),
    )
    resp.raise_for_status()
    return resp.json()


async def get_phone_number_info(phone_number_id: str, access_token: str) -> dict:
    """Fetch the phone number's display info (display_phone_number, verified_name).

    Useful during /setup to verify the access_token + phone_number_id combo
    is valid before subscribing the app. Raises httpx.HTTPStatusError on
    failure.
    """
    client = _get_client()
    resp = await client.get(
        f"{META_GRAPH_BASE}/{phone_number_id}",
        params={"fields": "display_phone_number,verified_name"},
        headers=_auth_headers(access_token),
    )
    resp.raise_for_status()
    return resp.json()
