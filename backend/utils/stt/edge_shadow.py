"""D2 edge shadow: mirror a uid-hash cohort's raw audio to listen-edge.

Plan D, D2 (omi-knowledge-base projects/backend-target-architecture/
plan-d-realtime-gateway.md). For sessions in the cohort, listen sends a copy
of every decoded client frame (raw payload plus its capture position) and its
own VAD gate's window probabilities to listen-edge's ``/v1/shadow``. The edge
decodes the frames, runs the same gate, and exports the agreement. Nothing
comes back and nothing reaches a provider.

The live session never waits on the mirror. ``offer`` only appends to a
bounded queue; one background task owns the socket. A full queue, a failed
connect, a failed or slow send, or an edge close stops mirroring for the rest
of the session (a gap would desynchronize the edge's decoder anyway).

Wire format: see ``backend/edge/src/shadow.rs`` (protocol v1).

Kill switch: ``EDGE_SHADOW_PERCENT`` (default 0). Mirroring also needs
``EDGE_SHADOW_URL``; ``EDGE_SHADOW_TOKEN`` is sent when set.
"""

import asyncio
import hashlib
import logging
import math
import os
import struct
from typing import Any, Callable, Optional, Sequence
from urllib.parse import urlencode

import websockets

from utils.metrics import OMI_LISTEN_EDGE_SHADOW_SESSIONS_TOTAL

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 1
MIRRORED_CODECS = frozenset({'opus', 'opus_fs320', 'pcm8', 'pcm16'})
# Messages held for the sender task: about 10 s of 20 ms frames plus window
# reports. Past this the edge is not keeping up and the mirror stops.
QUEUE_MESSAGES = 1024
CONNECT_TIMEOUT_SECONDS = 2.0
SEND_TIMEOUT_SECONDS = 2.0
UNKNOWN_ORIGIN = 2**64 - 1

_FRAME = struct.Struct('>BQI')
_GATE_START = struct.Struct('>BHBBddIQ')
_WINDOWS_HEAD = struct.Struct('>BHI')
_OPEN = struct.Struct('>BHQQ')

# Session outcomes (closed set; the metric's only label).
OUTCOMES = ('completed', 'queue_full', 'connect_failed', 'send_failed', 'edge_closed')


def shadow_percent() -> float:
    """``EDGE_SHADOW_PERCENT`` in [0, 100]; anything else is 0 (off)."""
    raw = os.getenv('EDGE_SHADOW_PERCENT', '0')
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(value) or value <= 0:
        return 0.0
    return min(value, 100.0)


def in_cohort(uid: str, percent: float) -> bool:
    """Static uid-hash cohort: the same uid is always in or out at a given percent."""
    if not uid or percent <= 0:
        return False
    digest = hashlib.sha256(f'edge-shadow:{uid}'.encode()).digest()
    bucket = int.from_bytes(digest[:4], 'big') % 10000
    return bucket < percent * 100


def session_key(session_id: str) -> str:
    """Hashed session key for the edge's logs; never a uid."""
    return hashlib.sha256(f'edge-shadow-session:{session_id}'.encode()).hexdigest()[:32]


def encode_frame(start_sample: int, decoded_samples: int, payload: bytes) -> bytes:
    return _FRAME.pack(1, start_sample, decoded_samples) + payload


def encode_gate_start(
    gen: int,
    *,
    agc: bool,
    active: bool,
    speech_threshold: float,
    continue_threshold: float,
    hangover_ms: float,
    origin_sample: Optional[int],
) -> bytes:
    return _GATE_START.pack(
        2,
        gen,
        1 if agc else 0,
        0 if active else 1,
        float(speech_threshold),
        float(continue_threshold),
        int(hangover_ms),
        UNKNOWN_ORIGIN if origin_sample is None else origin_sample,
    )


def encode_windows(gen: int, first_ordinal: int, probs: Sequence[float]) -> bytes:
    return _WINDOWS_HEAD.pack(3, gen, first_ordinal) + struct.pack(f'>{len(probs)}f', *probs)


