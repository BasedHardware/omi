"""Async HTTP client for the Telegram Bot API.

Wraps a module-level `httpx.AsyncClient` so the underlying TCP/TLS connection
is reused across calls (avoids repeated handshake per Telegram API request).

Three methods:
- set_webhook(bot_token, url, secret_token): register the webhook with Telegram
- get_me(bot_token): fetch the bot's username (needed to build the deep link)
- send_message(bot_token, chat_id, text): post a reply back to a chat
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger("telegram_client")

TELEGRAM_API_BASE = "https://api.telegram.org"

# Shared client with connection pooling. timeout applies per call (overridable
# via httpx.Timeout if needed). Created lazily so tests can patch httpx.AsyncClient
# before the client is constructed; tests use their own client via patch.
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


async def set_webhook(bot_token: str, url: str, secret_token: str) -> dict:
    """Register the plugin's webhook URL with Telegram.

    Returns the parsed JSON body. Raises httpx.HTTPStatusError on failure.
    """
    client = _get_client()
    resp = await client.post(
        f"{TELEGRAM_API_BASE}/bot{bot_token}/setWebhook",
        json={"url": url, "secret_token": secret_token},
    )
    resp.raise_for_status()
    return resp.json()


async def get_me(bot_token: str) -> dict:
    """Return the bot's user object: {username, id, ...}.

    Raises httpx.HTTPStatusError on failure (bad token, etc.).
    """
    client = _get_client()
    resp = await client.post(f"{TELEGRAM_API_BASE}/bot{bot_token}/getMe")
    resp.raise_for_status()
    return resp.json()


async def send_message(bot_token: str, chat_id: int | str, text: str) -> Optional[dict]:
    """Send a text message to the given chat. Returns the API response or None on error.

    Does not raise — Telegram's API is best-effort for our purposes; if a
    reply fails we log and move on rather than crash the webhook handler.

    Telegram caps messages at 4096 chars. Longer replies are truncated and a
    trailing ellipsis is added so the user sees their reply ended mid-sentence.
    """
    # Telegram Bot API hard limit on text length.
    MAX_LEN = 4096
    if text and len(text) > MAX_LEN:
        original_len = len(text)
        text = text[: MAX_LEN - 1].rstrip() + "\u2026"
        logger.warning(
            "send_message: truncated reply for chat_id=%s (%d -> %d chars)",
            chat_id,
            original_len,
            len(text),
        )

    try:
        client = _get_client()
        resp = await client.post(
            f"{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        # httpx.HTTPStatusError.__str__ includes the full request URL — which
        # contains the bot token. Log only the status code + chat_id to keep
        # the token out of logs.
        logger.error(
            "send_message failed for chat_id=%s: HTTP %s",
            chat_id,
            e.response.status_code,
        )
        return None
    except httpx.HTTPError as e:
        # Other HTTP errors (timeout, connect). These don't include the URL
        # in their repr but log a generic message anyway.
        logger.error("send_message failed for chat_id=%s: %s", chat_id, type(e).__name__)
        return None
