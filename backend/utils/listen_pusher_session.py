import asyncio
import json
import logging
import random
import struct
import time
import uuid
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, cast, Deque, Dict, List, Optional, Tuple

from websockets.legacy.client import WebSocketClientProtocol
from websockets.exceptions import ConnectionClosed

from utils.metrics import PUSHER_CIRCUIT_BREAKER_REJECTIONS, PUSHER_SESSION_DEGRADED
from utils.observability.fallback import record_fallback
from utils.pusher import PusherCircuitBreakerOpen, connect_to_trigger_pusher

# Typed wrapper because utils.pusher.connect_to_trigger_pusher uses the untyped
# `callable` builtin as a parameter annotation; cast to the proper signature.
_connect_to_trigger_pusher: Callable[..., Awaitable[Optional[WebSocketClientProtocol]]] = cast(
    "Callable[..., Awaitable[Optional[WebSocketClientProtocol]]]", connect_to_trigger_pusher
)


logger = logging.getLogger(__name__)

TARGET_SAMPLE_RATE = 16000


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
PUSHER_DELIVERY_ACK_TIMEOUT = 5.0
PUSHER_CLOSE_ACK_TIMEOUT = 10.0
PUSHER_SOCKET_CLOSE_TIMEOUT = 2.0
PUSHER_DELIVERY_DRAIN_OPCODE = 107


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


@dataclass
class _TranscriptDelivery:
    delivery_id: str
    conversation_id: Optional[str]
    segments: List[Dict[str, Any]]
    last_sent_ws: Optional[WebSocketClientProtocol] = None
    last_sent_at: float = 0.0


@dataclass
class _AudioDelivery:
    delivery_id: str
    conversation_id: Optional[str]
    chunks: List[bytes]
    last_received: Optional[float]


