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
    """Return the full Telegram API response envelope: {ok, result, ...}.

    Identified by cubic (P2): the docstring previously claimed this returns
    the bot user object {username, id, ...} but the implementation actually
    returns resp.json() — the full envelope. The caller in main.py already
    works around this by reading me.get("result"). The correct shape to
    document is the envelope; the caller continues to unwrap it.

    Raises httpx.HTTPStatusError on 4xx/5xx and ValueError on malformed JSON
    (the Telegram API contract is JSON-only, but a partial 2xx with no body
    would otherwise slip past raise_for_status and explode later).
    """
    client = _get_client()
    resp = await client.post(f"{TELEGRAM_API_BASE}/bot{bot_token}/getMe")
    resp.raise_for_status()
    try:
        return resp.json()
    except ValueError as e:
        # 2xx with no/garbage body — surface as a generic error rather than
        # letting the caller try to read .get("result") on a non-dict.
        raise httpx.HTTPError(f"getMe returned non-JSON body: {e!s}") from e


async def send_message(bot_token: str, chat_id: int | str, text: str) -> Optional[dict]:
    """Send a text message to the given chat. Returns the API response or None on error.

    Does not raise — Telegram's API is best-effort for our purposes; if a
    reply fails we log and move on rather than crash the webhook handler.

    P2 (cubic, PR #8682): bail early on an empty bot_token. The webhook
    can hit the "invalid setup token" branch for an unknown chat_id and
    tries to reply via _bot_token_for_unknown_chat() — that helper
    returns "" when we have no record, and the previous code passed
    the empty token straight to httpx, producing a request to
    https://api.telegram.org/bot/sendMessage (note the empty bot
    segment) which Telegram answers with a 404 and a loud ERROR log.
    Skip the round trip + log spam when we already know we can't reach
    the user.

    Telegram caps messages at 4096 chars. Longer replies are truncated and a
    trailing ellipsis is added so the user sees their reply ended mid-sentence.
    """
    if not bot_token:
        logger.debug(
            "send_message skipped: empty bot_token for chat_id=%s (chat not bound yet)",
            chat_id,
        )
        return None
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
        try:
            return resp.json()
        except ValueError:
            # Identified by cubic (P2): resp.json() can raise
            # json.JSONDecodeError (a ValueError subclass) on an invalid or
            # empty 2xx response body. Without this catch the exception
            # bypasses both except clauses (HTTPStatusError/HTTPError) and
            # leaks out of a function whose docstring promises "Does not
            # raise." Callers in the webhook handler rely on this contract
            # and do not wrap the call in any outer catch.
            logger.error("send_message returned non-JSON body for chat_id=%s", chat_id)
            return None
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
    except httpx.InvalidURL as e:
        # Cubic review 4614064929 P2: httpx.InvalidURL is NOT a subclass
        # of httpx.HTTPError — it lives at the top of the httpx
        # exception hierarchy. A non-empty but malformed bot_token
        # (e.g., containing whitespace or control characters) would
        # trigger this when interpolated into the request URL. The
        # docstring says this function "Does not raise" — without
        # this catch, an InvalidURL would escape and crash the
        # webhook handler that relies on the contract.
        logger.error(
            "send_message failed for chat_id=%s: invalid URL: %s",
            chat_id,
            type(e).__name__,
        )
        return None
