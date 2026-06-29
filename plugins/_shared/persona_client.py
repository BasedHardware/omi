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

import asyncio
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
    uid: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    context: Optional[dict] = None,
) -> str:
    """POST /v2/integrations/{app_id}/user/persona-chat and return the joined reply.

    Args:
        app_id: The Omi persona app id (e.g. "persona_abc").
        api_key: The user's app API key (`omi_dev_...`). Sent as `Authorization: Bearer`.
        omi_base: Backend base URL (e.g. "https://api.omi.me").
        text: Inbound message text from the chat platform.
        uid: The Omi user id the persona reply is generated for. REQUIRED —
            the backend route enforces that the API key was issued for this
            exact uid (auth boundary; an app-level key cannot impersonate
            arbitrary users).
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

    # httpx.Timeout sets per-phase timeouts (connect/read/write/pool) — it does
    # NOT enforce a wall-clock deadline. For SSE streams the read timeout resets
    # with each chunk, so the call can run far longer than `timeout_seconds`
    # under slow streams and starve webhook workers. We use asyncio.wait_for
    # to enforce a true wall-clock cap.
    timeout = httpx.Timeout(timeout_seconds)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # uid is sent as a query parameter because the backend uses it for
            # both route lookup (FastAPI extracts it from the URL) and the
            # tight auth check (api_key must be issued for this exact uid).
            #
            # We use client.stream() (not .post()) so the connection lifecycle
            # stays open while we iterate SSE events. client.post() would buffer
            # the entire body in memory before returning, defeating the
            # per-chunk read timeout and letting a slow stream hold a worker
            # far longer than `timeout_seconds`. Identified by cubic (P1).
            async with client.stream("POST", url, headers=headers, params={"uid": uid}, json=body) as response:
                response.raise_for_status()

                async def _consume_stream() -> str:
                    chunks: list[str] = []
                    async for event in EventSource(response).aiter_sse():
                        # event.data is the joined payload of one SSE event — for the
                        # persona-chat endpoint that's the chunk text (the backend yields
                        # `data: <token>` per token, sometimes multi-line).
                        if event.data:
                            chunks.append(event.data)
                    return _join_chunks(chunks)

                return await asyncio.wait_for(_consume_stream(), timeout=timeout_seconds)
    except httpx.TimeoutException as e:
        logger.error(
            "persona chat timed out after %.1fs (app_id=%s, uid=%s)",
            timeout_seconds,
            app_id,
            uid,
            extra={"err": str(e)},
        )
        return ""
    except asyncio.TimeoutError:
        # asyncio.wait_for raises asyncio.TimeoutError when the wall-clock cap
        # fires (P1.4 fix). httpx.TimeoutException only covers per-phase
        # transport timeouts, not the SSE wall-clock deadline.
        logger.error(
            "persona chat wall-clock timeout after %.1fs (app_id=%s, uid=%s)",
            timeout_seconds,
            app_id,
            uid,
        )
        return ""
    except httpx.ConnectError as e:
        logger.error(
            "persona chat connection failed (app_id=%s, uid=%s): %s",
            app_id,
            uid,
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
    """For multi-line SSE data frames, normalize line endings; else return as-is.

    Multi-line events happen when the backend streams a chunk whose text
    itself contains a newline (rare but legitimate — code blocks, lists).
    We use split("\n") (not splitlines()) because splitlines() silently
    drops trailing empty strings — e.g. "a\n\n" would split into ["a"]
    instead of ["a", ""], losing the trailing blank line. split("\n")
    preserves all empty strings at any position.
    """
    if "\n" not in data:
        return data
    # split("\n") preserves trailing empty strings; splitlines() would not.
    return "\n".join(data.split("\n"))
