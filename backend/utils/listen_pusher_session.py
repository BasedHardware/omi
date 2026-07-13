import asyncio
import json
import logging
import random
import struct
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, cast, Deque, Dict, List, Optional, Tuple

from websockets.client import WebSocketClientProtocol
from websockets.exceptions import ConnectionClosed

from utils.metrics import PUSHER_CIRCUIT_BREAKER_REJECTIONS, PUSHER_SESSION_DEGRADED
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


class ListenPusherSession:
    def __init__(self, config: ListenPusherSessionConfig, deps: ListenPusherSessionDeps):
        self.config = config
        self.deps = deps
        self.pusher_ws: Optional[WebSocketClientProtocol] = None
        self.pusher_connect_lock = asyncio.Lock()
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
        self.audio_chunks: Deque[bytes] = deque()
        self.audio_total_size = 0
        self.audio_buffer_last_received: Optional[float] = None

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
            data.extend(bytes(json.dumps(payload), "utf-8"))
            await self.pusher_ws.send(cast(bytes, data))
            logger.info(f"Sent process_conversation request to pusher: {conversation_id} {self.uid} {self.session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send process_conversation request: {e} {self.uid} {self.session_id}")
            return False

    async def _transcript_flush(self, auto_reconnect: bool = True):
        if self.pusher_connected and self.pusher_ws and len(self.segment_buffers) > 0:
            try:
                data = bytearray()
                data.extend(struct.pack("I", 102))
                data.extend(
                    bytes(
                        json.dumps(
                            {
                                "segments": list(self.segment_buffers),
                                "memory_id": self.deps.get_current_conversation_id(),
                            }
                        ),
                        "utf-8",
                    )
                )
                self.segment_buffers.clear()
                await self.pusher_ws.send(cast(bytes, data))
            except ConnectionClosed as e:
                logger.error(f"Pusher transcripts Connection closed: {e} {self.uid} {self.session_id}")
                self._mark_disconnected()
            except Exception as e:
                logger.error(f"Pusher transcripts failed: {e} {self.uid} {self.session_id}")

    async def transcript_consume(self):
        while self.deps.is_active():
            await self.deps.sleep(1)
            if len(self.segment_buffers) > 0:
                await self._transcript_flush(auto_reconnect=True)

    def audio_bytes_send(self, audio_bytes: bytes, received_at: float):
        chunk = audio_bytes
        if len(chunk) > self.config.max_audio_buffer_size:
            chunk = chunk[-self.config.max_audio_buffer_size :]
        while self.audio_total_size + len(chunk) > self.config.max_audio_buffer_size and self.audio_chunks:
            old = self.audio_chunks.popleft()
            self.audio_total_size -= len(old)
        self.audio_chunks.append(chunk)
        self.audio_total_size += len(chunk)
        self.audio_buffer_last_received = received_at

    async def _audio_bytes_flush(self, auto_reconnect: bool = True):
        current_conversation_id = self.deps.get_current_conversation_id()
        if (
            self.pusher_ws
            and current_conversation_id
            and (
                self.last_synced_conversation_id is None or current_conversation_id != self.last_synced_conversation_id
            )
        ):
            try:
                data = bytearray()
                data.extend(struct.pack("I", 103))
                data.extend(bytes(current_conversation_id, "utf-8"))
                await self.pusher_ws.send(cast(bytes, data))
                self.last_synced_conversation_id = current_conversation_id
            except ConnectionClosed as e:
                logger.error(f"Pusher audio_bytes Connection closed: {e} {self.uid} {self.session_id}")
                self._mark_disconnected()
            except Exception as e:
                logger.error(f"Failed to send conversation_id to pusher: {e} {self.uid} {self.session_id}")

        if self.pusher_connected and self.pusher_ws and self.audio_total_size > 0:
            try:
                effective_rate = TARGET_SAMPLE_RATE if self.config.is_multi_channel else self.config.sample_rate
                buffer_duration_seconds = self.audio_total_size / (effective_rate * 2)
                buffer_start_time = (self.audio_buffer_last_received or self.deps.now()) - buffer_duration_seconds
                audio_data = b''.join(self.audio_chunks)
                data = bytearray()
                data.extend(struct.pack("I", 101))
                data.extend(struct.pack("d", buffer_start_time))
                data.extend(audio_data)
                self.audio_chunks.clear()
                self.audio_total_size = 0
                del audio_data
                await self.pusher_ws.send(cast(bytes, data))
            except ConnectionClosed as e:
                logger.error(f"Pusher audio_bytes Connection closed: {e} {self.uid} {self.session_id}")
                self._mark_disconnected()
            except Exception as e:
                logger.error(f"Pusher audio_bytes failed: {e} {self.uid} {self.session_id}")

    async def audio_bytes_consume(self):
        while self.deps.is_active():
            await self.deps.sleep(1)
            if self.audio_total_size > 0:
                await self._audio_bytes_flush(auto_reconnect=True)

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
                    self.pending_conversation_requests.pop(conversation_id, None)

                    if "error" in result:
                        logger.error(f"Conversation processing failed: {result['error']} {self.uid} {self.session_id}")
                        continue

                    if result.get("success"):
                        logger.info(f"Conversation processed by pusher: {conversation_id} {self.uid} {self.session_id}")
                        self.deps.on_conversation_processed(conversation_id)

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
                        f"Conversation {cid} retry limit reached, keeping buffered for pusher recovery {self.uid} {self.session_id}"
                    )
                    info['sent_at'] = now
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
        await self._audio_bytes_flush(auto_reconnect=False)
        await self._transcript_flush(auto_reconnect=False)

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
        if not self.pusher_connected or not self.pusher_ws:
            self.pending_speaker_sample_requests.append((person_id, conv_id, segment_ids))
            logger.warning(
                f"Pusher not connected, buffered speaker sample request: person={person_id}, "
                f"{len(segment_ids)} segments ({len(self.pending_speaker_sample_requests)} pending) {self.uid} {self.session_id}"
            )
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
                        }
                    ),
                    "utf-8",
                )
            )
            await self.pusher_ws.send(cast(bytes, data))
            logger.info(
                f"Sent speaker sample request to pusher: person={person_id}, {len(segment_ids)} segments {self.uid} {self.session_id}"
            )
        except Exception as e:
            logger.error(f"Failed to send speaker sample request: {e} {self.uid} {self.session_id}")

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