class ListenPusherSession:
    def __init__(self, config: ListenPusherSessionConfig, deps: ListenPusherSessionDeps):
        self.config = config
        self.deps = deps
        self.pusher_ws: Optional[WebSocketClientProtocol] = None
        self.pusher_connect_lock = asyncio.Lock()
        self.pusher_receive_lock = asyncio.Lock()
        self.pusher_connected = False
        self.delivery_ack_supported = False
        self.reconnect_state = PusherReconnectState.CONNECTED
        self.reconnect_attempts = 0
        self.reconnect_task: Optional[asyncio.Task[None]] = None
        self.degraded_since: float = 0.0
        self.segment_buffers: Deque[Dict[str, Any]] = deque(maxlen=config.max_segment_buffer_size)
        self.segment_buffer_conversation_ids: Deque[Optional[str]] = deque(maxlen=config.max_segment_buffer_size)
        self.pending_transcript_delivery: Optional[_TranscriptDelivery] = None
        self.transcript_flush_lock = asyncio.Lock()
        self.last_synced_conversation_id: Optional[str] = None
        self.pending_conversation_requests: Dict[str, Dict[str, Any]] = {}
        self.pending_speaker_sample_requests: Deque[Tuple[str, str, List[str]]] = deque(
            maxlen=config.max_pending_speaker_sample_requests
        )
        self.pending_speaker_sample_delivery_ids: Dict[Tuple[str, str, Tuple[str, ...]], str] = {}
        self.pending_speaker_sample_sent: Dict[
            Tuple[str, str, Tuple[str, ...]], Tuple[WebSocketClientProtocol, float]
        ] = {}
        self.speaker_sample_send_lock = asyncio.Lock()
        self.audio_chunks: Deque[bytes] = deque()
        self.audio_chunk_conversation_ids: Deque[Optional[str]] = deque()
        self.audio_chunk_received_at: Deque[float] = deque()
        self.audio_total_size = 0
        self.audio_buffer_last_received: Optional[float] = None
        self.pending_audio_delivery: Optional[_AudioDelivery] = None
        self.audio_flush_lock = asyncio.Lock()

    @property
    def uid(self):
        return self.config.uid

    @property
    def session_id(self):
        return self.config.session_id

    def transcript_send(self, segments: List[Dict[str, Any]]) -> None:
        conversation_id = self.deps.get_current_conversation_id()
        pending_size = len(self.pending_transcript_delivery.segments) if self.pending_transcript_delivery else 0
        live_capacity = max(0, self.config.max_segment_buffer_size - pending_size)
        dropped = False
        for segment in segments:
            if len(self.segment_buffers) >= live_capacity:
                dropped = True
                continue
            self.segment_buffers.append(segment)
            self.segment_buffer_conversation_ids.append(conversation_id)
        if dropped:
            record_fallback(
                component='pusher',
                from_mode='listen_transcript_buffer',
                to_mode='drop_newest',
                reason='capacity_full',
                outcome='degraded',
                log=logger,
            )

    def _delivery_due(
        self,
        last_sent_ws: Optional[WebSocketClientProtocol],
        last_sent_at: float,
        pusher_ws: WebSocketClientProtocol,
    ) -> bool:
        return last_sent_ws is not pusher_ws or self.deps.monotonic() - last_sent_at >= PUSHER_DELIVERY_ACK_TIMEOUT

    def _ack_pusher_delivery(self, delivery_id: str) -> None:
        if self.pending_transcript_delivery is not None and self.pending_transcript_delivery.delivery_id == delivery_id:
            self.pending_transcript_delivery = None
            return
        for request in list(self.pending_speaker_sample_requests):
            person_id, conv_id, segment_ids = request
            request_key = (person_id, conv_id, tuple(segment_ids))
            if self.pending_speaker_sample_delivery_ids.get(request_key) != delivery_id:
                continue
            self.pending_speaker_sample_requests.remove(request)
            self.pending_speaker_sample_delivery_ids.pop(request_key, None)
            self.pending_speaker_sample_sent.pop(request_key, None)
            return

    async def _retry_pending_speaker_sample_requests(self) -> None:
        if not self.pusher_connected or not self.pusher_ws or not self.pending_speaker_sample_requests:
            return
        async with self.speaker_sample_send_lock:
            for person_id, conv_id, segment_ids in list(self.pending_speaker_sample_requests):
                if not self.pusher_connected:
                    break
                await self._send_speaker_sample_request(person_id, conv_id, segment_ids)

    def _take_transcript_delivery(self) -> Optional[_TranscriptDelivery]:
        if self.pending_transcript_delivery is not None:
            return self.pending_transcript_delivery
        if not self.segment_buffers:
            return None

        conversation_id = self.segment_buffer_conversation_ids[0]
        segments: List[Dict[str, Any]] = []
        while self.segment_buffers and self.segment_buffer_conversation_ids[0] == conversation_id:
            segments.append(self.segment_buffers.popleft())
            self.segment_buffer_conversation_ids.popleft()
        delivery = _TranscriptDelivery(
            delivery_id=str(uuid.uuid4()),
            conversation_id=conversation_id or self.deps.get_current_conversation_id(),
            segments=segments,
        )
        self.pending_transcript_delivery = delivery
        return delivery

    def _take_audio_delivery(self) -> Optional[_AudioDelivery]:
        if self.pending_audio_delivery is not None:
            return self.pending_audio_delivery
        if not self.audio_chunks:
            return None

        conversation_id = self.audio_chunk_conversation_ids[0]
        chunks: List[bytes] = []
        received_at: List[float] = []
        total_size = 0
        while self.audio_chunks and self.audio_chunk_conversation_ids[0] == conversation_id:
            chunk = self.audio_chunks.popleft()
            self.audio_chunk_conversation_ids.popleft()
            received_at.append(self.audio_chunk_received_at.popleft())
            chunks.append(chunk)
            total_size += len(chunk)

        delivery = _AudioDelivery(
            delivery_id=str(uuid.uuid4()),
            conversation_id=conversation_id or self.deps.get_current_conversation_id(),
            chunks=chunks,
            last_received=received_at[-1] if received_at else None,
        )
        self.audio_total_size -= total_size
        self.audio_buffer_last_received = self.audio_chunk_received_at[-1] if self.audio_chunk_received_at else None
        self.pending_audio_delivery = delivery
        return delivery

    def _buffer_pending_speaker_sample_request(
        self,
        person_id: str,
        conv_id: str,
        segment_ids: List[str],
    ) -> bool:
        request = (person_id, conv_id, list(segment_ids))
        request_key = (person_id, conv_id, tuple(segment_ids))
        if request in self.pending_speaker_sample_requests:
            return True
        if self.config.max_pending_speaker_sample_requests <= 0:
            record_fallback(
                component='pusher',
                from_mode='listen_speaker_sample_buffer',
                to_mode='drop_newest',
                reason='capacity_full',
                outcome='degraded',
                log=logger,
            )
            return False
        if len(self.pending_speaker_sample_requests) >= self.config.max_pending_speaker_sample_requests:
            record_fallback(
                component='pusher',
                from_mode='listen_speaker_sample_buffer',
                to_mode='drop_newest',
                reason='capacity_full',
                outcome='degraded',
                log=logger,
            )
            return False
        self.pending_speaker_sample_requests.append(request)
        self.pending_speaker_sample_delivery_ids[request_key] = str(uuid.uuid4())
        return True

    def _mark_failed_socket_disconnected(
        self,
        failed_ws: WebSocketClientProtocol,
        *,
        auto_reconnect: bool,
    ) -> None:
        if self.pusher_ws is not failed_ws:
            return
        if auto_reconnect:
            self._mark_disconnected()
        else:
            self.pusher_connected = False

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

    async def request_conversation_processing(
        self,
        conversation_id: str,
        finalization_job_id: Optional[str] = None,
        dispatch_generation: Optional[int] = None,
    ):
        """Request pusher to process a conversation through its durable lease."""
        pusher_ws = self.pusher_ws
        if not self.pusher_connected or not pusher_ws:
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
            data.extend(bytes(json.dumps(payload), "utf-8"))
            await pusher_ws.send(cast(bytes, data))
            logger.info(f"Sent process_conversation request to pusher: {conversation_id} {self.uid} {self.session_id}")
            return True
        except asyncio.CancelledError:
            self._mark_failed_socket_disconnected(
                pusher_ws,
                auto_reconnect=self.deps.is_active(),
            )
            raise
        except Exception as e:
            logger.error(f"Failed to send process_conversation request: {e} {self.uid} {self.session_id}")
            self._mark_failed_socket_disconnected(
                pusher_ws,
                auto_reconnect=self.deps.is_active(),
            )
            return False

    async def _transcript_flush(self, auto_reconnect: bool = True):
        async with self.transcript_flush_lock:
            pusher_ws = self.pusher_ws
            if not self.pusher_connected or not pusher_ws:
                return

            delivery = self._take_transcript_delivery()
            if delivery is None:
                return
            if self.delivery_ack_supported and not self._delivery_due(
                delivery.last_sent_ws, delivery.last_sent_at, pusher_ws
            ):
                return
            try:
                data = bytearray()
                data.extend(struct.pack("I", 102))
                data.extend(
                    bytes(
                        json.dumps(
                            {
                                "segments": delivery.segments,
                                "memory_id": delivery.conversation_id,
                                "delivery_id": delivery.delivery_id,
                            }
                        ),
                        "utf-8",
                    )
                )
            except Exception as e:
                logger.error(f"Pusher transcripts serialization failed: {e} {self.uid} {self.session_id}")
                return

            try:
                await pusher_ws.send(cast(bytes, data))
                if self.delivery_ack_supported:
                    delivery.last_sent_ws = pusher_ws
                    delivery.last_sent_at = self.deps.monotonic()
                elif self.pending_transcript_delivery is delivery:
                    self.pending_transcript_delivery = None
            except asyncio.CancelledError:
                # The stable pending delivery remains available to a reconnecting
                # session even though the caller is being cancelled.
                self._mark_failed_socket_disconnected(
                    pusher_ws,
                    auto_reconnect=self.deps.is_active(),
                )
                raise
            except ConnectionClosed as e:
                logger.error(f"Pusher transcripts Connection closed: {e} {self.uid} {self.session_id}")
                self._mark_failed_socket_disconnected(pusher_ws, auto_reconnect=auto_reconnect)
            except Exception as e:
                logger.error(f"Pusher transcripts failed: {e} {self.uid} {self.session_id}")
                self._mark_failed_socket_disconnected(pusher_ws, auto_reconnect=auto_reconnect)

    async def transcript_consume(self):
        while self.deps.is_active():
            await self.deps.sleep(1)
            if self.pending_transcript_delivery is not None or self.segment_buffers:
                await self._transcript_flush(auto_reconnect=True)

    def audio_bytes_send(self, audio_bytes: bytes, received_at: float):
        max_size = max(0, self.config.max_audio_buffer_size)
        pending_size = (
            sum(len(chunk) for chunk in self.pending_audio_delivery.chunks) if self.pending_audio_delivery else 0
        )
        live_capacity = max(0, max_size - pending_size)
        if live_capacity == 0:
            record_fallback(
                component='pusher',
                from_mode='listen_audio_buffer',
                to_mode='drop_newest',
                reason='capacity_full',
                outcome='degraded',
                log=logger,
            )
            return
        chunk = audio_bytes
        dropped = False
        if len(chunk) > live_capacity:
            chunk = chunk[-live_capacity:]
            dropped = True
        while self.audio_total_size + len(chunk) > live_capacity and self.audio_chunks:
            old = self.audio_chunks.popleft()
            self.audio_chunk_conversation_ids.popleft()
            self.audio_chunk_received_at.popleft()
            self.audio_total_size -= len(old)
            dropped = True
        self.audio_chunks.append(chunk)
        self.audio_chunk_conversation_ids.append(self.deps.get_current_conversation_id())
        self.audio_chunk_received_at.append(received_at)
        self.audio_total_size += len(chunk)
        self.audio_buffer_last_received = received_at
        if dropped:
            record_fallback(
                component='pusher',
                from_mode='listen_audio_buffer',
                to_mode='drop_oldest',
                reason='capacity_full',
                outcome='degraded',
                log=logger,
            )

    async def _audio_bytes_flush(self, auto_reconnect: bool = True):
        async with self.audio_flush_lock:
            pusher_ws = self.pusher_ws
            if not self.pusher_connected or not pusher_ws:
                return

            delivery = self._take_audio_delivery()
            if delivery is None:
                return

            try:
                if delivery.conversation_id and delivery.conversation_id != self.last_synced_conversation_id:
                    data = bytearray()
                    data.extend(struct.pack("I", 103))
                    data.extend(bytes(delivery.conversation_id, "utf-8"))
                    await pusher_ws.send(cast(bytes, data))
                    if self.pusher_ws is pusher_ws:
                        self.last_synced_conversation_id = delivery.conversation_id

                audio_data = b''.join(delivery.chunks)
                effective_rate = TARGET_SAMPLE_RATE if self.config.is_multi_channel else self.config.sample_rate
                buffer_duration_seconds = len(audio_data) / (effective_rate * 2)
                buffer_start_time = (delivery.last_received or self.deps.now()) - buffer_duration_seconds
                data = bytearray()
                data.extend(struct.pack("I", 101))
                data.extend(struct.pack("d", buffer_start_time))
                data.extend(audio_data)
                await pusher_ws.send(cast(bytes, data))
                if self.pending_audio_delivery is delivery:
                    self.pending_audio_delivery = None
            except asyncio.CancelledError:
                # Keep the route-stamped delivery intact for replay, then honor
                # structured cancellation.
                self._mark_failed_socket_disconnected(
                    pusher_ws,
                    auto_reconnect=self.deps.is_active(),
                )
                raise
            except ConnectionClosed as e:
                logger.error(f"Pusher audio_bytes Connection closed: {e} {self.uid} {self.session_id}")
                self._mark_failed_socket_disconnected(pusher_ws, auto_reconnect=auto_reconnect)
            except Exception as e:
                logger.error(f"Pusher audio_bytes failed: {e} {self.uid} {self.session_id}")
                self._mark_failed_socket_disconnected(pusher_ws, auto_reconnect=auto_reconnect)

    async def audio_bytes_consume(self):
        while self.deps.is_active():
            await self.deps.sleep(1)
            if self.pending_audio_delivery is not None or self.audio_total_size > 0:
                await self._audio_bytes_flush(auto_reconnect=True)

    async def pusher_receive(self):
        """Receive and handle messages from pusher, with timeout-based retry for pending requests."""
        while self.deps.is_active():
            pusher_ws = self.pusher_ws
            if not self.pusher_connected or pusher_ws is None:
                await self.deps.sleep(0.5)
                continue

            try:
                async with self.pusher_receive_lock:
                    msg = cast(bytes, await asyncio.wait_for(pusher_ws.recv(), timeout=5.0))
                if not msg or len(msg) < 4:
                    continue
                header_type = struct.unpack('<I', msg[:4])[0]

                if header_type == 202:
                    result = json.loads(msg[4:].decode("utf-8"))
                    delivery_id = result.get("delivery_id")
                    if isinstance(delivery_id, str) and delivery_id:
                        self._ack_pusher_delivery(delivery_id)
                elif header_type == 201:
                    result = json.loads(msg[4:].decode("utf-8"))
                    conversation_id = result.get("conversation_id")

                    if "error" in result:
                        if result.get("terminal"):
                            # The job reached its attempt budget and is now
                            # dead-lettered. Retrying it would never converge.
                            self.pending_conversation_requests.pop(conversation_id, None)
                            logger.error(
                                f"Conversation processing failed terminally: {conversation_id} {self.uid} {self.session_id}"
                            )
                        else:
                            pending = self.pending_conversation_requests.get(conversation_id)
                            if pending is not None:
                                # The pusher has released its durable lease back to
                                # queued. Keep the request so this live session can
                                # reclaim it instead of stranding `processing`.
                                pending['sent_at'] = self.deps.now() - PENDING_REQUEST_TIMEOUT - 1
                            logger.error(f"Conversation processing failed: {self.uid} {self.session_id}")
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
                self._mark_failed_socket_disconnected(pusher_ws, auto_reconnect=True)
            except Exception as e:
                logger.error(f"Pusher receive error: {e} {self.uid} {self.session_id}")
                await self.deps.sleep(0.5)

            await self._retry_pending_speaker_sample_requests()

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
        while self.pusher_connected and (self.pending_audio_delivery is not None or self.audio_chunks):
            before = (
                self.pending_audio_delivery.delivery_id if self.pending_audio_delivery else None,
                len(self.audio_chunks),
            )
            await self._audio_bytes_flush(auto_reconnect=False)
            after = (
                self.pending_audio_delivery.delivery_id if self.pending_audio_delivery else None,
                len(self.audio_chunks),
            )
            if after == before:
                break
        if not self.delivery_ack_supported:
            while self.pusher_connected and (self.pending_transcript_delivery is not None or self.segment_buffers):
                before = (
                    self.pending_transcript_delivery.delivery_id if self.pending_transcript_delivery else None,
                    len(self.segment_buffers),
                )
                await self._transcript_flush(auto_reconnect=False)
                after = (
                    self.pending_transcript_delivery.delivery_id if self.pending_transcript_delivery else None,
                    len(self.segment_buffers),
                )
                if after == before:
                    break

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

    async def _connect(self):
        try:
            pusher_sample_rate = TARGET_SAMPLE_RATE if self.config.is_multi_channel else self.config.sample_rate
            self.pusher_ws = await self.deps.connect_to_pusher(
                self.uid, pusher_sample_rate, retries=5, is_active=self.deps.is_active
            )
            if self.pusher_ws is None:
                return
            self.delivery_ack_supported = False
            response_headers = getattr(self.pusher_ws, 'response_headers', None)
            if response_headers is not None:
                try:
                    self.delivery_ack_supported = response_headers.get('X-Omi-Delivery-Ack') == '1'
                except Exception:
                    self.delivery_ack_supported = False
            self.pusher_connected = True
            self.reconnect_state = PusherReconnectState.CONNECTED
            self.reconnect_attempts = 0
            # Conversation routing is socket-local state on pusher. A fresh
            # connection must receive header 103 before any replayed audio.
            self.last_synced_conversation_id = None
            self.pending_speaker_sample_sent.clear()
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
                logger.info(
                    f"Reconnected to pusher, re-sending {len(buffered)} pending speaker sample requests {self.uid} {self.session_id}"
                )
                for person_id, conv_id, segment_ids in buffered:
                    if not self.pusher_connected:
                        break
                    await self._send_speaker_sample_request(person_id, conv_id, segment_ids)
        except PusherCircuitBreakerOpen:
            raise
        except Exception as e:
            logger.error(f"Exception in connect: {e} {self.uid} {self.session_id}")

    async def _drain_delivery_acks(self, deadline: float) -> None:
        if not self.delivery_ack_supported or not self.pusher_connected or not self.pusher_ws:
            return

        while self.pusher_connected and self.pusher_ws:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return
            if self.pending_transcript_delivery is not None or self.segment_buffers:
                await asyncio.wait_for(
                    self._transcript_flush(auto_reconnect=False),
                    timeout=remaining,
                )
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return
            await asyncio.wait_for(
                self._retry_pending_speaker_sample_requests(),
                timeout=remaining,
            )
            if (
                self.pending_transcript_delivery is None
                and not self.segment_buffers
                and not self.pending_speaker_sample_requests
            ):
                return

            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                logger.warning(
                    'Pusher close acknowledgement deadline elapsed pending_transcript=%s buffered_transcript=%s pending_speaker=%s uid=%s session=%s',
                    self.pending_transcript_delivery is not None,
                    len(self.segment_buffers),
                    len(self.pending_speaker_sample_requests),
                    self.uid,
                    self.session_id,
                )
                return
            try:
                pusher_ws = self.pusher_ws

                async def receive_one() -> bytes:
                    async with self.pusher_receive_lock:
                        return cast(bytes, await pusher_ws.recv())

                msg = await asyncio.wait_for(
                    receive_one(),
                    timeout=min(remaining, PUSHER_DELIVERY_ACK_TIMEOUT),
                )
            except (asyncio.TimeoutError, ConnectionClosed):
                if asyncio.get_running_loop().time() >= deadline:
                    return
                continue
            if not msg or len(msg) < 4 or struct.unpack('<I', msg[:4])[0] != 202:
                continue
            try:
                result = json.loads(msg[4:].decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            delivery_id = result.get('delivery_id')
            if isinstance(delivery_id, str) and delivery_id:
                self._ack_pusher_delivery(delivery_id)

    async def _request_delivery_drain(self) -> None:
        if not self.delivery_ack_supported or not self.pusher_connected or not self.pusher_ws:
            return
        await self.pusher_ws.send(struct.pack('I', PUSHER_DELIVERY_DRAIN_OPCODE))

    async def close(self, code: int = 1000):
        if self.reconnect_task and not self.reconnect_task.done():
            self.reconnect_task.cancel()
            try:
                await self.reconnect_task
            except asyncio.CancelledError:
                pass
            self.reconnect_task = None
        deadline = asyncio.get_running_loop().time() + PUSHER_CLOSE_ACK_TIMEOUT

        async def flush_and_drain() -> None:
            await self._flush()
            await self._retry_pending_speaker_sample_requests()
            await self._request_delivery_drain()
            await self._drain_delivery_acks(deadline)

        try:
            await asyncio.wait_for(
                flush_and_drain(),
                timeout=max(0.0, deadline - asyncio.get_running_loop().time()),
            )
        except asyncio.TimeoutError:
            logger.warning(
                'Pusher close delivery deadline elapsed pending_transcript=%s buffered_transcript=%s pending_speaker=%s uid=%s session=%s',
                self.pending_transcript_delivery is not None,
                len(self.segment_buffers),
                len(self.pending_speaker_sample_requests),
                self.uid,
                self.session_id,
            )
        finally:
            pusher_ws = self.pusher_ws
            if pusher_ws is not None:
                try:
                    await asyncio.wait_for(
                        pusher_ws.close(code),
                        timeout=PUSHER_SOCKET_CLOSE_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    logger.warning('Pusher socket close deadline elapsed uid=%s session=%s', self.uid, self.session_id)

    def is_degraded(self):
        return self.reconnect_state in (PusherReconnectState.DEGRADED, PusherReconnectState.HALF_OPEN_PROBE)

    async def send_speaker_sample_request(
        self,
        person_id: str,
        conv_id: str,
        segment_ids: List[str],
    ):
        """Send speaker sample extraction request to pusher with segment IDs."""
        async with self.speaker_sample_send_lock:
            if not self._buffer_pending_speaker_sample_request(person_id, conv_id, segment_ids):
                return
            if not self.pusher_connected or not self.pusher_ws:
                logger.warning(
                    f"Pusher not connected, buffered speaker sample request: person={person_id}, "
                    f"{len(segment_ids)} segments ({len(self.pending_speaker_sample_requests)} pending) {self.uid} {self.session_id}"
                )
                return
            await self._send_speaker_sample_request(person_id, conv_id, segment_ids)

    async def _send_speaker_sample_request(
        self,
        person_id: str,
        conv_id: str,
        segment_ids: List[str],
    ) -> None:
        pusher_ws = self.pusher_ws
        if not self.pusher_connected or not pusher_ws:
            return

        request = (person_id, conv_id, list(segment_ids))
        request_key = (person_id, conv_id, tuple(segment_ids))
        delivery_id = self.pending_speaker_sample_delivery_ids.get(request_key)
        if delivery_id is None:
            if not self._buffer_pending_speaker_sample_request(person_id, conv_id, segment_ids):
                return
            delivery_id = self.pending_speaker_sample_delivery_ids.get(request_key)
        if delivery_id is None:
            return
        sent = self.pending_speaker_sample_sent.get(request_key)
        if self.delivery_ack_supported and sent is not None and not self._delivery_due(sent[0], sent[1], pusher_ws):
            return
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
                            "delivery_id": delivery_id,
                        }
                    ),
                    "utf-8",
                )
            )
            await pusher_ws.send(cast(bytes, data))
            if self.delivery_ack_supported:
                self.pending_speaker_sample_sent[request_key] = (pusher_ws, self.deps.monotonic())
            else:
                try:
                    self.pending_speaker_sample_requests.remove(request)
                except ValueError:
                    pass
                self.pending_speaker_sample_delivery_ids.pop(request_key, None)
                self.pending_speaker_sample_sent.pop(request_key, None)
            logger.info(
                f"Sent speaker sample request to pusher: person={person_id}, {len(segment_ids)} segments {self.uid} {self.session_id}"
            )
        except asyncio.CancelledError:
            # Request and delivery id remain buffered for a safe replay.
            self._mark_failed_socket_disconnected(
                pusher_ws,
                auto_reconnect=self.deps.is_active(),
            )
            raise
        except Exception as e:
            logger.error(f"Failed to send speaker sample request: {e} {self.uid} {self.session_id}")
            self._mark_failed_socket_disconnected(pusher_ws, auto_reconnect=True)

    def is_connected(self):
        return self.pusher_connected

    async def pusher_heartbeat(self):
        """Send periodic data-frame heartbeats to reset the GKE ILB idle timer."""
        while self.deps.is_active():
            if await self.deps.wait_for_event(self.deps.shutdown_event, 20):
                break
            pusher_ws = self.pusher_ws
            if self.pusher_connected and pusher_ws:
                try:
                    await pusher_ws.send(struct.pack("I", 100))
                except ConnectionClosed:
                    self._mark_failed_socket_disconnected(pusher_ws, auto_reconnect=True)
                except Exception as e:
                    logger.error(f"Pusher heartbeat send failed: {e} {self.uid} {self.session_id}")

    def start_degraded(self):
        """Enter degraded mode and start reconnect loop after initial connect failure."""
        self.reconnect_state = PusherReconnectState.DEGRADED
        self.degraded_since = self.deps.monotonic()
        if self.reconnect_task is None or self.reconnect_task.done():
            self.reconnect_task = asyncio.create_task(self._pusher_reconnect_loop())
