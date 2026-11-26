"""Reliability experiment ``instant_live_text``: a batch-only phone session streams while it is watched.

A batch-only session archives its socket audio and opens no provider stream, so the phone shows nothing
until batch lands. With the experiment on, the moment this socket reports its transcript on screen
(``client_state`` with ``foreground`` and ``transcript_visible`` both true) the same audio is also sent
to Soniox, and the lines go to the phone. The stream closes on the first report that is not visible, on
a stale report, or at session end. There is no dwell.

The lines are display-only. They are sent on the socket in the ordinary live-segment format and are
never stored: they do not pass through the transcript processor, the conversation, its summary or the
v3 builder, and the session's provider selection is left alone. The record stays what batch makes of
the archived audio. Storing them was tried first and is wrong for a stream that covers only part of a
recording: the conversation was finalized and summarized from the fragment, and the batch projection
then kept those annotated lines and dropped the rest of its own text (local stack, 2026-11-25).

Custody is untouched and no failure here can end capture. Phone-file sessions (an admitted local
preview) never qualify: their audio is not on the socket.

Off, nothing is attached and every hook in the receiver is a no-op.
"""

import asyncio
import logging
import time
import uuid
from collections import deque
from typing import Any

from fastapi.websockets import WebSocketDisconnect
from prometheus_client import Counter

from config import reliability_experiments
from config.server_batch import owned
from models.transcript_segment import TranscriptSegment, transcript_segment_for_client
from routers.listen.demand_routing import DemandPolicy
from routers.listen.local_preview import batch_only_live_path
from utils.stt.live_failure import live_stt_socket_is_dead
from utils.stt.provider_stream_end import begin_stream_close
from utils.stt.replay_delivery import abort_replay_socket
from utils.stt.socket import release_live_stt_socket, track_live_stt_socket
from utils.stt.soniox import process_audio_soniox
from utils.stt.streaming import STTService

logger = logging.getLogger(__name__)

EXPERIMENT = 'instant_live_text'
SUPERSEDED_BY = 'vendor_recognizer_on_opened_app'
PROVIDER = STTService.soniox.value
# The app repeats its report every 60 s. A visible report older than this is not trusted to still be true.
STALE_REPORT_SECONDS = 150.0
DIAL_TIMEOUT_SECONDS = 10.0
# Audio that arrives while the provider is being dialled is kept and sent first, so the words spoken in
# that second are not lost. Bounded; older audio falls out (batch still has all of it).
DIAL_BUFFER_SECONDS = 5.0
# The last seconds before the page opened are kept too and sent first. A stream that starts in the middle
# of a sentence otherwise loses its first words (measured on the local stack: about 2 s), and the person
# opening the page sees the sentence in progress from its start. Costs about 32 KB per second for every
# session the rule admits, watched or not.
PRE_ROLL_SECONDS = 3.0
RETRY_SECONDS = 1.0
# Consecutive opens that died before any line arrived. After this many the stream stays closed until
# the page is closed and opened again.
MAX_FAILURES = 3
# The provider reports words. They are joined into one line per speaker turn, as the stored transcript is.
LINE_GAP_SECONDS = 3.0
LINE_MAX_CHARS = 600

OMI_LISTEN_WATCHED_STREAM_TOTAL = Counter(
    'omi_listen_watched_stream_total',
    'Provider streams opened for a watched batch-only phone session, by bounded outcome',
    ['outcome'],
)
OMI_LISTEN_WATCHED_STREAM_SECONDS_TOTAL = Counter(
    'omi_listen_watched_stream_seconds_total',
    'Seconds a watched batch-only phone session held a provider stream open',
)


def _uid(receiver: Any) -> str | None:
    """The session's account. On the event loop the first check for an account in a process reads off
    until its rules are learned on a worker thread; the checks here repeat on every client message and
    every second of the stream, so a session picks its rule up within moments."""
    uid = getattr(getattr(receiver.host, 'request', None), 'uid', None)
    return uid if isinstance(uid, str) and uid else None


