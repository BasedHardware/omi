"""Session-local, bounded PCM replay for a replaced live provider socket."""

from __future__ import annotations

import os
import asyncio
import time
from collections import deque
from typing import Any, Callable, Literal, cast

from config.live_stt_recovery import recovery_enabled as _env_recovery_enabled
from config.live_stt_recovery import session_recovery_enabled
from config.stt_provider_policy import provider_for_service

from utils.stt.live_metrics import (
    RECONNECT,
    REPLAY_SECONDS,
    WINDOW_REPLAY_SAFE_TRIMS,
    REPLAY_WALL,
    REPLAY_AUDIO,
    REPLAY_QUEUE_HIGH_WATER,
    REPLAY_CLOSED,
)
import utils.stt.replay_delivery as _replay_delivery
from utils.stt.replay_delivery import (
    ReplayPacer,
    replay_packets,
    REPLAY_PACKET_BYTES,
    family,
    clock,
    abort_replay_socket,
    await_frozen_writes,
    bounded_snapshot,
    socket_replay_limits,
)
from utils.stt.provider_resilience import fallback_socket_is_serving
from utils.stt.live_failure import PendingLiveFailover, settle_terminal_socket
from utils.stt.socket import release_live_stt_socket

RING_SECONDS = 15
RECOVERY_CAPTURE_SECONDS = 150
# Keep a full default replay horizon of recent VAD-negative capture, not just pre-roll.
WINDOW_SILENCE_TAIL_SECONDS = 15
MAX_RECONNECTS = 3
MAX_RECONNECTS_PER_MINUTE = 2
MAX_REPLAY_SECONDS = 30


def enabled() -> bool:
    return os.getenv('STT_RESILIENT_RECONNECT', 'false').lower() == 'true'


