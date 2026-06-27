"""Async HTTP client for the Telegram Bot API.

Wraps `httpx.AsyncClient` and provides three methods that the plugin uses:
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


async def set_webhook(bot_token: str, url: str, secret_token: str) -> dict:
    """Register the plugin's webhook URL with Telegram.

    Returns the parsed JSON body. Raises httpx.HTTPStatusError on failure.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
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
    async with httpx.AsyncClient(timeout=10.0) as client:
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
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{TELEGRAM_API_BASE}/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as e:
        logger.error("send_message failed for chat_id=%s: %s", chat_id, e)
        return None
