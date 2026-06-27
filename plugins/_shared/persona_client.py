"""Shared HTTP client for AI Clone plugins to call the Omi persona-chat API.

Used by:
- plugins/omi-telegram-app/  (T-003/004)
- plugins/omi-whatsapp-app/  (T-005)
- plugins/omi-imessage-app/  (T-006)

Contract:
    reply = await chat(app_id, api_key, omi_base, text, *, timeout_seconds=30.0)

Returns the concatenated persona reply (single string) on success.
Returns "" on timeout or connection error and logs at ERROR level — callers
(chat platforms) should treat "" as "no reply, do nothing".
Raises httpx.HTTPStatusError on 4xx/5xx responses (caller decides retry policy).
"""

from __future__ import annotations

import logging
from typing import AsyncIterator, Iterable, Optional

import httpx
from httpx_sse import EventSource

logger = logging.getLogger("persona_client")

DEFAULT_TIMEOUT_SECONDS = 30.0


async def chat(
    app_id: str,
    api_key: str,
    omi_base: str,
    text: str,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    context: Optional[dict] = None,
) -> str:
    """POST /v2/integrations/{app_id}/user/persona-chat and return the joined reply.

    Args:
        app_id: The Omi persona app id (e.g. "persona_abc").
        api_key: The user's app API key (`omi_dev_...`). Sent as `Authorization: Bearer`.
        omi_base: Backend base URL (e.g. "https://api.omi.me").
        text: Inbound message text from the chat platform.
        timeout_seconds: Total request timeout. On timeout the function returns "".
        context: Optional platform context (sender name, chat title, etc.).
            Forwarded to the persona prompt but not used for retrieval.

    Returns:
        The concatenated persona reply (single string). Empty string on timeout/connect error.

    Raises:
        httpx.HTTPStatusError: On any non-2xx response. The plugin should decide whether to retry.
    """
    url = f"{omi_base.rstrip('/')}/v2/integrations/{app_id}/user/persona-chat"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    body: dict = {"text": text}
    if context:
        body["context"] = context

    timeout = httpx.Timeout(timeout_seconds)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=body)
            response.raise_for_status()
            chunks: list[str] = []
            async for event in EventSource(response).aiter_sse():
                # event.data is the joined payload of one SSE event — for the
                # persona-chat endpoint that's the chunk text (the backend yields
                # `data: <token>` per token, sometimes multi-line).
                if event.data:
                    chunks.append(event.data)
            return _join_chunks(chunks)
    except httpx.TimeoutException as e:
        logger.error(
            "persona chat timed out after %.1fs (app_id=%s)",
            timeout_seconds,
            app_id,
            extra={"err": str(e)},
        )
        return ""
    except httpx.ConnectError as e:
        logger.error(
            "persona chat connection failed (app_id=%s): %s",
            app_id,
            e,
        )
        return ""


def _join_chunks(chunks: Iterable[str]) -> str:
    """Join SSE chunk strings into the final reply.

    The backend emits one SSE event per LLM token. Tokens are emitted as
    `data: <text>` payloads. Adjacent tokens generally concatenate directly,
    but multi-line events (rare) should be joined with newlines.
    """
    # The backend's persona engine streams `data: <token>` events. The token
    # text is what we want — no extra separators between tokens, since the LLM
    # already includes any whitespace it intends. Multi-line `data:` frames
    # are joined with a newline so the original line break survives.
    return "".join(_split_lines(c) for c in chunks)


def _split_lines(data: str) -> str:
    """For multi-line SSE data frames, join with newlines; else return as-is.

    Multi-line events happen when the backend streams a chunk whose text
    itself contains a newline (rare but legitimate — code blocks, lists).
    We preserve blank lines so the reply formatting survives intact.
    """
    if "\n" not in data:
        return data
    # Preserve blank lines (was previously filtered — fixed per review feedback
    # from cubic). Each line as-is, joined with newlines.
    return "\n".join(data.splitlines())
