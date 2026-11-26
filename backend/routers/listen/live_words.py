"""Reliability experiment ``vendor_recognizer_on_opened_app``: a store-nothing display stream.

While the phone app is in front and capturing, it sends a copy of the audio here on its own WebSocket
(``/v4/live-words``), separate from the listening connection and from the phone files that carry the
record. The audio goes to Soniox and the words come back as lines the phone shows where its own
recogniser returned nothing.

Nothing is stored and no text is logged: this module never touches a conversation, a recording row,
the transcript processor or the plan allowance. The record stays what batch makes of the audio the
phone uploads. A failure here closes this connection only; capture is on other connections.

Clock: the phone owns it. A line's ``start`` and ``end`` are seconds of audio counted from the first
frame this connection received, and the phone places them on its own capture time of that frame.

Silence: the phone's connection stays open through it. After ``PROVIDER_IDLE_SECONDS`` without audio
only the Soniox stream is closed, and the next audio dials a new one on the same connection. A pendant
that sends nothing while it is quiet would otherwise make the phone reconnect after every pause, and
production counts new connections per signed-in user on the listen service (20 in 5 minutes, shared
with the capture connection).

Limits: one connection per account and app install (a new one replaces the old), the connection
closes when no audio arrives for ``IDLE_SECONDS``, and audio held while Soniox is dialled is bounded.

Off, the endpoint refuses every connection.

Deployment: production's load balancer sends only the exact paths ``/v3/listen``, ``/v4/listen`` and
``/v4/web/listen`` to the listen service. Until ``/v4/live-words`` has a rule of its own it lands on the
main backend service (as it does on the local prod-parity stack, whose edge follows the same map). A
separate path is deliberate: a server build without this module refuses it, where an extra parameter on
``/v4/listen`` would open a real listening session from display audio.
"""

import asyncio
import json
import logging
import time
import uuid
from collections import deque
from typing import Any

from fastapi import WebSocketException
from fastapi.websockets import WebSocket, WebSocketDisconnect
from prometheus_client import Counter

from config import reliability_experiments
from utils.async_tasks import create_named_task
from utils.stt.live_failure import live_stt_socket_is_dead
from utils.stt.provider_stream_end import begin_stream_close
from utils.stt.replay_delivery import abort_replay_socket
from utils.stt.socket import release_live_stt_socket, track_live_stt_socket
from utils.stt.soniox import process_audio_soniox
from utils.stt.streaming import STTService

logger = logging.getLogger(__name__)

# Optional at import, as in the receiver: only an Opus connection needs the native library.
opuslib: Any = None
try:
    import opuslib as opuslib_module  # type: ignore[reportMissingImports]
except Exception:  # pragma: no cover - depends on the image
    pass
else:
    opuslib = opuslib_module

EXPERIMENT = 'vendor_recognizer_on_opened_app'
PROVIDER = STTService.soniox.value
SAMPLE_RATE = 16000
CODECS = frozenset({'opus', 'pcm16'})
# Largest Opus frame is 120 ms; the decoder never writes more than the packet holds.
OPUS_DECODE_CAPACITY = SAMPLE_RATE // 1000 * 120
# No audio for this long closes the provider stream only; the phone's connection stays, and the next
# audio dials again. So a quiet room costs no provider time and no new connection.
PROVIDER_IDLE_SECONDS = 20.0
# The phone closes the connection itself when it leaves the front, pauses or stops. One that stays open
# this long without audio is closed here, so a phone that vanished cannot hold a place on the server.
IDLE_SECONDS = 600.0
RECEIVE_POLL_SECONDS = 1.0
# A stream that was asked to finish is given this long to deliver its last words before it is cut.
RETIRE_GRACE_SECONDS = 3.0
# Dials are spaced at least this far apart, and this many in a row without a word end the connection.
REDIAL_SECONDS = 1.0
MAX_PROVIDER_FAILURES = 3
DIAL_TIMEOUT_SECONDS = 10.0
# Audio that arrives while the provider is dialled (the phone's 3 s lead-in comes first) is kept and
# sent first. Bounded; when it overflows the oldest audio falls out and the line clock is moved on.
DIAL_BUFFER_SECONDS = 8.0
# The phone learns from these how much audio arrived, and drops its display audio when they stop.
ACK_SECONDS = 1.0
# The provider reports words. They are joined into one line per speaker turn, as a transcript is.
LINE_GAP_SECONDS = 3.0
LINE_MAX_CHARS = 600
# One frame larger than any real one is a client fault, not audio.
MAX_FRAME_BYTES = 64 * 1024

CLOSE_REPLACED = 4009
CLOSE_IDLE = 4008