def admitted(receiver: Any) -> bool:
    """Read per call: the experiment, the batch custody and the preview grant can all change mid-session."""
    host = receiver.host
    uid = _uid(receiver)
    return bool(
        reliability_experiments.enabled(EXPERIMENT, uid)
        # Under vendor_recognizer_on_opened_app the phone already has a display stream of its own
        # (routers/listen/live_words.py) on every screen; a second one here would bill the same audio twice.
        and not reliability_experiments.enabled(SUPERSEDED_BY, uid)
        and batch_only_live_path(host)
        and owned(getattr(host, 'batch_record_capture', None) or {})
        and getattr(getattr(host, 'client_device_context', None), 'platform', None) in {'ios', 'android'}
        # Granted, not merely asked for: a phone whose preview request was refused sends its audio here.
        and not getattr(host, 'local_preview_batch', False)
        and not getattr(host, 'use_custom_stt', False)
        and not getattr(host, 'is_multi_channel', False)
        and host.request.uid
    )


class WatchedStream:
    def __init__(self, receiver: Any):
        self.receiver = receiver
        self.policy = DemandPolicy()
        self.reported_at: float | None = None
        self.failed = False
        self.failures = 0
        self.socket: Any = None
        self.opened_at: float | None = None
        self.metered_at: float | None = None
        self.generation = 0
        self.opening: asyncio.Task[Any] | None = None
        self.next_open_at = 0.0
        self.retired: list[Any] = []
        # (pcm, wall-clock time its first sample was captured)
        self.pending: deque[tuple[bytes, float]] = deque()
        self.pending_bytes = 0
        # Wall-clock time of the first sample sent on the open stream: the provider's zero.
        self.stream_wall: float | None = None
        # The conversation the lines are timed against, and its start on the wall clock.
        self.conversation_id: str | None = None
        self.origin: float | None = None
        self.lines: list[dict[str, Any]] = []
        self.dirty: dict[str, dict[str, Any]] = {}
        self.sender: asyncio.Task[Any] | None = None
        self._drain_lock = asyncio.Lock()

    # --- what the phone says -------------------------------------------------------------------

    def observe(self, payload: Any) -> None:
        self.policy.observe(payload)
        self.reported_at = time.monotonic()
        if self.policy.state != 'visible':
            self.close()
            self.failed = False
            self.failures = 0
            return
        self._dial()  # No dwell: the page is open, start now rather than on the next audio.

    def visible(self) -> bool:
        return bool(
            self.policy.state == 'visible'
            and self.reported_at is not None
            and time.monotonic() - self.reported_at <= STALE_REPORT_SECONDS
            and self.receiver.host.state.active
            and admitted(self.receiver)
        )

    # --- provider stream -----------------------------------------------------------------------

    def _dial(self) -> None:
        if self.failed or self.socket is not None or not self.visible():
            return
        if (self.opening is None or self.opening.done()) and time.monotonic() >= self.next_open_at:
            self.next_open_at = time.monotonic() + RETRY_SECONDS
            self.opening = self.receiver.host.spawn(self._open_background(), name='watched_stream_open')

    async def _open_background(self) -> None:
        try:
            await self.open()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.warning('Watched stream open failed type=%s', type(error).__name__)
            self._lost()  # An optional stream cannot end capture.

    async def _conversation_origin(self, conversation_id: str | None) -> float | None:
        """Start of the in-progress conversation: the clock the phone places live lines on."""
        host = self.receiver.host
        try:
            cache = getattr(getattr(host, 'transcripts', None), 'cache', None)
            row = await cache.get(conversation_id) if cache is not None and conversation_id else None
            started = (row or {}).get('started_at')
            if started is not None:
                return started.timestamp()
        except Exception as error:
            logger.warning('Watched stream conversation read failed type=%s', type(error).__name__)
        return getattr(host.state, 'first_audio_byte_timestamp', None) or None

    async def open(self) -> bool:
        if not self.visible() or self.failed:
            return False
        generation = self.generation
        await self.drain()
        if self.socket is not None:
            return not live_stt_socket_is_dead(self.socket)
        host = self.receiver.host
        admission = getattr(self.receiver, 'cap_admission', None)
        if admission is not None:
            # A plan with no cloud recognition left gets no stream. The seconds are not metered against
            # the allowance: batch transcribes the same audio and already accounts for it.
            await admission.refresh(force=False)
            if not admission.allowed(STTService.soniox):
                return False
        conversation_id = getattr(host.state, 'current_conversation_id', None)
        origin = await self._conversation_origin(conversation_id)
        if generation != self.generation or not self.visible():
            return False

        def words(segments: list[dict[str, Any]]) -> None:
            if generation != self.generation or self.failed or not self.visible():
                return  # A late callback from a closed stream never reaches the phone.
            self.failures = 0
            self._words(segments)

        raw = None
        adopted = False
        try:
            # Same-task timeout keeps ownership of the candidate explicit on cancellation.
            async with asyncio.timeout(DIAL_TIMEOUT_SECONDS):
                raw = await process_audio_soniox(
                    words,
                    host.request.sample_rate,
                    host.stt_language,
                    profile=getattr(host, 'language_profile', None),
                    uid=host.request.uid,
                )
            if generation != self.generation or not self.visible():
                return False
            self.socket = track_live_stt_socket(raw, PROVIDER)
            self.stream_wall = None  # Pinned to the first frame actually forwarded.
            self.conversation_id, self.origin = conversation_id, origin
            self.lines = []
            adopted = True
            self.opened_at = self.metered_at = time.monotonic()
            OMI_LISTEN_WATCHED_STREAM_TOTAL.labels(outcome='opened').inc()
            logger.info('event=watched_stream action=open')
            return True
        finally:
            if raw is not None and not adopted:
                await abort_replay_socket(raw, timeout=2)

    def _meter(self) -> None:
        if self.metered_at is not None:
            now = time.monotonic()
            OMI_LISTEN_WATCHED_STREAM_SECONDS_TOTAL.inc(max(0.0, now - self.metered_at))
            self.metered_at = now

    def close(self) -> None:
        socket, self.socket = self.socket, None
        self.generation += 1
        self.stream_wall = None
        self.pending.clear()
        self.pending_bytes = 0
        self._meter()
        self.metered_at = None
        if self.opened_at is not None:
            logger.info('event=watched_stream action=close seconds=%.1f', time.monotonic() - self.opened_at)
            self.opened_at = None
        if socket is not None:
            self.retired.append(socket)
            try:
                begin_stream_close(socket)
                socket.finish()
            except Exception:
                pass  # Closing an optional stream cannot interrupt original-audio custody.
            finally:
                release_live_stt_socket(socket)

    def _lost(self) -> None:
        """The provider died or could not be reached: retry a few times, then stay closed until re-opened."""
        self.failures += 1
        self.close()
        if self.failures >= MAX_FAILURES and not self.failed:
            self.failed = True
            OMI_LISTEN_WATCHED_STREAM_TOTAL.labels(outcome='failed').inc()
        else:
            self.next_open_at = time.monotonic() + RETRY_SECONDS * self.failures

    async def drain(self) -> None:
        async with self._drain_lock:
            while self.retired:
                await abort_replay_socket(self.retired.pop(), timeout=2)

    async def shutdown(self) -> None:
        self.close()
        for task in (self.opening, self.sender):
            if task is not None and task is not asyncio.current_task():
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        self.opening = self.sender = None
        await self.drain()

    # --- lines to the phone --------------------------------------------------------------------

    def _words(self, segments: list[dict[str, Any]]) -> None:
        """Join the provider's words into lines and queue the changed ones for the phone."""
        if self.stream_wall is None:
            return
        base = self.stream_wall - (self.origin if self.origin is not None else self.stream_wall)
        for segment in segments:
            text = str(segment.get('text') or '').strip()
            if not text:
                continue
            start = max(0.0, base + float(segment.get('start') or 0.0))
            end = max(start, base + float(segment.get('end') or 0.0))
            speaker = str(segment.get('speaker') or 'SPEAKER_00')
            line = self.lines[-1] if self.lines else None
            if (
                line is None
                or line['speaker'] != speaker
                or start - line['end'] >= LINE_GAP_SECONDS
                or len(line['text']) + len(text) > LINE_MAX_CHARS
            ):
                line = {'id': uuid.uuid4().hex, 'speaker': speaker, 'start': start, 'end': end, 'text': text}
                self.lines.append(line)
            else:
                line['text'] = ' '.join((line['text'], text))
                line['end'] = max(line['end'], end)
            self.dirty[line['id']] = line
        if self.dirty and (self.sender is None or self.sender.done()):
            self.sender = self.receiver.host.spawn(self._send_lines(), name='watched_stream_lines')

    async def _send_lines(self) -> None:
        """One sender at a time, so a line's later text can never overtake its earlier text."""
        websocket = self.receiver.host.request.websocket
        while self.dirty and self.receiver.host.state.active:
            changed, self.dirty = list(self.dirty.values()), {}
            payload = []
            for line in changed:
                try:
                    speaker_id = int(line['speaker'].rsplit('_', 1)[-1])
                except ValueError:
                    speaker_id = 0
                segment = TranscriptSegment(
                    id=line['id'],
                    text=line['text'],
                    speaker=line['speaker'],
                    speaker_id=speaker_id,
                    is_user=False,
                    start=line['start'],
                    end=line['end'],
                    stt_provider=PROVIDER,
                )
                payload.append(transcript_segment_for_client(segment.model_dump()))
            try:
                await websocket.send_json(payload)
            except (WebSocketDisconnect, RuntimeError):
                return  # The phone has gone; the session's own teardown handles that.

    # --- audio ---------------------------------------------------------------------------------

    def _hold(self, pcm: bytes, captured_at: float, seconds: float) -> None:
        self.pending.append((pcm, captured_at))
        self.pending_bytes += len(pcm)
        limit = int(seconds * self.receiver.host.request.sample_rate) * 2
        while self.pending_bytes > limit and len(self.pending) > 1:
            self.pending_bytes -= len(self.pending.popleft()[0])

    def _send(self, pcm: bytes, captured_at: float) -> bool:
        if self.stream_wall is None:
            self.stream_wall = captured_at
        return self.socket.send(pcm) is not False

    async def flush(self, buffer: bytearray) -> None:
        """Called for every decoded buffer of a batch-only session. Never awaits a provider dial."""
        receiver = self.receiver
        try:
            captured_at = time.time() - len(buffer) / (2 * receiver.host.request.sample_rate)
            if not self.visible():
                if self.socket is not None:
                    self.close()
                if buffer and not self.failed and admitted(receiver):
                    self._hold(bytes(buffer), captured_at, PRE_ROLL_SECONDS)
                elif self.pending:
                    self.pending.clear()
                    self.pending_bytes = 0
                return
            if not buffer or self.failed:
                return
            if self.socket is not None and self.conversation_id != getattr(
                receiver.host.state, 'current_conversation_id', None
            ):
                self.close()  # A new conversation has its own clock; reopen against it.
                self.next_open_at = 0.0
            if self.socket is None:
                self._hold(bytes(buffer), captured_at, PRE_ROLL_SECONDS + DIAL_BUFFER_SECONDS)
                self._dial()
                return
            if live_stt_socket_is_dead(self.socket):
                self._lost()
                return
            while self.pending:
                held, held_at = self.pending.popleft()
                self.pending_bytes -= len(held)
                if not self._send(held, held_at):
                    self._lost()
                    return
            if not self._send(bytes(buffer), captured_at):
                self._lost()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.warning('Watched stream send failed type=%s', type(error).__name__)
            self._lost()
        finally:
            buffer.clear()
            receiver._stt_buffer_start_sample = None

    async def run(self) -> None:
        try:
            while self.receiver.host.state.active:
                if self.socket is not None:
                    if live_stt_socket_is_dead(self.socket):
                        self._lost()
                    elif not self.visible():
                        self.close()
                    else:
                        self._meter()
                await self.drain()
                if await self.receiver.host.wait(1):
                    return
        finally:
            await self.shutdown()


def attach_watched_stream(receiver: Any) -> None:
    """Idempotent. Attached only to a session that is batch-only now, with the experiment on."""
    if getattr(receiver, 'watched_stream', None) is not None:
        return
    if not reliability_experiments.enabled(EXPERIMENT, _uid(receiver)) or not batch_only_live_path(receiver.host):
        return
    watched = receiver.watched_stream = WatchedStream(receiver)
    receiver.host.task_supervisor.create_lifetime_task(watched.run(), name='watched_stream')
    # The app reports on connect, which can land before this session is known to be batch-only.
    last = getattr(receiver, '_watched_last_state', None)
    if last is not None:
        watched.observe(last)


def observe_client_state(receiver: Any, payload: Any) -> None:
    """Every ``client_state`` message. Off, it keeps nothing and does nothing."""
    if not reliability_experiments.enabled(EXPERIMENT, _uid(receiver)):
        return
    receiver._watched_last_state = payload
    watched = getattr(receiver, 'watched_stream', None)
    if watched is not None:
        watched.observe(payload)