class ResilientAudio:
    def __init__(
        self,
        sample_rate: int,
        *,
        ring_seconds: int = RING_SECONDS,
        strict_replay: bool = False,
        recovery_enabled: bool | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.ring_seconds = ring_seconds
        self._base_ring_seconds = ring_seconds
        self.strict_replay = strict_replay
        self._chunks: deque[tuple[int, bytes]] = deque()
        self._end_sample = 0
        self.finalized_sample = 0
        self._attempts: deque[float] = deque()
        self._total_attempts = 0
        self._replayed_samples = 0
        self.on_cut: Callable[[int], None] | None = None
        self._recovery_enabled = recovery_enabled if recovery_enabled is not None else _env_recovery_enabled()

    @property
    def buffered_bytes(self) -> int:
        return sum(len(data) for _, data in self._chunks)

    @property
    def capture_bounds(self) -> tuple[int, int]:
        """Retained capture interval; an empty ring has equal boundaries."""
        return (self._chunks[0][0] if self._chunks else self._end_sample, self._end_sample)

    def projected_span_samples(self, data: bytes, start_sample: int | None) -> int:
        """Capture-time span after a send, including VAD-gated gaps."""
        if start_sample is None or not data:
            return 0
        first = self._chunks[0][0] if self._chunks else start_sample
        return max(0, start_sample + len(data) // 2 - first)

    def would_overflow(self, data: bytes, start_sample: int | None) -> bool:
        return self.projected_span_samples(data, start_sample) > self.ring_seconds * self.sample_rate

    def append(self, data: bytes, start_sample: int | None) -> None:
        if start_sample is None or not data:
            return
        self._chunks.append((start_sample, data))
        self._end_sample = max(self._end_sample, start_sample + len(data) // 2)
        self._trim()

    def append_bounded(self, data: bytes, start_sample: int | None, *, max_entries: int = 8192) -> int:
        """Append under the byte/entry caps; returns dropped PCM bytes to meter.

        An oversized packet is sliced to its newest cap-sized suffix before it
        lands; afterwards the oldest retained entries are evicted first. The
        caller meters the returned bytes once — nothing is dropped silently.
        """
        if start_sample is None or not data:
            return 0
        dropped = 0
        cap = RECOVERY_CAPTURE_SECONDS * self.sample_rate * 2
        if len(data) > cap:
            cut = len(data) - cap
            dropped += cut
            data = data[cut:]
            start_sample += cut // 2
        before = self.buffered_bytes
        self.append(data, start_sample)
        dropped += max(0, before + len(data) - self.buffered_bytes)
        retained_bytes = self.buffered_bytes
        while self._chunks and (retained_bytes > cap or len(self._chunks) > max_entries):
            _, evicted = self._chunks.popleft()
            retained_bytes -= len(evicted)
            dropped += len(evicted)
        if dropped and self.on_cut is not None:
            self.on_cut(self._chunks[0][0] if self._chunks else self._end_sample)
        return dropped

    def finalize_through(self, sample: int) -> int:
        before = self.buffered_bytes
        previous = self.finalized_sample
        self.finalized_sample = max(self.finalized_sample, sample)
        self._trim()
        if self.ring_seconds > self._base_ring_seconds and self.finalized_sample > previous:
            first, end = self.capture_bounds
            reclaim_span = max(0, self._base_ring_seconds - RING_SECONDS) * self.sample_rate
            if end - first <= reclaim_span:
                # Replacement headroom is temporary. Once progress has freed
                # enough capture, restore the original horizon with a full
                # replacement tail still free, without evicting pending audio.
                self.ring_seconds = self._base_ring_seconds
        return before - self.buffered_bytes

    def _trim(self) -> None:
        first = self.finalized_sample
        if not self.strict_replay:
            first = max(first, self._end_sample - self.ring_seconds * self.sample_rate)
        cut = False
        while self._chunks and self._chunks[0][0] + len(self._chunks[0][1]) // 2 <= first:
            self._chunks.popleft()
            cut = True
        if self._chunks and self._chunks[0][0] < first:
            start, data = self._chunks.popleft()
            self._chunks.appendleft((first, data[(first - start) * 2 :]))
            cut = True
        if cut and self.on_cut is not None:
            self.on_cut(first)

    def snapshot(self) -> tuple[tuple[int, bytes], ...]:
        return tuple(self._chunks)

    def admit(self, provider: str, reason: str, *, samples: int | None = None) -> bool:
        now = time.monotonic()
        while self._attempts and now - self._attempts[0] >= 60:
            self._attempts.popleft()
        if samples is None:
            samples = sum(len(data) // 2 for _, data in self._chunks)
        if (
            self._total_attempts >= MAX_RECONNECTS
            or len(self._attempts) >= MAX_RECONNECTS_PER_MINUTE
            or self._replayed_samples + samples > MAX_REPLAY_SECONDS * self.sample_rate
        ):
            RECONNECT.labels(provider=provider, reason=reason, outcome='limited').inc()
            return False
        self._total_attempts += 1
        self._attempts.append(now)
        RECONNECT.labels(provider=provider, reason=reason, outcome='attempt').inc()
        return True

    def record_replay(self, provider: str, samples: int) -> None:
        self._replayed_samples += samples
        REPLAY_SECONDS.labels(provider=provider).inc(samples / self.sample_rate)

    def close(self) -> None:
        self._chunks.clear()

    def reserve_replacement_headroom(self) -> None:
        # A full source backlog must not make the first live packet kill its
        # replacement before replay can produce text. Reserve one normal
        # tail per adopted downstream leg, including a full 135s replay. The
        # absolute 150s ceiling bounds retention even across repeated calls.
        if not self._recovery_enabled:
            self.ring_seconds = min(90 + 3 * RING_SECONDS, self.ring_seconds + RING_SECONDS)
            return
        self.ring_seconds = min(90 + 4 * RING_SECONDS, self.ring_seconds + RING_SECONDS)


def trim_window_replay_to_anchor(ring: ResilientAudio | None, socket: Any) -> None:
    """Discard only capture samples before the window's emitted sentence anchor."""
    if ring is None:
        return
    anchor = getattr(socket, 'window_replay_anchor_sample', None)
    sample = anchor() if callable(anchor) else None
    if isinstance(sample, int) and ring.finalize_through(sample):
        WINDOW_REPLAY_SAFE_TRIMS.inc()


def window_replay_action(
    ring: ResilientAudio | None, socket: Any, data: bytes, start_sample: int | None
) -> Literal['append', 'trim', 'failover']:
    """Reserve replay space after reconciling emitted text with the capture ring."""
    if ring is None:
        return 'append'
    trim_window_replay_to_anchor(ring, socket)
    raw = getattr(socket, 'raw', None)
    has_untranscribed_speech = getattr(socket, 'has_untranscribed_speech', None)
    if not callable(has_untranscribed_speech):
        has_untranscribed_speech = getattr(raw, 'has_untranscribed_speech', None)
    speech_pending = callable(has_untranscribed_speech) and has_untranscribed_speech()
    _, capture_end = ring.capture_bounds
    projected_end = max(capture_end, (start_sample or 0) + len(data) // 2)
    age_floor = max(0, projected_end - ring.ring_seconds * ring.sample_rate)
    pending_boundary = getattr(socket, 'window_replay_pending_sample', None)
    pending_sample = pending_boundary() if callable(pending_boundary) else None
    if callable(has_untranscribed_speech) and not speech_pending:
        keep_from = max(0, capture_end - WINDOW_SILENCE_TAIL_SECONDS * ring.sample_rate)
        accounted_boundary = getattr(socket, 'window_replay_accounted_span', None)
        accounted = (
            cast(Callable[[], tuple[int, int] | None], accounted_boundary)() if callable(accounted_boundary) else None
        )
        if accounted is not None and accounted[1] > age_floor:
            # An empty answer settles capacity, not transcript completeness.
            # Its capture audio only leaves replay at the natural ring age.
            keep_from = min(keep_from, accounted[0])
        if ring.finalize_through(max(age_floor, keep_from)):
            WINDOW_REPLAY_SAFE_TRIMS.inc()
    elif isinstance(pending_sample, int) and age_floor <= pending_sample:
        # Answered history may age out while new speech is pending. Never
        # evict an unresolved sample merely to make room for the next packet.
        if ring.finalize_through(age_floor):
            WINDOW_REPLAY_SAFE_TRIMS.inc()
    request_cut = getattr(raw, 'request_replay_cut', None)
    pending_samples = (
        max(0, projected_end - pending_sample)
        if isinstance(pending_sample, int)
        else ring.projected_span_samples(data, start_sample)
    )
    if speech_pending and callable(request_cut) and pending_samples >= ring.ring_seconds * ring.sample_rate * 2 // 3:
        request_cut()
    if not ring.would_overflow(data, start_sample):
        return 'append'
    if (
        callable(has_untranscribed_speech)
        and not speech_pending
        and len(data) <= ring.ring_seconds * ring.sample_rate * 2
    ):
        assert start_sample is not None
        keep_from = start_sample + len(data) // 2 - ring.ring_seconds * ring.sample_rate
        if ring.finalize_through(keep_from):
            WINDOW_REPLAY_SAFE_TRIMS.inc()
        return 'trim'
    if raw is not None:
        snapshot = getattr(socket, 'window_replay_diagnostics', None)
        if callable(snapshot):
            first, end = ring.capture_bounds
            raw.replay_lag_diagnostics = snapshot(first, end, ring.projected_span_samples(data, start_sample))
        fail = getattr(socket, 'fail', None) or raw.fail
        fail('capacity_full', capacity_subtype='replay_ring_cap')
    return 'failover'


def filter_replayed_segments(
    segments: list[dict[str, Any]],
    provider: str | None,
    *,
    soniox: ResilientAudio | None,
    cutoff: int,
) -> list[dict[str, Any]]:
    if soniox is None or provider != 'soniox':
        return segments
    kept = []
    for segment in segments:
        end = segment.get('_capture_end_sample')
        if isinstance(end, int) and end <= cutoff:
            continue
        if isinstance(end, int):
            soniox.finalize_through(end)
        kept.append(segment)
    return kept


class ReplayFilterMixin:
    host: Any

    def _window_ring(self) -> ResilientAudio | None:
        if getattr(self.host, 'stt_model', None) == 'parakeet-window':
            self._window_replay_started = True
        # A replacement accepting bytes is not proof that it transcribed them.
        # Keep this session's replay obligation through every downstream leg.
        return getattr(self, '_window_replay_audio', None) if getattr(self, '_window_replay_started', False) else None

    def _filter_replayed_segments(self, segments: list[dict[str, Any]], provider: str | None) -> list[dict[str, Any]]:
        ring = self._window_ring()
        if ring is not None and provider != 'parakeet':
            cutoff = getattr(self, '_window_replay_cutoff_sample', 0)
            kept = []
            for segment in segments:
                end = segment.get('_capture_end_sample')
                if isinstance(end, int) and end <= cutoff:
                    continue
                if isinstance(end, int) and str(segment.get('text') or '').strip():
                    if ring.finalize_through(end):
                        WINDOW_REPLAY_SAFE_TRIMS.inc()
                kept.append(segment)
            segments = kept
        return filter_replayed_segments(
            segments,
            provider,
            soniox=getattr(self, '_resilient_audio', None),
            cutoff=getattr(self, '_replay_cutoff_sample', 0),
        )


def socket_is_finishing(socket: Any, *, include_unmanaged_finishing: bool = False) -> bool:
    """Read the teardown latch through managed and legacy wrappers."""
    seen: set[int] = set()
    pending = [socket]
    while pending:
        current = pending.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        try:
            outcome = getattr(current, 'leg_outcome', None)
            if outcome is not None:
                # A managed leg calls raw.finish() as transport cleanup after a
                # failed send (e.g. a send queue that overflowed on replay). That
                # sets the raw socket's _finishing, which is not the client
                # leaving. Only the serving owner can declare teardown, so do not
                # descend into the raw transport here.
                return bool(outcome.owner_closing)
            if getattr(current, '_finishing', False) and (
                include_unmanaged_finishing or not session_recovery_enabled(current)
            ):
                return True
            pending.extend((getattr(current, '_conn', None), getattr(current, 'raw', None)))
        except Exception:
            continue
    return False


def retire_window_replay_socket(receiver: Any, socket: Any) -> None:
    retire = getattr(socket, 'retire_for_replay', None)
    if receiver._window_ring() is not None and callable(retire):
        retire()


async def reconnect_live_stt_socket(receiver: Any) -> bool:
    """Use the complete window obligation, with the existing reconnect budget."""
    ring = receiver._resilient_audio
    socket = receiver.stt_socket
    if (
        ring is None
        or socket is None
        or provider_for_service(receiver.host.stt_service) != 'soniox'
        or receiver.host.is_multi_channel
        or receiver.host.use_custom_stt
        or not receiver.host.state.active
        or receiver.host.state.stt_terminal_failure
        or receiver._stt_rebuild is None
        or getattr(receiver, '_resilient_closing', False)
        or socket_is_finishing(socket)
    ):
        return False
    reason = getattr(socket, 'typed_death_reason', None)
    if reason not in {'soniox_rotation', 'provider_5xx', 'connection_lost'}:
        return False
    if reason == 'connection_lost' and not str(getattr(socket, 'death_reason', '')).startswith('ws '):
        return False
    replay_ring = receiver._window_ring() or ring
    identity = getattr(socket, 'routing_target', None) or 'soniox'
    if not receiver.recovery.grant_soniox_reentry(identity):
        RECONNECT.labels(provider='soniox', reason=reason, outcome='limited').inc()
        return False
    RECONNECT.labels(provider='soniox', reason=reason, outcome='attempt').inc()
    receiver._settle_pending_live_failover_failure(continuing=True)
    hop = PendingLiveFailover.from_socket(socket, 'soniox', 'soniox')
    retire_window_replay_socket(receiver, socket)
    try:
        await abort_replay_socket(socket)
    except Exception:
        pass
    finally:
        # Direct sockets carry a lease here; managed sockets release their
        # own gauge in finish(), and release_live_stt_socket is idempotent.
        release_live_stt_socket(socket)
    await asyncio.sleep(0)  # deliver the dead socket's last finalized callback
    if not receiver.host.state.active or receiver.host.state.stt_terminal_failure:
        hop.note_failure(None)
        RECONNECT.labels(provider='soniox', reason=reason, outcome='teardown').inc()
        return False
    receiver._replay_ingesting = True
    limits = socket_replay_limits(socket)
    replay = bounded_snapshot(replay_ring, 'soniox', 'soniox', rate=limits.rate, birth=receiver._live_birth)
    for packet in receiver._replay_live_tail:
        receiver._live_birth.note(packet.start, packet.start + len(packet.data) // 2, packet.received)
    receiver._replay_live_tail.clear()
    receiver._replay_tail_bytes = 0
    receiver._window_replay_cutoff_sample = replay_ring.finalized_sample
    receiver._replay_cutoff_sample = replay_ring.finalized_sample
    parakeet_callback, modulate_callback, epoch = receiver._stt_rebuild[0]()
    if epoch is not None:
        epoch.replay_origin_sample = replay[0][0] if replay else replay_ring.finalized_sample
    raw = None
    try:
        try:
            async with asyncio.timeout(max(0.0, receiver.recovery.dial_budget())):
                raw = await receiver._create_stt_socket(
                    parakeet_callback,
                    receiver._stt_rebuild[1],
                    modulate_callback=modulate_callback,
                    epoch=epoch,
                    same_provider=True,
                    replay_start_sample=replay[0][0] if replay else replay_ring.finalized_sample,
                )
                serving = raw is not None and await fallback_socket_is_serving(raw)
        except TimeoutError:
            serving = False
        if not serving:
            if raw is not None:
                retire_window_replay_socket(receiver, raw)
                if receiver.host.state.active and not receiver.host.state.stt_terminal_failure:
                    settle_terminal_socket(raw, 'soniox', 'connection_lost')
                await abort_replay_socket(raw)
            raise RuntimeError('Soniox reconnect refused')
        adopted = await receiver._pump_replacement(
            raw,
            epoch,
            hop,
            replay,
            replay_ring,
            None,
            sample_rate=receiver._stt_rebuild[1],
            limits=socket_replay_limits(raw),
            dead_provider='soniox',
            meter_source=ring,
        )
        if not adopted:
            if (
                receiver.recovery.client_has_left()
                or not receiver.host.state.active
                or receiver.host.state.stt_terminal_failure
            ):
                retire_window_replay_socket(receiver, raw)
                await abort_replay_socket(raw)
                hop.note_failure(None, continuing=True)
                RECONNECT.labels(provider='soniox', reason=reason, outcome='teardown').inc()
                return False
            raise RuntimeError('Soniox replay send failed')
    except asyncio.CancelledError:
        hop.note_failure(None)
        if raw is not None:
            retire_window_replay_socket(receiver, raw)
            await abort_replay_socket(raw)
        raise
    except Exception:
        if raw is not None:
            retire_window_replay_socket(receiver, raw)
            if receiver.host.state.active and not receiver.host.state.stt_terminal_failure:
                settle_terminal_socket(raw, 'soniox', 'send_failed')
            await abort_replay_socket(raw)
        hop.note_failure(None, continuing=True)
        RECONNECT.labels(provider='soniox', reason=reason, outcome='failed').inc()
        return False
    RECONNECT.labels(provider='soniox', reason=reason, outcome='connected').inc()
    return True


async def replay_chunks(
    socket: Any,
    chunks: tuple[tuple[int, bytes], ...],
    *,
    source: ResilientAudio | None,
    provider: str,
    soniox: ResilientAudio | None,
    is_active: Callable[[], bool] = lambda: True,
    pacer: ReplayPacer | None = None,
    deadline: float | None = None,
    await_writes: bool = False,
) -> int | None:
    """Return the first rejected sample, or None when the snapshot was accepted
    and (with ``await_writes``) its frozen transport writes have completed.

    ``deadline`` is the absolute prefix wall on the module clock: the caller
    passes ``min(began + prefix wall, episode deadline)`` so enqueues
    AND the frozen-write wait share the 20s prefix budget — REPLAY_WALL then
    measures real prefix delivery, not just admission.
    """
    if source is None:
        return None
    successor = family(socket)
    labels = dict(
        source=provider if provider in {'parakeet', 'modulate', 'soniox', 'deepgram'} else 'unknown',
        successor=successor,
    )
    pacer = pacer or ReplayPacer(source.sample_rate, successor, socket)
    began = clock()
    end = (
        began + _replay_delivery.REPLAY_PREFIX_SECONDS
        if deadline is None
        else min(deadline, began + _replay_delivery.REPLAY_PREFIX_SECONDS)
    )
    pacer.deadline = end
    accepted_chunks: list[tuple[int, bytes]] = []
    position = chunks[0][0] if chunks else source.finalized_sample
    expired = False
    try:
        for start, data in replay_packets(
            chunks, max_frame_bytes=getattr(pacer, 'max_frame_bytes', None) or REPLAY_PACKET_BYTES
        ):
            position = start
            if clock() >= end:
                expired = True
                break
            if not await pacer.send(socket, data, start, is_active, replay=True):
                return start
            if soniox is not None:
                accepted_chunks.append((start, data))
            source.record_replay(provider, len(data) // 2)
            REPLAY_AUDIO.labels(**labels).inc(len(data) / (2 * source.sample_rate))
        if not expired and await_writes and not await await_frozen_writes(socket, end):
            expired = True
        if expired:
            fail = getattr(socket, 'fail', None)
            if callable(fail):
                fail('capacity_full')
            else:
                mark = getattr(socket, '_mark_dead', None)
                if callable(mark):
                    mark('replay wall budget exhausted', typed_reason='capacity_full')
            return position
        if soniox is not None:
            for start, data in accepted_chunks:
                soniox.append(data, start)
        return None
    finally:
        pacer.deadline = None
        REPLAY_WALL.labels(**labels).observe(clock() - began)
        queue = getattr(getattr(socket, 'raw', socket), '_send_queue', None)
        REPLAY_QUEUE_HIGH_WATER.labels(**labels).observe(getattr(queue, 'high_water', 0))
        if socket.is_connection_dead and is_active():
            REPLAY_CLOSED.labels(**labels).inc()
