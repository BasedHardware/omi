"""Relay G2 microphone audio into Omi as real conversations.

The glasses emit PCM16 LE mono at 16 kHz, which is exactly what `WS /v4/listen`
wants, so audio passes through unconverted.

Behaviors this encodes, each verified against the backend rather than assumed:

* **`source` must be a real `ConversationSource` member.** `_missing_` maps any
  unknown string to `unknown` instead of raising, so a typo does not fail loudly --
  it silently mislabels every conversation. `rayban_meta` is the correct value for
  third-party glasses (`docs/rayban-meta-device.md`) and is photo-capable, so
  `resolve_photo_conversation_source` won't later rewrite provenance to `openglass`.
* **Something must arrive inbound every 90 s** or the server closes with 1001
  (`routers/listen/runtime.py:312-323`). Any frame counts; a JSON frame with an
  unhandled `type` is ignored server-side, so it is a free keepalive.
* **The server sends the literal text `ping`**, which is not JSON. Parsing it blindly
  throws on every heartbeat.
* **Live transcript arrives as a bare JSON array**, not a `{"type": ...}` envelope
  (`routers/listen/transcripts.py:314`). Only new/updated segments are sent.
* **Closing the socket does not finalize the conversation.** Disconnect teardown only
  finalizes when `source == 'desktop'` and the close code is 1000
  (`runtime.py:612-639`), so we call `POST /v1/conversations` explicitly to close out.
* Frames of `<= 2` bytes are silently dropped (`receiver.py:491`), so we never emit them.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from urllib.parse import urlencode

import websockets

from omi_auth import OmiAuth

log = logging.getLogger(__name__)

SOURCE = 'rayban_meta'
SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2

# The server flushes to STT every 30 ms (960 bytes at 16 kHz). Sending a little more
# than that per frame keeps us comfortably above the 2-byte floor without bursting.
CHUNK_BYTES = 1920  # 60 ms
_MIN_FRAME_BYTES = 3

# Server closes after 90 s of inbound silence; stay well inside that.
_KEEPALIVE_INTERVAL = 25.0

# Silence appended on stop so the STT endpointer emits its final segment, and how
# long to wait for that segment to come back. ~2s of silence is well past any
# provider's endpointing window without meaningfully delaying the UI.
_FLUSH_SILENCE_FRAMES = 34  # 34 * 60ms ~= 2.0s
_FLUSH_SETTLE_SECONDS = 4.0

# How many times to try before concluding the socket will never work. Only
# applies before the first successful connect; after that, drops are treated as
# transient and retried for as long as capture is wanted.
_INITIAL_CONNECT_ATTEMPTS = 3
_INITIAL_CONNECT_DELAY = 0.5
_MAX_RECONNECT_DELAY = 30


@dataclass
class CaptureStats:
    bytes_sent: int = 0
    frames_sent: int = 0
    segments_received: int = 0
    conversation_id: str | None = None
    started_at: float = field(default_factory=time.monotonic)
    last_error: str | None = None
    reconnects: int = 0

    @property
    def audio_seconds(self) -> float:
        return self.bytes_sent / (SAMPLE_RATE * BYTES_PER_SAMPLE)


SegmentCallback = Callable[[list[dict]], Awaitable[None]]
EventCallback = Callable[[dict], Awaitable[None]]


def listen_url(base_url: str, *, language: str = 'en') -> str:
    """Build the /v4/listen URL with the parameters the G2 stream needs."""
    ws_base = base_url.replace('https://', 'wss://').replace('http://', 'ws://').rstrip('/')
    query = urlencode(
        {
            'source': SOURCE,
            'codec': 'pcm16',
            'sample_rate': str(SAMPLE_RATE),
            'channels': '1',
            'language': language,
            'include_speech_profile': 'true',
            # Values below 120 are clamped up server-side; pass the real floor.
            'conversation_timeout': '120',
        }
    )
    return f'{ws_base}/v4/listen?{query}'


class CaptureSession:
    """One live audio session streaming glasses PCM into Omi."""

    def __init__(
        self,
        auth: OmiAuth,
        base_url: str,
        on_segments: SegmentCallback | None = None,
        on_event: EventCallback | None = None,
    ) -> None:
        self._auth = auth
        self._base = base_url.rstrip('/')
        self._on_segments = on_segments
        self._on_event = on_event
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=256)
        self._pending = bytearray()
        self._task: asyncio.Task | None = None
        self.stats = CaptureStats()
        self.active = False

    async def start(self) -> None:
        if self.active:
            return
        self.active = True
        self.stats = CaptureStats()
        self._task = asyncio.create_task(self._run(), name='omi-even-capture')

    async def stop(self, finalize: bool = True) -> CaptureStats:
        """Stop streaming. `finalize` closes out the Omi conversation immediately.

        Sends a short tail of silence before closing. The STT endpointer only emits
        its final segment once it hears the utterance end, so cutting the stream
        immediately after speech loses the last sentence -- measured: a 7.4s clip
        yielded only its first 2.8s without this, and the full text with it.
        """
        if not self.active:
            return self.stats

        # Flush the partial frame first so the tail of real audio is not lost.
        if len(self._pending) >= _MIN_FRAME_BYTES:
            with contextlib.suppress(asyncio.QueueFull):
                self._queue.put_nowait(bytes(self._pending))
        self._pending.clear()

        silence = b'\x00' * CHUNK_BYTES
        for _ in range(_FLUSH_SILENCE_FRAMES):
            with contextlib.suppress(asyncio.QueueFull):
                self._queue.put_nowait(silence)
        # Give the server time to run the endpointer over that silence and send
        # the closing segment before we tear the socket down.
        await asyncio.sleep(_FLUSH_SETTLE_SECONDS)

        self.active = False
        with contextlib.suppress(asyncio.QueueFull):
            self._queue.put_nowait(None)

        if self._task is not None:
            with contextlib.suppress(asyncio.CancelledError, TimeoutError):
                await asyncio.wait_for(self._task, timeout=10)
            self._task = None

        if finalize:
            await self._finalize_conversation()
        return self.stats

    def feed(self, pcm: bytes) -> None:
        """Accept PCM from the glasses, batching into sensibly sized frames.

        Non-blocking by design: audio arrives on the app WebSocket and must never
        be stalled by backpressure here. If the queue is full we drop and count it
        rather than let the socket read loop back up.
        """
        if not self.active or not pcm:
            return
        self._pending.extend(pcm)
        while len(self._pending) >= CHUNK_BYTES:
            frame = bytes(self._pending[:CHUNK_BYTES])
            del self._pending[:CHUNK_BYTES]
            try:
                self._queue.put_nowait(frame)
            except asyncio.QueueFull:
                self.stats.last_error = 'audio queue full; dropped a frame'
                log.warning('capture queue full -- dropping %d bytes', len(frame))

    async def _finalize_conversation(self) -> None:
        """Ask Omi to close the in-progress conversation.

        Needed because disconnect-time finalization is desktop-only; without this
        the conversation lingers `in_progress` until a later session finds it stale.
        """
        import httpx  # local: only needed on the stop path

        try:
            headers = await self._auth.auth_header()
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(f'{self._base}/v1/conversations', headers=headers)
            if response.status_code >= 400:
                log.warning('finalize returned HTTP %s: %.160s', response.status_code, response.text)
            else:
                log.info('conversation finalized')
        except Exception as exc:  # noqa: BLE001 - stop() must never raise
            log.warning('could not finalize conversation: %s', exc)

    async def _run(self) -> None:
        """Hold the listen socket open for as long as capture is wanted.

        Built for all-day wear, so a dropped connection is expected rather than
        exceptional: Wi-Fi roams, the laptop sleeps, the server closes an idle
        socket with 1001. Any of those used to end capture permanently and
        silently. Instead we reconnect with backoff until `stop()` is called.

        The auth header is rebuilt per attempt so a reconnect after the ID token's
        one-hour expiry mints a fresh one instead of looping on 401.
        """
        url = listen_url(self._base)
        attempt = 0
        connected_once = False

        while self.active:
            try:
                headers = await self._auth.auth_header()
                async with websockets.connect(url, additional_headers=headers, max_size=None) as socket:
                    if attempt:
                        log.info('capture socket reconnected after %d attempt(s)', attempt)
                    else:
                        log.info('capture socket open (source=%s)', SOURCE)
                    attempt = 0  # a successful connect resets the backoff
                    connected_once = True
                    self.stats.last_error = None

                    sender = asyncio.create_task(self._send_loop(socket), name='capture-send')
                    receiver = asyncio.create_task(self._recv_loop(socket), name='capture-recv')
                    done, pending = await asyncio.wait(
                        {sender, receiver}, return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in pending:
                        task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await task
                    for task in done:
                        # `.exception()` re-raises on a cancelled task, which would
                        # look like the session itself being cancelled.
                        if task.cancelled():
                            continue
                        exc = task.exception()
                        if exc:
                            raise exc

                # Both loops finished without error: that only happens when the
                # send loop consumed the stop sentinel, so this is a clean exit.
                if not self.active:
                    break
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - reconnect, never crash the bridge
                self.stats.last_error = f'{type(exc).__name__}: {exc}'
                log.warning('capture socket dropped: %s', self.stats.last_error)

            if not self.active:
                break

            # A socket that has never connected is a configuration or auth problem
            # -- a bad URL, a revoked token -- and retrying forever would hide it.
            # One that connected and then dropped is a network blip during all-day
            # wear, which is expected and worth retrying for a long time.
            if not connected_once and attempt + 1 >= _INITIAL_CONNECT_ATTEMPTS:
                log.error('capture never connected after %d attempts; giving up', attempt + 1)
                break

            attempt += 1
            self.stats.reconnects += 1
            if connected_once:
                # Transient drop during all-day wear. Back off, but cap it so the
                # session recovers promptly once the network returns rather than
                # sitting out a long sleep.
                delay = min(2**attempt, _MAX_RECONNECT_DELAY)
            else:
                # Still probing a socket that has never worked; retry quickly so a
                # misconfiguration surfaces in a second rather than a minute.
                delay = _INITIAL_CONNECT_DELAY
            log.info('reconnecting capture in %ss (attempt %d)', delay, attempt)
            await asyncio.sleep(delay)

        self.active = False
        log.info(
            'capture ended: %.1fs audio, %d segments, %d reconnects',
            self.stats.audio_seconds,
            self.stats.segments_received,
            self.stats.reconnects,
        )

    async def _send_loop(self, socket) -> None:
        while True:
            try:
                frame = await asyncio.wait_for(self._queue.get(), timeout=_KEEPALIVE_INTERVAL)
            except TimeoutError:
                # Any inbound frame resets the server's 90s activity timer. An
                # unrecognized `type` is a documented no-op on the server.
                await socket.send(json.dumps({'type': 'keepalive'}))
                continue
            if frame is None:
                return
            if len(frame) < _MIN_FRAME_BYTES:
                continue
            await socket.send(frame)
            self.stats.bytes_sent += len(frame)
            self.stats.frames_sent += 1

    async def _recv_loop(self, socket) -> None:
        async for raw in socket:
            if isinstance(raw, bytes):
                continue
            # The heartbeat is the literal string "ping" -- not JSON.
            if raw == 'ping':
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                log.debug('non-JSON frame from listen: %.60s', raw)
                continue

            # Live transcript arrives as a bare array, with no type envelope.
            if isinstance(payload, list):
                self.stats.segments_received += len(payload)
                if self._on_segments:
                    await self._on_segments(payload)
                continue

            if isinstance(payload, dict):
                kind = payload.get('type')
                if kind == 'conversation_session':
                    self.stats.conversation_id = payload.get('conversation_id')
                    log.info('capture conversation id: %s', self.stats.conversation_id)
                elif kind == 'freemium_threshold_reached':
                    self.stats.last_error = 'transcription quota nearly exhausted'
                    log.warning('%s', self.stats.last_error)
                if self._on_event:
                    await self._on_event(payload)