OMI_LISTEN_LIVE_WORDS_TOTAL = Counter(
    'omi_listen_live_words_total',
    'Display-only live-words connections by bounded outcome',
    ['outcome'],
)
OMI_LISTEN_LIVE_WORDS_SECONDS_TOTAL = Counter(
    'omi_listen_live_words_seconds_total',
    'Seconds a display-only live-words connection held a provider stream open',
)
OMI_LISTEN_LIVE_WORDS_AUDIO_SECONDS_TOTAL = Counter(
    'omi_listen_live_words_audio_seconds_total',
    'Seconds of audio received on display-only live-words connections',
)

# (uid, app install) -> the one open session. Process-local: a second listen pod cannot see it, and
# the idle close bounds a connection this map could not replace.
_sessions: dict[tuple[str, str], 'LiveWordsSession'] = {}


class LineJoiner:
    """Joins the provider's words into lines; remembers which lines changed since they were last sent."""

    def __init__(self) -> None:
        self.line: dict[str, Any] | None = None
        self.dirty: dict[str, dict[str, Any]] = {}
        self.lines = 0
        self.words = 0

    def add(self, segments: list[dict[str, Any]], base: float) -> None:
        for segment in segments:
            text = str(segment.get('text') or '').strip()
            if not text:
                continue
            start = max(0.0, base + float(segment.get('start') or 0.0))
            end = max(start, base + float(segment.get('end') or 0.0))
            speaker = str(segment.get('speaker') or 'SPEAKER_00')
            line = self.line
            if (
                line is None
                or line['speaker'] != speaker
                or start - line['end'] >= LINE_GAP_SECONDS
                or len(line['text']) + len(text) > LINE_MAX_CHARS
            ):
                line = self.line = {
                    'id': uuid.uuid4().hex,
                    'speaker': speaker,
                    'start': start,
                    'end': end,
                    'text': text,
                    'words': [],
                }
                self.lines += 1
            else:
                line['text'] = f"{line['text']} {text}"
                line['end'] = max(line['end'], end)
            line['words'].append([text, round(start, 3), round(end, 3)])
            self.words += 1
            self.dirty[line['id']] = line

    def take(self) -> list[dict[str, Any]]:
        changed, self.dirty = list(self.dirty.values()), {}
        return [
            {
                'id': line['id'],
                'speaker': line['speaker'],
                'start': round(line['start'], 3),
                'end': round(line['end'], 3),
                'text': line['text'],
                'words': list(line['words']),
            }
            for line in changed
        ]


