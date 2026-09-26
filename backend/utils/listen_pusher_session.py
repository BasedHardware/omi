import asyncio
import json
import logging
import random
import struct
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, cast, Deque, Dict, List, Optional, Tuple, TYPE_CHECKING

from websockets.exceptions import ConnectionClosed

if TYPE_CHECKING:
    from websockets.legacy.client import WebSocketClientProtocol
else:
    WebSocketClientProtocol = Any

from utils.metrics import PUSHER_CIRCUIT_BREAKER_REJECTIONS, PUSHER_SESSION_DEGRADED
from utils.pusher import PusherCircuitBreakerOpen, connect_to_trigger_pusher
from utils.pusher_protocol import (
    AUDIO_TIMELINE_PROTOCOL,
    PUSHER_AUDIO_TIMELINE_ACK_OPCODE,
)

# Typed wrapper because utils.pusher.connect_to_trigger_pusher uses the untyped
# `callable` builtin as a parameter annotation; cast to the proper signature.
_connect_to_trigger_pusher: Callable[..., Awaitable[Optional[WebSocketClientProtocol]]] = cast(
    "Callable[..., Awaitable[Optional[WebSocketClientProtocol]]]", connect_to_trigger_pusher
)


logger = logging.getLogger(__name__)

TARGET_SAMPLE_RATE = 16000

# Two buffered runs belong to one opcode-101 frame only when their projected
# positions are contiguous within 1 ms. A wider positive gap (a client stall
# that minted a new capture anchor, or a withheld-then-resumed window) must
# flush a separate frame: concatenating the bytes would delete the gap from
# the stored audio while the header still claims the first run's start.
AUDIO_RUN_GAP_TOLERANCE_SECONDS = 0.001


class PusherReconnectState(str, Enum):
    CONNECTED = 'connected'
    RECONNECT_BACKOFF = 'reconnect_backoff'
    DEGRADED = 'degraded'
    HALF_OPEN_PROBE = 'half_open_probe'


PUSHER_MAX_RECONNECT_ATTEMPTS = 6
PUSHER_DEGRADED_COOLDOWN = 60.0
PUSHER_RECONNECT_BASE_DELAY = 1.0
PUSHER_RECONNECT_MAX_DELAY = 60.0
PENDING_REQUEST_TIMEOUT = 120
MAX_RETRIES_PER_REQUEST = 3
PENDING_REQUEST_RECOVERY_COOLDOWN = 300
# Wire contract with utils.pusher_finalization: a claim rejected because a live
# lease is already finalizing this job reports the non-terminal `job_leased`
# error. That is healthy in-flight work, not a failed attempt.
FINALIZATION_IN_FLIGHT_ERROR = 'job_leased'
# Advertise the generation-aware opcode-201 result handling capability. A
# pusher only sends generation-aware stale responses after seeing this value.
FINALIZATION_RESULT_PROTOCOL = 2
FINALIZATION_STALE_GENERATION_ERROR = 'job_stale_generation'
# How long a v2-opted-in listen waits for the pusher's audio-timeline
# acknowledgment after connect. A pusher that stays silent is an old pusher:
# the session falls back to v1 audio (before any v2 capture is committed) or
# suspends v2 audio (mid-recording capability loss) — never blind v2.
AUDIO_TIMELINE_ACK_TIMEOUT_SECONDS = 4.0


@dataclass
class ListenPusherSessionConfig:
    uid: str
    session_id: str
    sample_rate: int
    is_multi_channel: bool
    language: str
    audio_bytes_enabled: bool
    max_segment_buffer_size: int
    max_audio_buffer_size: int
    max_pending_requests: int
    max_pending_speaker_sample_requests: int
    client_kind: str = 'unknown'
    # Opt this session into audio-timeline v2 (AUDIO_TIMELINE_V2 at the call
    # boundary). The pusher must acknowledge capability before v2 audio is sent.
    audio_timeline_v2: bool = False


@dataclass
class AudioRun:
    """One retained contiguous buffered audio run.

    The conversation binding and the projected start of the run's first sample
    are captured at acceptance time and travel with the bytes through replays
    and reconnects; they are never recomputed from a later arrival.
    """

    conversation_id: Optional[str]
    start_wall: Optional[float]
    data: bytes


