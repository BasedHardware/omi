"""Client for the Omi APIs the glasses need.

The important piece is `POST /v2/messages`. It advertises `text/event-stream` and
`response_model=ResponseMessage`, and both are misleading:

* It is **always** a stream -- the declared JSON response model is never returned
  (`backend/routers/chat.py:481`).
* It is **not** spec-compliant SSE. `EventSource` silently drops most of it. Frames
  are `\\n\\n`-delimited records with a bare prefix, so the body must be buffered and
  split manually.

Frame protocol, ported from the app's reference parser
(`app/lib/backend/http/api/messages.dart:59` `parseMessageChunk`):

    data: <token>       token delta; literal `__CRLF__` stands in for a newline
    think: <text>       progress/status line, same `__CRLF__` escaping
    error: <message>    terminal error
    error:402:<body>    legacy quota shape, no space after the colon
    done: <base64>      terminal; base64 of the authoritative ResponseMessage JSON
    message: <base64>   voice endpoint only; the transcribed user message

A well-formed stream always ends in `done:` or `error:`.

Two traps worth knowing:

* A quota breach returns **HTTP 200** with a canned `done:` message, not a 402
  (`chat.py:299-313`). Read the text, not the status code.
* The agent may run to 150s while the server's default request timeout is 120s
  (`utils/other/timeout.py:20`), so a slow answer can die as a bare 504 with no
  terminal frame. Callers must treat stream truncation as a real outcome.

`X-App-Platform` is deliberately not sent: only `desktop` is trial-paywalled
(`utils/subscription.py:270`), and an absent platform never is. `X-Request-Start-Time`
is also omitted -- clock skew beyond the allowance is rejected with a 408.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import os
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field

import httpx

from omi_auth import OmiAuth

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = os.getenv('OMI_API_BASE', 'https://api.omi.me')

_FRAME_SEP = b'\n\n'
# Generous: the agent's own hard cap is 150s. The read timeout must exceed the
# gap between frames, not the total, since keepalives arrive every ~20s.
_STREAM_TIMEOUT = httpx.Timeout(180.0, connect=10.0, read=60.0)
_JSON_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


@dataclass
class ChatEvent:
    """One decoded frame from the chat stream."""

    kind: str  # 'data' | 'think' | 'error' | 'done' | 'message'
    text: str = ''
    message: dict | None = None


@dataclass
class ChatResult:
    """The outcome of a complete chat turn."""

    text: str
    error: str | None = None
    truncated: bool = False  # stream ended without a terminal frame
    elapsed_s: float = 0.0
    thinking: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.text.strip())


def _decode_b64_json(payload: str) -> dict | None:
    try:
        decoded = json.loads(base64.b64decode(payload).decode('utf-8'))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        log.warning('could not decode terminal frame: %s', exc)
        return None
    # Valid JSON is not necessarily an object: b64decode ignores non-alphabet
    # characters, so a corrupted payload can decode to a bare list or number.
    # The caller does `.get()` on this, so anything else must read as absent.
    if not isinstance(decoded, dict):
        log.warning('terminal frame was %s, not a JSON object', type(decoded).__name__)
        return None
    return decoded


def parse_frame(frame: str) -> ChatEvent | None:
    """Decode one `\\n\\n`-delimited frame. Returns None if unrecognized.

    Mirrors `parseMessageChunk` in the Flutter client, including the `__CRLF__`
    un-escaping that applies to both `data:` and `think:`.
    """
    # Checked before `error: ` -- this legacy variant has no space after the colon.
    if frame.startswith('error:402:'):
        return ChatEvent('error', frame[len('error:402:') :].strip())

    if frame.startswith('error: '):
        text = frame[len('error: ') :].strip()
        return ChatEvent('error', text or 'Omi returned an unspecified error')

    if frame.startswith('think: '):
        return ChatEvent('think', frame[len('think: ') :].replace('__CRLF__', '\n'))

    if frame.startswith('data: '):
        return ChatEvent('data', frame[len('data: ') :].replace('__CRLF__', '\n'))

    if frame.startswith('done: '):
        decoded = _decode_b64_json(frame[len('done: ') :])
        return ChatEvent('done', (decoded or {}).get('text', ''), decoded)

    if frame.startswith('message: '):
        decoded = _decode_b64_json(frame[len('message: ') :])
        return ChatEvent('message', (decoded or {}).get('text', ''), decoded)

    return None


class OmiClient:
    def __init__(self, auth: OmiAuth, base_url: str = DEFAULT_BASE_URL) -> None:
        self._auth = auth
        self._base = base_url.rstrip('/')

    async def _headers(self) -> dict[str, str]:
        return await self._auth.auth_header()

    async def chat_stream(self, text: str, app_id: str | None = None) -> AsyncIterator[ChatEvent]:
        """Stream one chat turn, yielding decoded frames as they arrive."""
        url = f'{self._base}/v2/messages'
        params = {'app_id': app_id} if app_id else None
        headers = {**await self._headers(), 'Content-Type': 'application/json'}

        async with httpx.AsyncClient(timeout=_STREAM_TIMEOUT) as client:
            async with client.stream(
                'POST', url, params=params, headers=headers, json={'text': text, 'file_ids': []}
            ) as response:
                if response.status_code != 200:
                    body = (await response.aread()).decode('utf-8', errors='replace')[:300]
                    yield ChatEvent('error', f'HTTP {response.status_code}: {body}')
                    return

                buffer = b''
                async for chunk in response.aiter_bytes():
                    buffer += chunk
                    # Frames are separated, not terminated -- the tail stays buffered.
                    while _FRAME_SEP in buffer:
                        raw, buffer = buffer.split(_FRAME_SEP, 1)
                        frame = raw.decode('utf-8', errors='replace')
                        if not frame.strip():
                            continue
                        event = parse_frame(frame)
                        if event is None:
                            log.debug('ignoring unrecognized frame: %.80s', frame)
                            continue
                        yield event

                # A final frame without a trailing separator is still valid.
                tail = buffer.decode('utf-8', errors='replace').strip()
                if tail:
                    event = parse_frame(tail)
                    if event is not None:
                        yield event

    async def chat(
        self,
        text: str,
        app_id: str | None = None,
        deadline_s: float | None = None,
        enough: Callable[[str], bool] | None = None,
    ) -> ChatResult:
        """Run a chat turn to completion, or to `deadline_s`, whichever comes first.

        The deadline exists because the glasses' client will give up long before
        Omi's 150s agent cap. On timeout the partial answer accumulated so far is
        returned rather than nothing -- a truncated answer beats a spinner.

        `enough` stops the stream early once the accumulated text is already more
        than the caller can display. Omi writes for a phone and routinely emits
        three times what fits on the glasses; measured, waiting for the rest costs
        about 3 seconds per answer that the user never sees. The predicate is only
        consulted on `data` frames, and a stream stopped this way is *not* marked
        truncated -- the answer shown is complete as far as the display goes.
        """
        started = time.monotonic()
        parts: list[str] = []
        thinking: list[str] = []
        final_text = ''
        error: str | None = None
        saw_terminal = False

        stream = self.chat_stream(text, app_id=app_id)
        try:
            while True:
                remaining = None
                if deadline_s is not None:
                    remaining = deadline_s - (time.monotonic() - started)
                    if remaining <= 0:
                        break
                try:
                    event = await asyncio.wait_for(anext(stream), timeout=remaining)
                except StopAsyncIteration:
                    break
                except TimeoutError:
                    break

                if event.kind == 'data':
                    parts.append(event.text)
                    if enough is not None and enough(''.join(parts)):
                        saw_terminal = True  # complete for display purposes
                        break
                elif event.kind == 'think':
                    thinking.append(event.text)
                elif event.kind == 'error':
                    error = event.text
                    saw_terminal = True
                    break
                elif event.kind == 'done':
                    # Authoritative: prefer it over the accumulated deltas.
                    final_text = event.text or ''.join(parts)
                    saw_terminal = True
                    break
        finally:
            await stream.aclose()

        elapsed = time.monotonic() - started
        answer = (final_text or ''.join(parts)).strip()
        return ChatResult(
            text=answer,
            error=error,
            truncated=not saw_terminal,
            elapsed_s=elapsed,
            thinking=thinking,
        )

    async def get_messages(self, limit: int = 20, app_id: str | None = None) -> list[dict]:
        """Recent chat history, newest last (server caps this at 100)."""
        headers = await self._headers()
        params = {'app_id': app_id} if app_id else None
        async with httpx.AsyncClient(timeout=_JSON_TIMEOUT) as client:
            response = await client.get(f'{self._base}/v2/messages', params=params, headers=headers)
        response.raise_for_status()
        messages = response.json()
        return messages[-limit:] if isinstance(messages, list) else []

    async def transcribe_pcm(
        self,
        pcm: bytes,
        sample_rate: int = 16000,
        channels: int = 1,
        language: str = 'en',
    ) -> str:
        """Transcribe raw PCM16 via the endpoint's octet-stream mode.

        The G2 mic emits exactly PCM16 LE mono at 16 kHz, so nothing is resampled.
        """
        headers = {**await self._headers(), 'Content-Type': 'application/octet-stream'}
        params = {
            'language': language,
            'encoding': 'linear16',
            'sample_rate': str(sample_rate),
            'channels': str(channels),
        }
        async with httpx.AsyncClient(timeout=_JSON_TIMEOUT) as client:
            response = await client.post(
                f'{self._base}/v2/voice-message/transcribe',
                params=params,
                headers=headers,
                content=pcm,
            )
        if response.status_code != 200:
            raise RuntimeError(f'transcribe failed: HTTP {response.status_code} {response.text[:200]}')
        return (response.json() or {}).get('transcript', '')

    async def _get_json(self, path: str, params: dict | None = None):
        headers = await self._headers()
        async with httpx.AsyncClient(timeout=_JSON_TIMEOUT) as client:
            response = await client.get(f'{self._base}{path}', params=params, headers=headers)
        response.raise_for_status()
        return response.json()

    async def memories(self, limit: int = 20) -> list[dict]:
        """Recent memories. Note `offset=0` makes the server ignore `limit` and
        return up to 5000 (`routers/memories.py:740`), so we slice client-side."""
        rows = await self._get_json('/v3/memories', {'limit': limit, 'offset': 0})
        return rows[:limit] if isinstance(rows, list) else []

    async def action_items(self, limit: int = 20) -> list[dict]:
        payload = await self._get_json('/v1/action-items', {'limit': limit})
        if isinstance(payload, dict):
            payload = payload.get('action_items') or payload.get('items') or []
        return payload[:limit] if isinstance(payload, list) else []

    async def daily_summaries(self, limit: int = 3) -> list[dict]:
        payload = await self._get_json('/v1/users/daily-summaries', {'limit': limit})
        if isinstance(payload, dict):
            payload = payload.get('daily_summaries') or payload.get('items') or []
        return payload[:limit] if isinstance(payload, list) else []

    async def tool_search(self, tool: str, payload: dict) -> str:
        """Call one of Omi's direct retrieval tools and return its text result.

        These skip the agent loop entirely. Measured against the live account:
        memories 1.5s, conversations 0.8s, versus 6-18s for `/v2/messages`. That
        difference is what makes an answer arrive before Even's client gives up.
        """
        headers = {**await self._headers(), 'Content-Type': 'application/json'}
        async with httpx.AsyncClient(timeout=_JSON_TIMEOUT) as client:
            response = await client.post(
                f'{self._base}/v1/tools/{tool}', headers=headers, json=payload
            )
        if response.status_code != 200:
            raise RuntimeError(f'{tool} failed: HTTP {response.status_code}')
        body = response.json() or {}
        if body.get('is_error'):
            raise RuntimeError(f'{tool} reported an error')
        return body.get('result_text', '')

    async def usage_quota(self) -> dict:
        headers = await self._headers()
        async with httpx.AsyncClient(timeout=_JSON_TIMEOUT) as client:
            response = await client.get(f'{self._base}/v1/users/me/usage-quota', headers=headers)
        response.raise_for_status()
        return response.json()