class LiveWordsSession:
    def __init__(self, websocket: WebSocket, uid: str, device: str, codec: str, language: str):
        self.websocket = websocket
        self.uid = uid
        self.device = device
        self.codec = codec
        self.language = language
        self.decoder: Any = None
        self.socket: Any = None
        self.opening: asyncio.Task[Any] | None = None
        self.sender: asyncio.Task[Any] | None = None
        self.stop_reason: str | None = None
        self.joiner = LineJoiner()
        self.pending: deque[bytes] = deque()
        self.pending_bytes = 0
        # Streams that were asked to finish, with the time they were: cut after RETIRE_GRACE_SECONDS.
        self.retired: list[tuple[Any, float]] = []
        self.failures = 0
        self.next_dial_at = 0.0
        self.provider_opened_at: float | None = None
        self.provider_seconds = 0.0
        self.provider_streams = 0
        self.frames = 0
        self.samples = 0
        self.undecodable = 0
        self.last_audio_at = time.monotonic()
        self.last_ack_at = 0.0
        self._send_lock = asyncio.Lock()

    # --- lifecycle -----------------------------------------------------------------------------

    def stop(self, reason: str) -> None:
        if self.stop_reason is None:
            self.stop_reason = reason

    async def run(self) -> None:
        key = (self.uid, self.device)
        previous = _sessions.get(key)
        _sessions[key] = self
        if previous is not None:
            previous.stop('replaced')
        if self.codec == 'opus':
            self.decoder = _opus_decoder()
        self._dial()  # At once: the lead-in the phone sends first should not wait for a dial.
        logger.info('event=live_words action=connect uid=%s codec=%s', self.uid, self.codec)
        try:
            await self._receive()
        finally:
            if _sessions.get(key) is self:
                del _sessions[key]
            await self._shutdown()

    async def _receive(self) -> None:
        while self.stop_reason is None:
            now = time.monotonic()
            if now - self.last_audio_at >= IDLE_SECONDS:
                self.stop('idle')
                break
            if self.socket is not None and live_stt_socket_is_dead(self.socket):
                self._provider_lost()
            elif self.socket is not None and now - self.last_audio_at >= PROVIDER_IDLE_SECONDS:
                # Quiet: give the provider stream back and keep the phone's connection.
                self._retire_provider('provider_idle')
            await self._cut_retired(now)
            if self.stop_reason is not None:
                break
            try:
                message = await asyncio.wait_for(self.websocket.receive(), timeout=RECEIVE_POLL_SECONDS)
            except asyncio.TimeoutError:
                continue
            except (WebSocketDisconnect, RuntimeError):
                self.stop('client')
                break
            if message.get('type') == 'websocket.disconnect':
                self.stop('client')
                break
            data = message.get('bytes')
            if data:
                if len(data) > MAX_FRAME_BYTES:
                    self.stop('bad_frame')
                    break
                self._audio(data)
            if self.frames and time.monotonic() - self.last_ack_at >= ACK_SECONDS:
                self.last_ack_at = time.monotonic()
                await self._send({'type': 'ack', 'frames': self.frames, 'audio_ms': self.samples * 1000 // SAMPLE_RATE})

    async def _shutdown(self) -> None:
        reason = self.stop_reason or 'client'
        for task in (self.opening, self.sender):
            if task is not None and task is not asyncio.current_task():
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        self.opening = self.sender = None
        self._retire_provider(None)
        self.pending.clear()
        self.pending_bytes = 0
        seconds = self.provider_seconds
        OMI_LISTEN_LIVE_WORDS_AUDIO_SECONDS_TOTAL.inc(self.samples / SAMPLE_RATE)
        OMI_LISTEN_LIVE_WORDS_TOTAL.labels(outcome=reason).inc()
        # Counts only: the words themselves are never logged.
        logger.info(
            'event=live_words action=close uid=%s reason=%s seconds=%.1f streams=%d audio_seconds=%.1f frames=%d '
            'undecodable=%d lines=%d words=%d',
            self.uid,
            reason,
            seconds,
            self.provider_streams,
            self.samples / SAMPLE_RATE,
            self.frames,
            self.undecodable,
            self.joiner.lines,
            self.joiner.words,
        )
        await self._cut_retired(None)
        code = {'replaced': CLOSE_REPLACED, 'idle': CLOSE_IDLE, 'client': 1000, 'bad_frame': 1008}.get(reason, 1011)
        try:
            await self.websocket.close(code=code, reason=reason)
        except Exception:
            pass  # Already closed by the phone.

    # --- provider stream -----------------------------------------------------------------------

    def _dial(self) -> None:
        """Start a dial unless one is running, a stream is open, or the last dial was a moment ago."""
        if self.stop_reason is not None or self.socket is not None:
            return
        if self.opening is not None and not self.opening.done():
            return
        now = time.monotonic()
        if now < self.next_dial_at:
            return
        self.next_dial_at = now + REDIAL_SECONDS
        self.opening = create_named_task(self._open(), name='live_words_open')

    async def _open(self) -> None:
        raw = None
        adopted = False
        stream: dict[str, Any] = {'base': None}

        def words(segments: list[dict[str, Any]]) -> None:
            self._words(stream, segments)

        try:
            # Same-task timeout keeps ownership of the candidate explicit on cancellation.
            async with asyncio.timeout(DIAL_TIMEOUT_SECONDS):
                raw = await process_audio_soniox(words, SAMPLE_RATE, self.language, uid=self.uid)
            if self.stop_reason is not None:
                return
            self.socket = track_live_stt_socket(raw, PROVIDER)
            adopted = True
            # The provider's zero is the first sample it is sent: everything received on this connection
            # before the audio still waiting here. Lines are timed from the connection's first frame.
            stream['base'] = (self.samples - self.pending_bytes // 2) / SAMPLE_RATE
            self.joiner.line = None  # A new stream starts a new line.
            self.provider_opened_at = time.monotonic()
            self.provider_streams += 1
            OMI_LISTEN_LIVE_WORDS_TOTAL.labels(outcome='opened').inc()
            logger.info('event=live_words action=open uid=%s stream=%d', self.uid, self.provider_streams)
            self._drain_pending()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.warning('Live words provider dial failed type=%s', type(error).__name__)
            self._provider_failed('provider_unavailable')
        finally:
            if raw is not None and not adopted:
                await abort_replay_socket(raw, timeout=2)

    def _retire_provider(self, outcome: str | None) -> None:
        """Ask the open stream to finish and let go of it. The phone's connection is not touched."""
        socket, self.socket = self.socket, None
        if self.provider_opened_at is not None:
            seconds = max(0.0, time.monotonic() - self.provider_opened_at)
            self.provider_seconds += seconds
            self.provider_opened_at = None
            OMI_LISTEN_LIVE_WORDS_SECONDS_TOTAL.inc(seconds)
        if socket is None:
            return
        if outcome is not None:
            OMI_LISTEN_LIVE_WORDS_TOTAL.labels(outcome=outcome).inc()
            logger.info('event=live_words action=%s uid=%s', outcome, self.uid)
        try:
            begin_stream_close(socket)
            socket.finish()
        except Exception:
            pass  # An optional stream; it is cut below either way.
        finally:
            release_live_stt_socket(socket)
        self.retired.append((socket, time.monotonic()))

    async def _cut_retired(self, now: float | None) -> None:
        """Close retired streams for good once they had their grace; all of them when [now] is None."""
        keep: list[tuple[Any, float]] = []
        for socket, retired_at in self.retired:
            if now is not None and now - retired_at < RETIRE_GRACE_SECONDS:
                keep.append((socket, retired_at))
            else:
                await abort_replay_socket(socket, timeout=2)
        self.retired = keep

    def _provider_lost(self) -> None:
        self._retire_provider('provider_lost')
        self._provider_failed('provider_lost')

    def _provider_failed(self, reason: str) -> None:
        """A dial or a stream failed. The next audio dials again; several in a row end the connection."""
        self.failures += 1
        if self.failures >= MAX_PROVIDER_FAILURES:
            self.stop(reason)

    def _drain_pending(self) -> bool:
        while self.pending:
            held = self.pending.popleft()
            self.pending_bytes -= len(held)
            if self.socket.send(held) is False:
                self._provider_lost()
                return False
        return True

    # --- audio ---------------------------------------------------------------------------------

    def _audio(self, data: bytes) -> None:
        if self.codec == 'opus':
            try:
                pcm = self.decoder.decode(bytes(data), frame_size=OPUS_DECODE_CAPACITY)
            except Exception:
                self.undecodable += 1
                return
        else:
            pcm = bytes(data[: len(data) - len(data) % 2])
        if not pcm:
            return
        self.frames += 1
        self.samples += len(pcm) // 2
        self.last_audio_at = time.monotonic()
        if self.socket is None:
            self.pending.append(pcm)
            self.pending_bytes += len(pcm)
            limit = int(DIAL_BUFFER_SECONDS * SAMPLE_RATE) * 2
            while self.pending_bytes > limit and len(self.pending) > 1:
                self.pending_bytes -= len(self.pending.popleft())  # Display audio only; the line clock moves on.
            self._dial()  # After silence, or after a lost stream: the audio itself asks for a new one.
            return
        if self._drain_pending() and self.socket is not None and self.socket.send(pcm) is False:
            self._provider_lost()

    # --- lines to the phone --------------------------------------------------------------------

    def _words(self, stream: dict[str, Any], segments: list[dict[str, Any]]) -> None:
        if self.stop_reason is not None or stream['base'] is None:
            return  # A late callback from a closing connection never reaches the phone.
        self.failures = 0
        self.joiner.add(segments, stream['base'])
        if self.joiner.dirty and (self.sender is None or self.sender.done()):
            self.sender = create_named_task(self._send_lines(), name='live_words_lines')

    async def _send_lines(self) -> None:
        """One sender at a time, so a line's later text can never overtake its earlier text."""
        while self.joiner.dirty and self.stop_reason is None:
            await self._send({'type': 'lines', 'lines': self.joiner.take()})

    async def _send(self, payload: dict[str, Any]) -> None:
        try:
            async with self._send_lock:
                await self.websocket.send_text(json.dumps(payload, separators=(',', ':')))
        except (WebSocketDisconnect, RuntimeError):
            self.stop('client')


def _opus_decoder() -> Any:
    if opuslib is None:
        raise RuntimeError('Opus live words need opuslib and the native libopus library.')
    return opuslib.Decoder(SAMPLE_RATE, 1)


def device_key(websocket: WebSocket) -> str:
    """The app install behind this connection, as the listening connection names it; bounded."""
    headers = websocket.headers
    platform = (headers.get('x-app-platform') or 'unknown').strip().lower()[:16]
    install = (headers.get('x-device-id-hash') or 'unknown').strip().lower()[:64]
    return f'{platform}_{install}'


async def run_live_words(websocket: WebSocket, uid: str, *, language: str, sample_rate: int, codec: str) -> None:
    """The accepted-socket body of ``/v4/live-words``. Refuses before accepting when it cannot serve."""
    await reliability_experiments.warm(uid)
    if not reliability_experiments.enabled(EXPERIMENT, uid):
        raise WebSocketException(code=1008, reason='Live words are off')
    if codec not in CODECS or sample_rate != SAMPLE_RATE or (codec == 'opus' and opuslib is None):
        raise WebSocketException(code=1008, reason='Unsupported audio format')
    try:
        await websocket.accept()
    except RuntimeError as error:
        logger.error('live words accept failed uid=%s error_type=%s', uid, type(error).__name__)
        return
    await LiveWordsSession(websocket, uid, device_key(websocket), codec, language).run()