def encode_open(gen: int, chunk_start: int, preroll_start: int) -> bytes:
    return _OPEN.pack(4, gen, chunk_start, preroll_start)


class GateTap:
    """Reports one VAD gate's windows and opens to the mirror.

    The gate calls ``chunk`` after scoring each chunk and ``opened`` on a
    SILENCE -> SPEECH transition. The first chunk announces the gate
    (``GATE_START``) with its origin, so the edge can align its own gate.
    """

    def __init__(self, mirror: 'EdgeShadowMirror', gen: int):
        self._mirror = mirror
        self.gen = gen
        self._announced = False

    def chunk(self, gate: Any, start_sample: Optional[int], first_ordinal: int, probs: Sequence[float], agc: bool):
        if not self._announced:
            self._announced = True
            speech_threshold, continue_threshold, hangover_ms = gate.decision_params()
            self._mirror.offer(
                encode_gate_start(
                    self.gen,
                    agc=agc,
                    active=gate.mode == 'active',
                    speech_threshold=speech_threshold,
                    continue_threshold=continue_threshold,
                    hangover_ms=hangover_ms,
                    origin_sample=start_sample,
                )
            )
        if probs:
            self._mirror.offer(encode_windows(self.gen, first_ordinal, probs))

    def opened(self, chunk_start: int, preroll_start: int) -> None:
        self._mirror.offer(encode_open(self.gen, chunk_start, preroll_start))

    def renew(self) -> 'GateTap':
        """The gate restarted its VAD state: report it as the next gate."""
        return self._mirror.tap()


class EdgeShadowMirror:
    """One session's mirror: a bounded queue and a sender task."""

    def __init__(
        self,
        url: str,
        *,
        codec: str,
        sample_rate: int,
        session_id: str,
        token: str = '',
        queue_messages: int = QUEUE_MESSAGES,
        connect: Callable[..., Any] = websockets.connect,
    ):
        query = urlencode(
            {'v': PROTOCOL_VERSION, 'codec': codec, 'sample_rate': sample_rate, 'session': session_key(session_id)}
        )
        self._url = f'{url}?{query}'
        self._headers = {'x-edge-shadow-token': token} if token else {}
        self._connect = connect
        self._queue: asyncio.Queue[Optional[bytes]] = asyncio.Queue(maxsize=queue_messages)
        self._task: Optional[asyncio.Task[Any]] = None
        self._gates = 0
        self.active = True
        self.outcome: Optional[str] = None

    def start(self, spawn: Callable[..., 'asyncio.Task[Any]']) -> None:
        self._task = spawn(self._run(), name='edge_shadow_mirror')

    def offer(self, message: bytes) -> None:
        """Queue one message without waiting. Never raises."""
        if not self.active:
            return
        try:
            self._queue.put_nowait(message)
        except asyncio.QueueFull:
            self._stop('queue_full')
        except Exception as error:
            self._abandon(error)

    def frame(self, start_sample: int, decoded_samples: int, payload: bytes) -> None:
        """Copy one client frame. Never raises into the session."""
        if not self.active:
            return
        try:
            message = encode_frame(start_sample, decoded_samples, payload)
        except Exception as error:
            self._abandon(error)
            return
        self.offer(message)

    def tap(self) -> GateTap:
        """A tap for a newly built gate; each gets the next generation."""
        self._gates += 1
        return GateTap(self, self._gates)

    def close(self) -> None:
        """Session over: flush what is queued, then close the socket. Never raises."""
        if not self.active:
            return
        self.active = False
        try:
            self._queue.put_nowait(None)
        except asyncio.QueueFull:
            self._stop('queue_full')
        except Exception as error:
            self._abandon(error)

    def _abandon(self, error: Exception) -> None:
        """Last resort: anything unexpected ends the mirror, never the session."""
        self.active = False
        logger.warning('edge shadow mirror stopped type=%s', type(error).__name__)
        try:
            self._stop('send_failed')
        except Exception:
            pass

    def _stop(self, outcome: str) -> None:
        self.active = False
        self._finish(outcome)
        self._cancel()

    def _cancel(self) -> None:
        task = self._task
        if task is None or task.done():
            return
        try:
            current = asyncio.current_task()
        except RuntimeError:  # called off the loop
            current = None
        if task is not current:
            task.cancel()

    def _finish(self, outcome: str) -> None:
        if self.outcome is None:
            self.outcome = outcome
            try:
                OMI_LISTEN_EDGE_SHADOW_SESSIONS_TOTAL.labels(outcome=outcome).inc()
            except Exception:
                logger.warning('edge shadow outcome metric failed')

    async def _run(self) -> None:
        try:
            socket = await asyncio.wait_for(
                self._connect(
                    self._url,
                    extra_headers=self._headers,
                    open_timeout=CONNECT_TIMEOUT_SECONDS,
                    close_timeout=1,
                    ping_interval=None,
                    max_queue=1,
                    write_limit=64 * 1024,
                ),
                timeout=CONNECT_TIMEOUT_SECONDS,
            )
        except Exception as error:
            logger.info('edge shadow connect failed type=%s', type(error).__name__)
            self.active = False
            self._finish('connect_failed')
            return
        try:
            while True:
                message = await self._queue.get()
                if message is None:
                    self._finish('completed')
                    break
                try:
                    await asyncio.wait_for(socket.send(message), timeout=SEND_TIMEOUT_SECONDS)
                except websockets.ConnectionClosed:
                    self.active = False
                    self._finish('edge_closed')
                    break
                except Exception as error:
                    logger.info('edge shadow send failed type=%s', type(error).__name__)
                    self.active = False
                    self._finish('send_failed')
                    break
        finally:
            try:
                await asyncio.wait_for(socket.close(), timeout=1)
            except Exception:
                pass