@dataclass
class ListenPusherSessionDeps:
    get_current_conversation_id: Callable[[], Optional[str]]
    is_active: Callable[[], bool]
    shutdown_event: asyncio.Event
    get_byok_keys: Callable[[], Dict[str, Any]]
    on_conversation_processed: Callable[[str], None]
    wait_for_event: Callable[[asyncio.Event, float], Awaitable[bool]]
    connect_to_pusher: Callable[..., Awaitable[Optional[WebSocketClientProtocol]]] = _connect_to_trigger_pusher
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    random: Callable[[], float] = random.random
    now: Callable[[], float] = time.time
    monotonic: Callable[[], float] = time.monotonic


class ListenPusherSession:
    def __init__(self, config: ListenPusherSessionConfig, deps: ListenPusherSessionDeps):
        self.config = config
        self.deps = deps
        self.pusher_ws: Optional[WebSocketClientProtocol] = None
        self.pusher_connect_lock = asyncio.Lock()
        self.transcript_flush_lock = asyncio.Lock()
        self.audio_flush_lock = asyncio.Lock()
        self.pusher_connected = False
        self.reconnect_state = PusherReconnectState.CONNECTED
        self.reconnect_attempts = 0
        self.reconnect_task: Optional[asyncio.Task[None]] = None
        self.degraded_since: float = 0.0
        self.segment_buffers: Deque[Dict[str, Any]] = deque(maxlen=config.max_segment_buffer_size)
        self.last_synced_conversation_id: Optional[str] = None
        self.pending_conversation_requests: Dict[str, Dict[str, Any]] = {}
        self.pending_request_event = asyncio.Event()
        self.pending_speaker_sample_requests: Deque[Tuple[str, str, List[str]]] = deque(
            maxlen=config.max_pending_speaker_sample_requests
        )
        self.audio_runs: Deque[AudioRun] = deque()
        self.audio_total_size = 0
        self.audio_buffer_last_received: Optional[float] = None
        # Audio-timeline v2 handshake state. ``audio_timeline_active`` means a
        # pusher acknowledged v2 on this or a previous connection of this
        # session; ``audio_timeline_suspended`` means an active v2 recording
        # lost the capable pusher: audio is withheld (a coverage gap), never
        # silently downgraded and never used to terminate the recording.
        self.audio_timeline_active = False
        self.audio_timeline_suspended = False

    @property
    def uid(self):
        return self.config.uid

    @property
    def session_id(self):
        return self.config.session_id

    def transcript_send(self, segments: List[Dict[str, Any]]) -> None:
        self.segment_buffers.extend(segments)

    def _buffer_pending_conversation_request(
        self,
        conversation_id: str,
        *,
        finalization_job_id: Optional[str] = None,
        dispatch_generation: Optional[int] = None,
    ):
        existing = self.pending_conversation_requests.get(conversation_id)
        if existing is None and len(self.pending_conversation_requests) >= self.config.max_pending_requests:
            oldest_id = min(
                self.pending_conversation_requests,
                key=lambda k: self.pending_conversation_requests[k]['sent_at'],
            )
            logger.info(
                f"Too many pending requests, dropping {oldest_id} to add {conversation_id} {self.uid} {self.session_id}"
            )
            del self.pending_conversation_requests[oldest_id]
            existing = None
        self.pending_conversation_requests[conversation_id] = {
            'sent_at': self.deps.now(),
            'retries': (existing or {}).get('retries', 0),
            'finalization_job_id': finalization_job_id or (existing or {}).get('finalization_job_id'),
            'dispatch_generation': dispatch_generation or (existing or {}).get('dispatch_generation'),
        }
        self.pending_request_event.set()

    async def request_conversation_processing(
        self,
        conversation_id: str,
        finalization_job_id: Optional[str] = None,
        dispatch_generation: Optional[int] = None,
    ):
        """Request pusher to process a conversation through its durable lease."""
        if not self.pusher_connected or not self.pusher_ws:
            logger.info(
                f"Pusher not connected for {conversation_id}, will retry on reconnect {self.uid} {self.session_id}"
            )
            self._buffer_pending_conversation_request(
                conversation_id,
                finalization_job_id=finalization_job_id,
                dispatch_generation=dispatch_generation,
            )
            return False
        try:
            self._buffer_pending_conversation_request(
                conversation_id,
                finalization_job_id=finalization_job_id,
                dispatch_generation=dispatch_generation,
            )
            pending = self.pending_conversation_requests[conversation_id]
            data = bytearray()
            data.extend(struct.pack("I", 104))
            payload: Dict[str, Any] = {
                "conversation_id": conversation_id,
                "language": self.config.language,
                "byok_keys": self.deps.get_byok_keys(),
            }
            if pending.get('finalization_job_id'):
                payload['finalization_job_id'] = pending['finalization_job_id']
                payload['dispatch_generation'] = pending.get('dispatch_generation') or 1
                payload['finalization_result_protocol'] = FINALIZATION_RESULT_PROTOCOL
            data.extend(bytes(json.dumps(payload), "utf-8"))
            await self.pusher_ws.send(cast(bytes, data))
            logger.info(f"Sent process_conversation request to pusher: {conversation_id} {self.uid} {self.session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send process_conversation request: {e} {self.uid} {self.session_id}")
            return False

    async def _transcript_flush(self):
        async with self.transcript_flush_lock:
            if self.pusher_connected and self.pusher_ws and len(self.segment_buffers) > 0:
                pending_segments = self.segment_buffers
                self.segment_buffers = deque(maxlen=self.config.max_segment_buffer_size)
                try:
                    data = bytearray()
                    data.extend(struct.pack("I", 102))
                    data.extend(
                        bytes(
                            json.dumps(
                                {
                                    "segments": list(pending_segments),
                                    "memory_id": self.deps.get_current_conversation_id(),
                                }
                            ),
                            "utf-8",
                        )
                    )
                    await self.pusher_ws.send(cast(bytes, data))
                except (asyncio.CancelledError, Exception) as e:
                    self.segment_buffers = deque(
                        (*pending_segments, *self.segment_buffers), maxlen=self.config.max_segment_buffer_size
                    )
                    if isinstance(e, asyncio.CancelledError):
                        raise
                    elif isinstance(e, ConnectionClosed):
                        logger.error(f"Pusher transcripts Connection closed: {e} {self.uid} {self.session_id}")
                        self._mark_disconnected()
                    else:
                        logger.error(f"Pusher transcripts failed: {e} {self.uid} {self.session_id}")

    async def transcript_consume(self):
        while self.deps.is_active():
            await self.deps.sleep(1)
            if len(self.segment_buffers) > 0:
                await self._transcript_flush()

    def audio_bytes_send(
        self,
        audio_bytes: bytes,
        received_at: float,
        *,
        conversation_id: Optional[str] = None,
        start_wall: Optional[float] = None,
    ):
        """Buffer one accepted audio run with its binding and projected start.

        The conversation id and the capture-projected wall time of the run's
        first sample are stored at acceptance time, so audio is never bound to
        whatever conversation happens to be current a second later, and a
        replayed or reconnected run keeps its original position. A clipped
        dropped prefix shifts the retained start by exactly the samples kept.
        """
        chunk = audio_bytes
        chunk_start_wall = start_wall
        if len(chunk) > self.config.max_audio_buffer_size:
            dropped = len(chunk) - self.config.max_audio_buffer_size
            chunk = chunk[-self.config.max_audio_buffer_size :]
            if chunk_start_wall is not None:
                rate = TARGET_SAMPLE_RATE if self.config.is_multi_channel else self.config.sample_rate
                chunk_start_wall += dropped / (rate * 2)
        while self.audio_total_size + len(chunk) > self.config.max_audio_buffer_size and self.audio_runs:
            old = self.audio_runs.popleft()
            self.audio_total_size -= len(old.data)
        self.audio_runs.append(AudioRun(conversation_id=conversation_id, start_wall=chunk_start_wall, data=chunk))
        self.audio_total_size += len(chunk)
        self.audio_buffer_last_received = received_at

    async def _audio_bytes_flush(self):
        async with self.audio_flush_lock:
            current_conversation_id = self.deps.get_current_conversation_id()
            pusher_ws = self.pusher_ws
            if not (self.pusher_connected and pusher_ws):
                return
            if self.audio_timeline_suspended and self.audio_total_size > 0:
                # Capability loss mid-v2-recording: keep the recording alive
                # and keep buffering, but withhold audio (a coverage gap)
                # rather than emitting falsely positioned legacy frames.
                return
            pending_runs = self.audio_runs
            pending_total_size = self.audio_total_size
            self.audio_runs = deque()
            self.audio_total_size = 0
            sent_runs = 0
            try:
                effective_rate = TARGET_SAMPLE_RATE if self.config.is_multi_channel else self.config.sample_rate
                # Send one 101 frame per contiguous same-conversation run.
                # Pending runs are attributed to the conversation bound at
                # their acceptance time (falling back to the current one for
                # legacy runs), so a rollover's buffered tail can never be
                # re-bound to the newer conversation; opcode 103 is emitted
                # ahead of each conversation boundary so the pusher flushes
                # its buffers instead of concatenating across rollovers. The
                # header timestamp is the run's retained projected start when
                # the capture timeline supplied one, and the legacy
                # last-arrival-minus-duration estimate otherwise.
                group: List[AudioRun] = []
                group_conversation: Optional[str] = None

                def frame_header_time(runs: List[AudioRun]) -> Optional[float]:
                    if runs and runs[0].start_wall is not None:
                        return runs[0].start_wall
                    duration = pending_total_size / (effective_rate * 2)
                    return (self.audio_buffer_last_received or self.deps.now()) - duration

                def runs_are_contiguous(prev: AudioRun, nxt: AudioRun) -> bool:
                    # Legacy runs carry no projection; keep the legacy
                    # grouping for them.
                    if prev.start_wall is None or nxt.start_wall is None:
                        return True
                    projected_prev_end = prev.start_wall + len(prev.data) / (effective_rate * 2)
                    return nxt.start_wall - projected_prev_end <= AUDIO_RUN_GAP_TOLERANCE_SECONDS

                async def send_group(runs: List[AudioRun]) -> None:
                    nonlocal sent_runs
                    if not runs:
                        return
                    conversation = runs[0].conversation_id or current_conversation_id
                    if conversation and conversation != self.last_synced_conversation_id:
                        header = bytearray()
                        header.extend(struct.pack("I", 103))
                        header.extend(bytes(conversation, "utf-8"))
                        await pusher_ws.send(cast(bytes, header))
                        self.last_synced_conversation_id = conversation
                    audio_data = b''.join(run.data for run in runs)
                    data = bytearray()
                    data.extend(struct.pack("I", 101))
                    data.extend(struct.pack("d", frame_header_time(runs)))
                    data.extend(audio_data)
                    del audio_data
                    await pusher_ws.send(cast(bytes, data))
                    sent_runs += len(runs)

                for run in pending_runs:
                    run_conversation = run.conversation_id or current_conversation_id
                    if group and (run_conversation != group_conversation or not runs_are_contiguous(group[-1], run)):
                        await send_group(group)
                        group = []
                    group.append(run)
                    group_conversation = run_conversation
                await send_group(group)
                if current_conversation_id and current_conversation_id != self.last_synced_conversation_id:
                    # Standalone announcement when no run carried the current
                    # conversation yet (legacy sessions with no buffered audio,
                    # or after every buffered rollover tail was flushed).
                    data = bytearray()
                    data.extend(struct.pack("I", 103))
                    data.extend(bytes(current_conversation_id, "utf-8"))
                    await pusher_ws.send(cast(bytes, data))
                    self.last_synced_conversation_id = current_conversation_id
            except (asyncio.CancelledError, Exception) as e:
                unsent = list(pending_runs)[sent_runs:]
                self.audio_runs.extendleft(reversed(unsent))
                self.audio_total_size += sum(len(run.data) for run in unsent)
                while self.audio_total_size > self.config.max_audio_buffer_size and self.audio_runs:
                    self.audio_total_size -= len(self.audio_runs.popleft().data)
                if isinstance(e, asyncio.CancelledError):
                    raise
                elif isinstance(e, ConnectionClosed):
                    logger.error(f"Pusher audio_bytes Connection closed: {e} {self.uid} {self.session_id}")
                    self._mark_disconnected()
                else:
                    logger.error(f"Pusher audio_bytes failed: {e} {self.uid} {self.session_id}")

    async def audio_bytes_consume(self):
        while self.deps.is_active():
            await self.deps.sleep(1)
            if self.audio_total_size > 0:
                await self._audio_bytes_flush()

    async def pusher_receive(self):
        """Receive and handle messages from pusher, with timeout-based retry for pending requests."""
        while self.deps.is_active():
            if not self.pending_conversation_requests:
                self.pending_request_event.clear()
                try:
                    await asyncio.wait_for(self.pending_request_event.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    continue

            if not self.pusher_connected or not self.pusher_ws:
                await self.deps.sleep(0.5)
                continue

            try:
                msg = cast(bytes, await asyncio.wait_for(self.pusher_ws.recv(), timeout=5.0))
                if not msg or len(msg) < 4:
                    continue
                header_type = struct.unpack('<I', msg[:4])[0]

                if header_type == 201:
                    result = json.loads(msg[4:].decode("utf-8"))
                    conversation_id = result.get("conversation_id")

                    if "error" in result:
                        if result.get("error") == FINALIZATION_STALE_GENERATION_ERROR:
                            # A delayed stale response must not delete a newer
                            # request for this conversation. Only drop when the
                            # response identifies the generation still pending.
                            pending = self.pending_conversation_requests.get(conversation_id)
                            rejected_generation = result.get("dispatch_generation")
                            pending_generation = (
                                (pending.get('dispatch_generation') or 1) if pending is not None else None
                            )
                            if (
                                pending is not None
                                and isinstance(rejected_generation, int)
                                and not isinstance(rejected_generation, bool)
                                and pending_generation == rejected_generation
                            ):
                                self.pending_conversation_requests.pop(conversation_id, None)
                                logger.info(
                                    'Conversation finalization superseded by durable replay '
                                    'conversation=%s dispatch_generation=%s uid=%s session=%s',
                                    conversation_id,
                                    rejected_generation,
                                    self.uid,
                                    self.session_id,
                                )
                            else:
                                logger.info(
                                    'Ignoring delayed stale finalization response '
                                    'conversation=%s rejected_generation=%s pending_generation=%s uid=%s session=%s',
                                    conversation_id,
                                    rejected_generation,
                                    pending_generation,
                                    self.uid,
                                    self.session_id,
                                )
                        elif result.get("terminal"):
                            # The job reached its attempt budget and is now
                            # dead-lettered. Retrying it would never converge.
                            self.pending_conversation_requests.pop(conversation_id, None)
                            logger.error(
                                f"Conversation processing failed terminally: {conversation_id} {self.uid} {self.session_id}"
                            )
                        elif result.get("error") == FINALIZATION_IN_FLIGHT_ERROR:
                            # Another dispatch of this same job holds a live lease
                            # and is finalizing right now. Re-requesting it can only
                            # be rejected again, so leave the pending entry on its
                            # normal timeout instead of spending the session's whole
                            # retry burst against healthy work.
                            logger.info(
                                f"Conversation finalization already in flight: {conversation_id} {self.uid} {self.session_id}"
                            )
                        else:
                            pending = self.pending_conversation_requests.get(conversation_id)
                            if pending is not None:
                                # The pusher has released its durable lease back to
                                # queued. Keep the request so this live session can
                                # reclaim it instead of stranding `processing`.
                                pending['sent_at'] = self.deps.now() - PENDING_REQUEST_TIMEOUT - 1
                            # The pusher released its durable lease back to queued
                            # and the pending entry stays armed for bounded retry —
                            # this is in-flight work with a live recovery path, not
                            # a server fault. The terminal dead-lettering above is
                            # the fault signal and stays at ERROR.
                            logger.warning(f"Conversation processing failed: {self.uid} {self.session_id}")
                    elif result.get('fenced'):
                        self.pending_conversation_requests.pop(conversation_id, None)
                        logger.info(
                            'Conversation finalization fenced by durable lifecycle conversation=%s uid=%s session=%s',
                            conversation_id,
                            self.uid,
                            self.session_id,
                        )
                    elif result.get("success"):
                        self.pending_conversation_requests.pop(conversation_id, None)
                        logger.info(f"Conversation processed by pusher: {conversation_id} {self.uid} {self.session_id}")
                        self.deps.on_conversation_processed(conversation_id)
                    else:
                        pending = self.pending_conversation_requests.get(conversation_id)
                        if pending is not None:
                            pending['sent_at'] = self.deps.now() - PENDING_REQUEST_TIMEOUT - 1
                        logger.warning(
                            f"Conversation processing returned no terminal result: {conversation_id} {self.uid} {self.session_id}"
                        )

            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                break
            except ConnectionClosed as e:
                logger.error(f"Pusher receive connection closed: {e} {self.uid} {self.session_id}")
                self._mark_disconnected()
            except Exception as e:
                logger.error(f"Pusher receive error: {e} {self.uid} {self.session_id}")
                await self.deps.sleep(0.5)

            now = self.deps.now()
            timed_out = [
                cid
                for cid, info in list(self.pending_conversation_requests.items())
                if now - info['sent_at'] > PENDING_REQUEST_TIMEOUT
            ]
            for cid in timed_out:
                info = self.pending_conversation_requests.get(cid)
                if not info:
                    continue
                if info['retries'] >= MAX_RETRIES_PER_REQUEST:
                    logger.warning(
                        f"Conversation {cid} retry burst exhausted; scheduling recovery cooldown {self.uid} {self.session_id}"
                    )
                    # Continue in bounded bursts rather than permanently
                    # dropping a queued durable finalization after one live
                    # session's transient provider failures.
                    info['retries'] = 0
                    info['sent_at'] = now + PENDING_REQUEST_RECOVERY_COOLDOWN - PENDING_REQUEST_TIMEOUT
                    continue
                info['retries'] += 1
                logger.warning(
                    f"Retrying process_conversation for {cid} (attempt {info['retries']}/{MAX_RETRIES_PER_REQUEST}) {self.uid} {self.session_id}"
                )
                await self.request_conversation_processing(
                    cid,
                    info.get('finalization_job_id'),
                    info.get('dispatch_generation'),
                )

    async def _flush(self):
        await self._audio_bytes_flush()
        await self._transcript_flush()

    def _mark_disconnected(self):
        """Signal pusher disconnection and ensure one reconnect loop is running."""
        if not self.pusher_connected:
            return
        self.pusher_connected = False
        if self.reconnect_state == PusherReconnectState.CONNECTED:
            self.reconnect_state = PusherReconnectState.RECONNECT_BACKOFF
            logger.info(f"Pusher disconnected, entering RECONNECT_BACKOFF {self.uid} {self.session_id}")
        if self.reconnect_task is None or self.reconnect_task.done():
            self.reconnect_task = asyncio.create_task(self._pusher_reconnect_loop())

    async def _pusher_reconnect_loop(self):
        """Single reconnect loop per session."""
        logger.info(f"Pusher reconnect loop started {self.uid} {self.session_id}")
        PUSHER_SESSION_DEGRADED.inc()
        try:
            while self.deps.is_active() and not self.pusher_connected:
                if self.reconnect_state == PusherReconnectState.RECONNECT_BACKOFF:
                    if self.reconnect_attempts >= PUSHER_MAX_RECONNECT_ATTEMPTS:
                        self.reconnect_state = PusherReconnectState.DEGRADED
                        self.degraded_since = self.deps.monotonic()
                        self.reconnect_attempts = 0
                        logger.warning(
                            f"Pusher reconnect exhausted ({PUSHER_MAX_RECONNECT_ATTEMPTS} attempts), "
                            f"entering DEGRADED mode {self.uid} {self.session_id}"
                        )
                        if self.pending_conversation_requests:
                            logger.info(
                                f"Keeping {len(self.pending_conversation_requests)} conversations buffered for pusher recovery {self.uid} {self.session_id}"
                            )
                        continue

                    delay = min(
                        PUSHER_RECONNECT_BASE_DELAY * (2**self.reconnect_attempts),
                        PUSHER_RECONNECT_MAX_DELAY,
                    )
                    delay *= 0.75 + self.deps.random() * 0.5
                    logger.info(
                        f"Pusher reconnect attempt {self.reconnect_attempts + 1}/{PUSHER_MAX_RECONNECT_ATTEMPTS}, "
                        f"waiting {delay:.1f}s {self.uid} {self.session_id}"
                    )
                    if await self.deps.wait_for_event(self.deps.shutdown_event, delay):
                        break

                    try:
                        await self.connect()
                        if self.pusher_connected:
                            self.reconnect_state = PusherReconnectState.CONNECTED
                            self.reconnect_attempts = 0
                            logger.info(f"Pusher reconnected successfully {self.uid} {self.session_id}")
                            break
                    except PusherCircuitBreakerOpen:
                        PUSHER_CIRCUIT_BREAKER_REJECTIONS.inc()
                        self.reconnect_state = PusherReconnectState.DEGRADED
                        self.degraded_since = self.deps.monotonic()
                        self.reconnect_attempts = 0
                        logger.warning(f"Circuit breaker open, skipping to DEGRADED {self.uid} {self.session_id}")
                        continue
                    except Exception:
                        pass

                    self.reconnect_attempts += 1

                elif self.reconnect_state == PusherReconnectState.DEGRADED:
                    elapsed = self.deps.monotonic() - self.degraded_since
                    remaining = PUSHER_DEGRADED_COOLDOWN - elapsed
                    if remaining > 0:
                        if await self.deps.wait_for_event(self.deps.shutdown_event, min(remaining, 5.0)):
                            break
                        continue
                    self.reconnect_state = PusherReconnectState.HALF_OPEN_PROBE
                    logger.info(f"Pusher DEGRADED cooldown elapsed, probing {self.uid} {self.session_id}")

                elif self.reconnect_state == PusherReconnectState.HALF_OPEN_PROBE:
                    try:
                        await self.connect()
                        if self.pusher_connected:
                            self.reconnect_state = PusherReconnectState.CONNECTED
                            self.reconnect_attempts = 0
                            logger.info(f"Pusher probe succeeded, back to CONNECTED {self.uid} {self.session_id}")
                            break
                    except PusherCircuitBreakerOpen:
                        PUSHER_CIRCUIT_BREAKER_REJECTIONS.inc()
                    except Exception:
                        pass
                    self.reconnect_state = PusherReconnectState.DEGRADED
                    self.degraded_since = self.deps.monotonic()
                    logger.warning(f"Pusher probe failed, back to DEGRADED {self.uid} {self.session_id}")

                else:
                    break
        finally:
            PUSHER_SESSION_DEGRADED.dec()
            logger.info(
                f"Pusher reconnect loop ended (state={self.reconnect_state.value}) {self.uid} {self.session_id}"
            )

    async def connect(self):
        async with self.pusher_connect_lock:
            if self.pusher_connected:
                return
            if self.pusher_ws:
                try:
                    await self.pusher_ws.close()
                    self.pusher_ws = None
                except Exception as e:
                    logger.error(f"Pusher draining failed: {e} {self.uid} {self.session_id}")
            await self._connect()

    async def _await_audio_timeline_ack(self) -> bool:
        """Wait for the pusher's v2 acknowledgment on a fresh connection.

        Must run before ``pusher_connected`` flips and before the ordinary
        ``pusher_receive`` task starts, so this coroutine is the only reader.
        An old pusher ignores the unknown ``audio_timeline`` query parameter
        and stays silent: the bounded timeout below then means v1.
        """
        pusher_ws = self.pusher_ws
        if pusher_ws is None:
            return False
        deadline = self.deps.monotonic() + AUDIO_TIMELINE_ACK_TIMEOUT_SECONDS
        while True:
            remaining = deadline - self.deps.monotonic()
            if remaining <= 0:
                return False
            try:
                message = await asyncio.wait_for(pusher_ws.recv(), timeout=remaining)
            except (asyncio.TimeoutError, ConnectionClosed, asyncio.CancelledError):
                return False
            except Exception as e:
                logger.warning(f"Audio timeline ack read failed: {e} {self.uid} {self.session_id}")
                return False
            if not isinstance(message, bytes) or len(message) < 4:
                continue
            if struct.unpack('<I', message[:4])[0] != PUSHER_AUDIO_TIMELINE_ACK_OPCODE:
                continue
            try:
                payload = json.loads(message[4:].decode('utf-8'))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return False
            if not isinstance(payload, dict):
                return False
            if payload.get('type') != 'audio_timeline_ack':
                return False
            version = payload.get('version')
            if isinstance(version, bool) or not isinstance(version, int) or version < AUDIO_TIMELINE_PROTOCOL:
                logger.warning(f"Pusher audio timeline ack version unsupported: {version} {self.uid} {self.session_id}")
                return False
            return True

    async def _connect(self):
        try:
            pusher_sample_rate = TARGET_SAMPLE_RATE if self.config.is_multi_channel else self.config.sample_rate
            connect_kwargs: Dict[str, Any] = {
                'retries': 5,
                'is_active': self.deps.is_active,
                'client_kind': self.config.client_kind,
            }
            if self.config.audio_timeline_v2:
                connect_kwargs['audio_timeline'] = AUDIO_TIMELINE_PROTOCOL
            self.pusher_ws = await self.deps.connect_to_pusher(self.uid, pusher_sample_rate, **connect_kwargs)
            if self.pusher_ws is None:
                return
            if self.config.audio_timeline_v2:
                # Capability gated per socket: an explicit acknowledgment is
                # required before any v2 audio is committed, and again on
                # every reconnect of a v2 session.
                if await self._await_audio_timeline_ack():
                    self.audio_timeline_active = True
                    if self.audio_timeline_suspended:
                        logger.info(f"Capable pusher recovered; v2 audio resumed {self.uid} {self.session_id}")
                    self.audio_timeline_suspended = False
                elif self.audio_timeline_active:
                    # A live v2 recording lost its capable pusher. Keep the
                    # recording and this connection (transcripts and
                    # finalization still flow); withhold the audio, which
                    # records as a coverage gap, and never terminate the
                    # recording or silently downgrade to v1 positions.
                    self.audio_timeline_suspended = True
                    logger.warning(
                        f"Pusher lost audio-timeline capability mid-v2-recording; "
                        f"audio withheld as coverage gap {self.uid} {self.session_id}"
                    )
                else:
                    logger.info(
                        f"Pusher did not acknowledge audio timeline v2; using v1 audio {self.uid} {self.session_id}"
                    )
            self.pusher_connected = True
            self.reconnect_state = PusherReconnectState.CONNECTED
            self.reconnect_attempts = 0
            if self.pending_conversation_requests:
                logger.info(
                    f"Reconnected to pusher, re-sending {len(self.pending_conversation_requests)} pending requests {self.uid} {self.session_id}"
                )
                for cid in list(self.pending_conversation_requests.keys()):
                    pending = self.pending_conversation_requests[cid]
                    pending['sent_at'] = self.deps.now()
                    await self.request_conversation_processing(
                        cid,
                        pending.get('finalization_job_id'),
                        pending.get('dispatch_generation'),
                    )
            if self.pending_speaker_sample_requests:
                buffered = list(self.pending_speaker_sample_requests)
                self.pending_speaker_sample_requests.clear()
                logger.info(
                    f"Reconnected to pusher, re-sending {len(buffered)} pending speaker sample requests {self.uid} {self.session_id}"
                )
                for person_id, conv_id, segment_ids in buffered:
                    await self.send_speaker_sample_request(person_id, conv_id, segment_ids)
        except PusherCircuitBreakerOpen:
            raise
        except Exception as e:
            logger.error(f"Exception in connect: {e} {self.uid} {self.session_id}")

    async def close(self, code: int = 1000):
        if self.reconnect_task and not self.reconnect_task.done():
            self.reconnect_task.cancel()
            try:
                await self.reconnect_task
            except asyncio.CancelledError:
                pass
            self.reconnect_task = None
        await self._flush()
        if self.pusher_ws:
            await self.pusher_ws.close(code)

    def is_degraded(self):
        return self.reconnect_state in (PusherReconnectState.DEGRADED, PusherReconnectState.HALF_OPEN_PROBE)

    async def send_speaker_sample_request(
        self,
        person_id: str,
        conv_id: str,
        segment_ids: List[str],
    ):
        """Send speaker sample extraction request to pusher with segment IDs."""
        request = (person_id, conv_id, segment_ids)
        if not self.pusher_connected or not self.pusher_ws:
            self.pending_speaker_sample_requests.append(request)
            logger.warning(
                f"Pusher not connected, buffered speaker sample request: person={person_id}, "
                f"{len(segment_ids)} segments ({len(self.pending_speaker_sample_requests)} pending) {self.uid} {self.session_id}"
            )
            return False
        try:
            data = bytearray()
            data.extend(struct.pack("I", 105))
            data.extend(
                bytes(
                    json.dumps(
                        {
                            "person_id": person_id,
                            "conversation_id": conv_id,
                            "segment_ids": segment_ids,
                        }
                    ),
                    "utf-8",
                )
            )
            await self.pusher_ws.send(cast(bytes, data))
            logger.info(
                f"Sent speaker sample request to pusher: person={person_id}, {len(segment_ids)} segments {self.uid} {self.session_id}"
            )
            return True
        except Exception as e:
            self.pending_speaker_sample_requests.append(request)
            if isinstance(e, ConnectionClosed):
                self._mark_disconnected()
            logger.error(f"Failed to send speaker sample request: {e} {self.uid} {self.session_id}")
            return False

    def is_connected(self):
        return self.pusher_connected

    async def pusher_heartbeat(self):
        """Send periodic data-frame heartbeats to reset the GKE ILB idle timer."""
        while self.deps.is_active():
            if await self.deps.wait_for_event(self.deps.shutdown_event, 20):
                break
            if self.pusher_connected and self.pusher_ws:
                try:
                    await self.pusher_ws.send(struct.pack("I", 100))
                except ConnectionClosed:
                    self._mark_disconnected()
                except Exception as e:
                    logger.error(f"Pusher heartbeat send failed: {e} {self.uid} {self.session_id}")

    def start_degraded(self):
        """Enter degraded mode and start reconnect loop after initial connect failure."""
        self.reconnect_state = PusherReconnectState.DEGRADED
        self.degraded_since = self.deps.monotonic()
        if self.reconnect_task is None or self.reconnect_task.done():
            self.reconnect_task = asyncio.create_task(self._pusher_reconnect_loop())