def attach_tap(gate: Any, receiver: Any) -> None:
    """Give a newly built gate a tap when the receiver's session is mirrored.

    Looks the factory up on the receiver's class, so test doubles without one
    are left alone. Never raises.
    """
    factory = getattr(type(receiver), 'edge_shadow_tap', None)
    if gate is None or not callable(factory):
        return
    try:
        gate.edge_tap = factory(receiver)
    except Exception as error:
        logger.warning('edge shadow tap attach failed type=%s', type(error).__name__)


def session_mirror(receiver: Any) -> Optional[EdgeShadowMirror]:
    """The listen receiver's mirror, started on the first call if its session is in the cohort.

    Only single-channel server-STT sessions have capture positions
    (``receiver.capture_timeline``), so only they are mirrored. The percent is
    checked first: at the default 0 nothing else is read. Never raises.
    """
    if getattr(receiver, '_edge_shadow_checked', False):
        return receiver.edge_shadow
    receiver._edge_shadow_checked = True
    receiver.edge_shadow = None
    if receiver.capture_timeline is None or shadow_percent() <= 0:
        return None
    try:
        host = receiver.host
        request = host.request
        receiver.edge_shadow = maybe_start(
            uid=request.uid,
            session_id=host.session_id,
            codec=request.codec,
            sample_rate=int(request.sample_rate),
            spawn=host.spawn,
        )
    except Exception as error:
        logger.warning('edge shadow setup failed type=%s', type(error).__name__)
    return receiver.edge_shadow


def maybe_start(
    *,
    uid: str,
    session_id: str,
    codec: str,
    sample_rate: int,
    spawn: Callable[..., 'asyncio.Task[Any]'],
) -> Optional[EdgeShadowMirror]:
    """Start a mirror if this session is in the cohort; otherwise None.

    Never raises: the shadow must not affect whether a session starts.
    """
    try:
        percent = shadow_percent()
        url = os.getenv('EDGE_SHADOW_URL', '').strip()
        if percent <= 0 or not url or codec not in MIRRORED_CODECS or not in_cohort(uid, percent):
            return None
        mirror = EdgeShadowMirror(
            url,
            codec=codec,
            sample_rate=sample_rate,
            session_id=session_id,
            token=os.getenv('EDGE_SHADOW_TOKEN', ''),
        )
        mirror.start(spawn)
        return mirror
    except Exception as error:
        logger.warning('edge shadow start failed type=%s', type(error).__name__)
        return None
