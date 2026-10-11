"""Audio-time pacing and bounded, ordered live delivery behind a replay prefix."""

from __future__ import annotations

import asyncio
import bisect
import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterator, cast

from config.live_stt_replay import ReplayLimits, DEFAULT_REPLAY_LIMITS
from utils.stt.live_metrics import REPLAY_SKIPPED
from utils.stt.live_reason import normalize_live_stt_reason
from utils.stt.send_queue import audio_send_deadline
from utils.stt.socket import release_live_stt_socket

REPLAY_WALL_BUDGET = 25.0
REPLAY_CONNECT_SECONDS = 5.0
REPLAY_PREFIX_SECONDS = REPLAY_WALL_BUDGET - REPLAY_CONNECT_SECONDS
LIVE_TAIL_SECONDS = REPLAY_WALL_BUDGET + 1.0
TAIL_RESIDENCE_SECONDS = 28.0
SHUTDOWN_CLEANUP_SECONDS = 2.0
REPLAY_RATES = {'soniox': 1.0, 'modulate': 1.0, 'deepgram': 1.0, 'parakeet': 1.0}
clock = time.monotonic
sleep = asyncio.sleep
logger = logging.getLogger(__name__)


def family(socket: Any, fallback: str = 'unknown') -> str:
    current = socket
    seen: set[int] = set()
    for _ in range(8):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        service = getattr(current, 'service', None)
        name = getattr(service, 'value', service)
        if name in REPLAY_RATES:
            return name
        name = type(current).__name__.lower()
        matched = next((key for key in REPLAY_RATES if key in name), None)
        if matched:
            return matched
        current = (
            getattr(current, 'raw', None) or getattr(current, '_conn', None) or getattr(current, 'connection', None)
        )
    return fallback if fallback in REPLAY_RATES else 'unknown'


def socket_replay_limits(socket: Any, family_name: str = 'unknown') -> ReplayLimits:
    """Typed endpoint limits: selected target declaration, then adapter, then
    the safe default. Never a guessed family map."""
    current = socket
    seen: set[int] = set()
    for _ in range(8):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        target = getattr(current, '_routing_target_entry', None) or getattr(current, 'target', None)
        declared = getattr(target, 'replay', None) if target is not None else None
        if isinstance(declared, ReplayLimits):
            return declared
        declared = getattr(current, 'replay_limits', None)
        if isinstance(declared, ReplayLimits):
            return declared
        current = getattr(current, 'raw', None) or getattr(current, '_conn', None)
    declared_rate = getattr(socket, 'max_replay_rate', REPLAY_RATES.get(family_name, 1.0))
    rate = float(declared_rate) if type(declared_rate) in (float, int) and 0 < declared_rate <= 1.0 else 1.0
    if rate == DEFAULT_REPLAY_LIMITS.rate and REPLAY_PACKET_BYTES == DEFAULT_REPLAY_LIMITS.max_frame_bytes:
        return DEFAULT_REPLAY_LIMITS
    return ReplayLimits(rate=rate, max_frame_bytes=REPLAY_PACKET_BYTES)


REPLAY_PACKET_BYTES = 16 * 1024

WRITER_SLOT_SECONDS = 2.0


def _next_audio_slot(previous: float, duration: float, now: float) -> float:
    """Advance the armed audio slot from the previous slot, not the observed
    send/write time: sub-frame timer oversleep is absorbed instead of
    accumulating drift, while a slip of one frame or longer rebases on the
    clock so it never banks catch-up credit."""
    return (now if now - previous >= duration else previous) + duration


class AudioDeliveryExpired(TimeoutError):
    """A queued live audio frame outlived its absolute capture-age deadline."""


class RecoveryWriterPace:
    """Opt-in per-recovery-leg wire cadence shared with the typed limits.

    Sustained writes stay at <=1x audio time plus the bounded jitter allowance
    of queued-plus-in-flight bytes. There is no catch-up credit: slots advance
    from the previously armed slot (sub-frame timer oversleep is absorbed, not
    accumulated), and a stall of one frame or longer rebases on the clock, so
    a blocked write never earns debt that a resumed transport could burst with.
    """

    def __init__(self, sample_rate: int, rate: float, budget: Callable[[], float | None] = lambda: None) -> None:
        self.sample_rate = sample_rate
        self.rate = rate
        self.budget = budget
        self.next_write = 0.0

    async def throttle(self, nbytes: int, deadline: float | None = None) -> None:
        """Wait until this frame's earliest write start. The wait is
        interruptible in <=WRITER_SLOT_SECONDS chunks so an episode deadline
        or a dead leg can't hold the loop, but the slot itself is never
        released early. A queued frame's absolute deadline applies even when
        the next slot is already due."""
        while True:
            if deadline is not None and clock() >= deadline:
                raise AudioDeliveryExpired('live audio delivery expired')
            delay = self.next_write - clock()
            if delay <= 0:
                return
            cap = self.budget()
            if cap is not None and cap <= 0:
                raise TimeoutError('recovery writer budget exhausted')
            if deadline is not None:
                await sleep(min(delay, WRITER_SLOT_SECONDS, max(0.000001, deadline - clock())))
            else:
                await sleep(min(delay, WRITER_SLOT_SECONDS))

    def note_write(self, nbytes: int) -> float:
        """Record the write start immediately before ws.send."""
        start = clock()
        self.next_write = _next_audio_slot(self.next_write, nbytes / (2 * self.sample_rate * self.rate), start)
        return start

    def complete_write(self) -> None:
        """Clamp the armed slot to the actual completion — a write that ran
        long keeps its slot in the future; a fast one keeps start+duration."""
        self.next_write = max(self.next_write, clock())

    def write_bound(self, deadline: float | None = None) -> float:
        """Per-write transport bound during recovery: 2s, episode left, and the
        queued frame's remaining absolute deadline — never a send after expiry."""
        cap = self.budget()
        if cap is not None and cap <= 0:
            raise TimeoutError('recovery writer budget exhausted')
        bound = WRITER_SLOT_SECONDS if cap is None else min(WRITER_SLOT_SECONDS, cap)
        if deadline is not None:
            remaining = deadline - clock()
            if remaining <= 0:
                raise AudioDeliveryExpired('live audio delivery expired')
            bound = min(bound, remaining)
        return bound


def enable_recovery_writer_pace(
    socket: Any, sample_rate: int, limits: ReplayLimits, budget: Callable[[], float | None]
) -> None:
    """Opt a recovery leg's real transport into writer cadence. Managed
    wrappers and initial ordinary/PTT legs never see this call."""
    if getattr(socket, 'recovery_enabled', None) is False:
        return
    current = socket
    seen: set[int] = set()
    for _ in range(8):
        if current is None or id(current) in seen:
            return
        seen.add(id(current))
        enable = getattr(current, 'enable_writer_pacing', None)
        if callable(enable):
            enable(sample_rate, limits.rate, budget)
            return
        current = getattr(current, 'raw', None) or getattr(current, '_conn', None)


async def await_frozen_writes(socket: Any, deadline: float | None) -> bool:
    """Wait until the leg's send queue has written every audio frame that was
    enqueued when this call began — the frozen prefix boundary, not the live
    queue that keeps extending behind it."""
    queue = getattr(getattr(socket, 'raw', socket), '_send_queue', None)
    frozen = getattr(queue, 'enqueued_audio', None) if queue is not None else None
    if not isinstance(frozen, int):
        return True
    while True:
        written = getattr(queue, 'written_audio', 0)
        if written >= frozen:
            return True
        raw = getattr(socket, 'raw', socket)
        if getattr(raw, 'is_connection_dead', False):
            return False
        if deadline is not None and clock() >= deadline:
            return False
        await sleep(0.01)


def replay_packets(
    chunks: tuple[tuple[int, bytes], ...], max_frame_bytes: int | None = None
) -> Iterator[tuple[int, bytes]]:
    """Coalesce adjacent s16le capture spans; bound copies and preserve gaps."""
    if max_frame_bytes is None:
        max_frame_bytes = REPLAY_PACKET_BYTES
    pending = bytearray()
    first = 0
    for start, data in chunks:
        if pending and start != first + len(pending) // 2:
            yield first, bytes(pending)
            pending.clear()
        offset = 0
        while offset < len(data):
            if not pending:
                first = start + offset // 2
            count = min(max_frame_bytes - len(pending), len(data) - offset)
            pending.extend(data[offset : offset + count])
            offset += count
            if len(pending) == max_frame_bytes:
                yield first, bytes(pending)
                pending.clear()
    if pending:
        yield first, bytes(pending)


class ReplayPacer:
    def __init__(
        self, sample_rate: int, successor: str, socket: Any = None, limits: ReplayLimits | None = None
    ) -> None:
        self.sample_rate = sample_rate
        if limits is None:
            limits = socket_replay_limits(socket, successor)
        self.limits = limits
        self.rate = limits.rate
        self.max_frame_bytes = limits.max_frame_bytes
        self.next_send = clock()
        self.deadline: float | None = None

    async def send(
        self,
        socket: Any,
        data: bytes,
        start: int,
        active: Callable[[], bool],
        *,
        replay: bool,
        admitted: bool = False,
        deadline: float | None = None,
    ) -> bool:
        # Owner departure and death are checked at each bounded packet interval;
        # missed slots never earn burst credit. Cancellation interrupts sleep.
        # ``deadline`` is the packet's absolute live-capture bound; the prefix
        # wall in self.deadline still applies to replay sends.
        packet_deadline = deadline
        if replay and self.deadline is not None:
            packet_deadline = self.deadline if packet_deadline is None else min(packet_deadline, self.deadline)
        while clock() < self.next_send:
            if not active() or socket.is_connection_dead:
                return False
            if packet_deadline is not None:
                remaining = packet_deadline - clock()
                if remaining <= 0:
                    return False
                await sleep(min(self.next_send - clock(), remaining))
            else:
                await sleep(max(0.000001, self.next_send - clock()))
        if not active() or socket.is_connection_dead:
            return False
        if packet_deadline is not None and clock() >= packet_deadline:
            return False
        wait = getattr(socket, 'wait_send_capacity', None)
        if callable(wait):
            wait_timeout = self.limits.queue_wait_seconds
            if packet_deadline is not None:
                wait_timeout = min(wait_timeout, packet_deadline - clock())
                if wait_timeout <= 0:
                    return False
            try:
                capacity = await cast(Callable[..., Awaitable[bool]], wait)(
                    limit=self.limits.queue_packets, timeout=wait_timeout
                )
            except TypeError:
                capacity = await cast(Callable[[], Awaitable[bool]], wait)()
            if not capacity:
                return False
        if not active() or socket.is_connection_dead:
            return False
        if packet_deadline is not None and clock() >= packet_deadline:
            return False
        send = getattr(socket, 'replay_send', None) if replay else None
        token = None
        if not replay and packet_deadline is not None:
            token = audio_send_deadline.set(packet_deadline)
        try:
            if admitted:
                accepted = socket.send_admitted_audio(data, ((start, len(data) // 2),))
            else:
                accepted = send(data, start) if callable(send) else socket.send(data, start_sample=start)
        finally:
            if token is not None:
                audio_send_deadline.reset(token)
        complete = (
            getattr(socket, 'complete_send', None) if getattr(socket, 'idle_close_enabled', False) is True else None
        )
        if accepted is True and callable(complete):
            if packet_deadline is not None:
                async with asyncio.timeout(max(0.0, packet_deadline - clock())):
                    accepted = await cast(Callable[[], Awaitable[bool]], complete)()
            else:
                accepted = await cast(Callable[[], Awaitable[bool]], complete)()
        self.next_send = _next_audio_slot(self.next_send, len(data) / (2 * self.sample_rate * self.rate), clock())
        await sleep(0)
        succeeded = accepted is True and not socket.is_connection_dead
        if succeeded and getattr(socket, 'idle_close_enabled', False) is True:
            socket.commit_send()
        return succeeded


def raw_transport(socket: Any) -> Any:
    """Unwrap ReplayTailSocket/LiveLeg/Gated/Recording layers to the raw
    provider transport owner whose tasks and wire must be aborted."""
    current = socket
    seen: set[int] = set()
    for _ in range(8):
        if current is None or id(current) in seen:
            return current
        seen.add(id(current))
        inner = getattr(current, 'raw', None) or getattr(current, '_conn', None) or getattr(current, 'connection', None)
        if inner is None or inner is current:
            return current
        current = inner
    return current


async def abort_replay_socket(socket: Any, timeout: float = 2.0) -> None:
    """Close a rejected replay leg, including its adapter's tasks and transport.
    ``timeout`` is one total wall bound shared by the task wait and the
    transport close; a spent budget still cancels and attempts an immediate
    abort rather than awaiting a dead provider."""
    deadline = clock() + max(0.0, timeout)
    try:
        socket.finish()
    except Exception as error:
        logger.warning('replay abort finish failed: %s', type(error).__name__)
    try:
        release_live_stt_socket(socket)
    except Exception as error:
        logger.warning('replay abort release failed: %s', type(error).__name__)
    raw = raw_transport(socket)
    abort = getattr(raw, 'abort_transport', None)
    if callable(abort):
        await cast(Callable[[float], Awaitable[None]], abort)(max(0.0, deadline - clock()))
        return
    if hasattr(raw, '_closed'):
        raw._closed = True
    tasks = [
        task
        for name in ('_send_task', '_recv_task', '_pump_task', '_sender_task', '_receiver_task')
        if isinstance((task := getattr(raw, name, None)), asyncio.Task)
    ]
    for task in tasks:
        task.cancel()
    if tasks:
        _, pending = await asyncio.wait(tasks, timeout=max(0.0, deadline - clock()))
        for task in pending:
            task.cancel()
    transport = getattr(raw, '_ws', None)
    if transport is not None:
        remaining = deadline - clock()
        closed = remaining > 0
        if closed:
            try:
                async with asyncio.timeout(remaining):
                    await transport.close()
            except Exception as error:
                logger.warning('replay abort transport close failed: %s', type(error).__name__)
                closed = False
            else:
                closed = getattr(transport, 'closed', True) is not False
        if not closed:
            abort = getattr(transport, 'abort', None)
            if not callable(abort):
                abort = getattr(getattr(transport, 'transport', None), 'abort', None)
            if callable(abort):
                try:
                    abort()
                except Exception as error:
                    logger.warning('replay abort transport abort failed: %s', type(error).__name__)
    queued = getattr(raw, '_send_queue', None)
    if queued is not None:
        try:
            clear = getattr(queued, 'clear', None)
            if callable(clear):
                clear()
            else:
                while True:
                    queued.get_nowait()
        except Exception:
            pass


BIRTH_LEDGER_MAX = 8192


class BirthLedger:
    """Bounded (start, end, born) first-admission intervals for live capture.

    A retry must never reset the live-audio residence clock, so each interval
    stores only its first admission; lookups return the containing interval's
    stamp. The ledger is pruned at every capture cut and coalesces adjacent
    intervals (earliest born wins) when it would exceed the entry bound.
    """

    def __init__(self) -> None:
        self._iv: list[list[Any]] = []
        self._starts: list[int] = []

    def __len__(self) -> int:
        return len(self._iv)

    def note(self, start: int, end: int, born: float | None = None) -> float:
        born = clock() if born is None else born
        if end <= start:
            return born
        i = bisect.bisect_right(self._starts, start) - 1
        if i >= 0 and self._iv[i][1] > start:
            if end > self._iv[i][1]:
                self._iv[i][1] = end
                while i + 1 < len(self._iv) and self._iv[i + 1][0] < end:
                    self._iv[i][1] = max(self._iv[i][1], self._iv[i + 1][1])
                    self._iv[i][2] = min(self._iv[i][2], self._iv[i + 1][2])
                    del self._iv[i + 1]
                    del self._starts[i + 1]
            return self._iv[i][2]
        j = i + 1
        self._iv.insert(j, [start, end, born])
        self._starts.insert(j, start)
        if len(self._iv) > BIRTH_LEDGER_MAX:
            self._coalesce()
        return born

    def lookup(self, sample: int) -> float | None:
        i = bisect.bisect_right(self._starts, sample) - 1
        if i >= 0 and self._iv[i][0] <= sample < self._iv[i][1]:
            return self._iv[i][2]
        return None

    def prune_before(self, sample: int) -> None:
        i = 0
        while i < len(self._iv) and self._iv[i][1] <= sample:
            i += 1
        if i:
            del self._iv[:i]
            del self._starts[:i]
        if self._iv and self._iv[0][0] < sample:
            self._iv[0][0] = sample
            self._starts[0] = sample

    def _coalesce(self) -> None:
        merged: list[list[Any]] = []
        for start, end, born in self._iv:
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
                merged[-1][2] = min(merged[-1][2], born)
            else:
                merged.append([start, end, born])
        while len(merged) > BIRTH_LEDGER_MAX:
            best = min(range(len(merged) - 1), key=lambda i: merged[i + 1][0] - merged[i][1])
            merged[best][1] = merged[best + 1][1]
            merged[best][2] = min(merged[best][2], merged[best + 1][2])
            del merged[best + 1]
        self._iv = merged
        self._starts = [entry[0] for entry in merged]


def bounded_snapshot(
    ring: Any,
    source: str,
    successor: str,
    *,
    rate: float | None = None,
    wall_seconds: float | None = None,
    birth: BirthLedger | None = None,
) -> tuple[tuple[int, bytes], ...]:
    """Keep the newest unanswered AUDIO duration; capture gaps consume no quota.

    Called only after the actual successor is constructed so its declared rate,
    not the requested family's, sizes the retained audio. Live intervals whose
    first admission (``birth`` ledger) is already past the residence bound are
    cut through the same metered policy: everything older than the last expired
    live span is discarded once and the fresh suffix still ships.
    """
    pace = 1.0
    if isinstance(rate, (int, float)) and not isinstance(rate, bool) and 0 < rate <= 1.0:
        pace = float(rate)
    wall = REPLAY_PREFIX_SECONDS if wall_seconds is None else max(0.0, wall_seconds)
    now = clock()
    if birth is not None:
        snapshot = ring.snapshot()
        if snapshot:
            birth.prune_before(snapshot[0][0])
        expired_end = 0
        for start, data in snapshot:
            end = start + len(data) // 2
            born = birth.lookup(start)
            if born is None and end > start:
                born = birth.lookup(end - 1)
            if born is not None and now - born > TAIL_RESIDENCE_SECONDS:
                expired_end = end
        if expired_end:
            dropped = ring.finalize_through(expired_end)
            if dropped:
                REPLAY_SKIPPED.labels(source=source, successor=successor).inc(dropped / (2 * ring.sample_rate))
            birth.prune_before(expired_end)
    remaining = int(min(REPLAY_PREFIX_SECONDS, wall) * pace * ring.sample_rate) * 2
    kept = []
    total = ring.buffered_bytes
    for start, data in reversed(ring.snapshot()):
        count = min(remaining, len(data))
        if count:
            kept.append((start + (len(data) - count) // 2, data[-count:]))
            remaining -= count
        if not remaining:
            break
    kept.reverse()
    skipped = total - sum(len(data) for _, data in kept)
    if skipped:
        REPLAY_SKIPPED.labels(source=source, successor=successor).inc(skipped / (2 * ring.sample_rate))
        # Explicit lossy budget cut, distinct from an emitted-text safe trim.
        ring.finalize_through(kept[0][0] if kept else ring.capture_bounds[1])
    return tuple(kept)


@dataclass
class TailPacket:
    """One live-capture packet held for paced delivery behind a replay prefix."""

    start: int
    data: bytes
    received: float
    admitted: bool = False


class ReplayTailSocket:
    """Keep live input ordered and paced after prefix admission, without a lock.

    The receiver's supervisor owns the tail task. At real-time input, <=26s
    PCM is retained here; overload rejects the leg instead of dropping audio,
    and no accepted packet may wait past the hard residence bound.
    """

    def __init__(
        self,
        socket: Any,
        pacer: ReplayPacer,
        tail: deque[TailPacket],
        host: Any,
        *,
        source: str = 'unknown',
        birth: 'BirthLedger | None' = None,
        retire_interval: Callable[[int], int] | None = None,
        write_wait_seconds: float | None = None,
    ) -> None:
        self.connection, self.pacer, self.tail, self.host = socket, pacer, tail, host
        self._birth = birth
        self._retire_interval = retire_interval
        self._write_wait_seconds = write_wait_seconds
        self._task: asyncio.Task[Any] | None = None
        self._pumping = True
        self._dead = False
        self._local_reason: str | None = None
        self._closing = False
        self._finalize_pending = False
        self._draining = False
        self._pending_write: tuple[Any, int, bytes, Any, int | None] | None = None
        self._tail_bytes = sum(len(packet.data) for packet in tail)
        self.source = source if source in REPLAY_RATES else 'unknown'

    def __getattr__(self, name: str) -> Any:
        return getattr(self.connection, name)

    @property
    def is_connection_dead(self) -> bool:
        return self._dead or self.connection.is_connection_dead

    @property
    def typed_death_reason(self) -> str | None:
        return self._local_reason or self.connection.typed_death_reason

    @property
    def normalized_death_reason(self) -> str:
        return normalize_live_stt_reason(
            self._local_reason,
            getattr(self.connection, 'normalized_death_reason', None),
            self.typed_death_reason,
            getattr(self.connection, 'death_reason', None),
        )

    def mark_capacity_full(self) -> None:
        self._dead = True
        self._local_reason = 'capacity_full'

    def _tail_bound_bytes(self) -> float:
        return LIVE_TAIL_SECONDS * self.pacer.sample_rate * 2

    def _retire_expired(self) -> None:
        """Retire live intervals past the residence bound through the same
        metered cut as a prefix budget cut, then continue with the fresh
        suffix — one expired interval is audio loss, not provider death."""
        now = clock()
        while self.tail and now - self.tail[0].received > TAIL_RESIDENCE_SECONDS:
            expired = self.tail.popleft()
            self._tail_bytes -= len(expired.data)
            end = expired.start + len(expired.data) // 2
            removed = self._retire_interval(end) if self._retire_interval is not None else 0
            dropped = max(len(expired.data), removed)
            if dropped:
                REPLAY_SKIPPED.labels(source=self.source, successor=family(self.connection)).inc(
                    dropped / (2 * self.pacer.sample_rate)
                )
            if self._birth is not None:
                self._birth.prune_before(end)

    def send(self, data: bytes, start_sample: int | None = None) -> bool:
        if self._closing or self.is_connection_dead:
            return False
        if start_sample is None and not self.tail and not self._pumping:
            return self.connection.send(data)
        if start_sample is None:
            start_sample = 0
        self._retire_expired()
        if self._tail_bytes + len(data) > self._tail_bound_bytes():
            self.mark_capacity_full()
            return False
        assert start_sample is not None
        received = self._birth.note(start_sample, start_sample + len(data) // 2) if self._birth is not None else clock()
        self.tail.append(TailPacket(start_sample, data, received))
        self._tail_bytes += len(data)
        if not self._pumping:
            self._start_pump()
        return True

    def send_admitted_audio(self, data: bytes, spans: Any) -> bool:
        # Queue an already gated onset behind every older replay/tail packet.
        # Preserve each capture interval; concatenated pre-roll can have gaps.
        if data and not spans:
            return False  # No capture proof: never accept bytes without queuing them.
        if self._closing or self.is_connection_dead:
            return False
        if self._tail_bytes + len(data) > self._tail_bound_bytes():
            self.mark_capacity_full()
            return False
        offset = 0
        for start, length in spans:
            packet = data[offset * 2 : (offset + length) * 2]
            received = self._birth.note(start, start + length) if self._birth is not None else clock()
            self.tail.append(TailPacket(start, packet, received, admitted=True))
            offset += length
        self._tail_bytes += len(data)
        if not self._pumping:
            self._start_pump()
        return True

    def _start_pump(self) -> None:
        if self._task is not None and self._task.done():
            self._task = None
        if self._task is None:
            self._pumping = True
            self._task = self.host.spawn(self._pump_tail(), name='stt_replay_live_tail')

    def start_tail(self, *, draining: bool = False) -> None:
        self._draining = self._draining or draining
        if self.tail:
            self._start_pump()
        else:
            self._pumping = False

    async def _pump_tail(self) -> None:
        try:
            while self.tail:
                self._retire_expired()
                if not self.tail:
                    break
                entry = self.tail[0]
                expired_mid = False
                for position, packet in replay_packets(
                    ((entry.start, entry.data),), max_frame_bytes=self.pacer.max_frame_bytes
                ):
                    born = self._birth.lookup(position) if self._birth is not None else None
                    packet_deadline = (entry.received if born is None else born) + TAIL_RESIDENCE_SECONDS
                    shutdown_deadline = getattr(getattr(self.host, 'receiver', None), 'shutdown_deadline', None)
                    if shutdown_deadline is not None:
                        packet_deadline = min(packet_deadline, shutdown_deadline)
                    if clock() >= packet_deadline:
                        expired_mid = True
                        break
                    raw = raw_transport(self.connection)
                    queue = getattr(raw, '_send_queue', None)
                    enqueued = getattr(queue, 'enqueued_audio', None)
                    self._pending_write = (
                        entry,
                        position,
                        packet,
                        queue,
                        enqueued + 1 if isinstance(enqueued, int) else None,
                    )
                    if not await self.pacer.send(
                        self.connection,
                        packet,
                        position,
                        self.active,
                        replay=False,
                        admitted=entry.admitted,
                        deadline=packet_deadline,
                    ):
                        self._pending_write = None
                        if clock() >= packet_deadline and not self.connection.is_connection_dead:
                            expired_mid = True
                            break
                        entry.start = position
                        self._dead = True
                        return
                    try:
                        write_deadline = packet_deadline
                        if self._write_wait_seconds is not None:
                            write_deadline = min(write_deadline, clock() + self._write_wait_seconds)
                        confirmed = await await_frozen_writes(self.connection, write_deadline)
                    except asyncio.CancelledError:
                        if not self._closing and not self._debit_pending_write():
                            entry.start = position
                        raise
                    if not confirmed:
                        if not self._debit_pending_write():
                            entry.start = position
                        self._dead = True
                        if clock() < packet_deadline and not self.connection.is_connection_dead:
                            self._local_reason = 'capacity_full'
                        return
                    self._pending_write = None
                    entry.start = position + len(packet) // 2
                    entry.data = entry.data[len(packet) :]
                    self._tail_bytes -= len(packet)
                if expired_mid:
                    end = entry.start + len(entry.data) // 2
                    if self.tail and self.tail[0] is entry:
                        self.tail.popleft()
                    self._tail_bytes -= len(entry.data)
                    removed = self._retire_interval(end) if self._retire_interval is not None else 0
                    dropped = max(len(entry.data), removed)
                    if dropped:
                        REPLAY_SKIPPED.labels(source=self.source, successor=family(self.connection)).inc(
                            dropped / (2 * self.pacer.sample_rate)
                        )
                    if self._birth is not None:
                        self._birth.prune_before(end)
                    continue
                if self.tail and self.tail[0] is entry:
                    self.tail.popleft()
            self._pumping = False
            if self._finalize_pending:
                self.connection.finalize()
        except asyncio.CancelledError:
            raise
        except Exception:
            self._dead = True

    def active(self) -> bool:
        return (
            (self.host.state.active or self._draining)
            and not self._closing
            and not self.host.state.stt_terminal_failure
        )

    def finalize(self) -> None:
        if self._pumping or self.tail:
            self._finalize_pending = True
        else:
            self.connection.finalize()

    def _debit_pending_write(self) -> bool:
        pending = self._pending_write
        if pending is None:
            return False
        entry, position, packet, queue, target = pending
        if isinstance(target, int) and getattr(queue, 'written_audio', 0) >= target:
            entry.start = position + len(packet) // 2
            entry.data = entry.data[len(packet) :]
            self._tail_bytes -= len(packet)
            self._pending_write = None
            return True
        return False

    def finish(self) -> None:
        self._closing = True
        if self._task is not None:
            self._task.cancel()
        try:
            self.connection.finish()
        finally:
            # The receiver tracks the inner connection, not this tail wrapper.
            release_live_stt_socket(self.connection)
        self._debit_pending_write()
        self._pending_write = None
        outcome = getattr(self.connection, 'leg_outcome', None)
        if self.tail and (not self.host.state.active or getattr(outcome, 'owner_closing', False)):
            REPLAY_SKIPPED.labels(source=self.source, successor=family(self.connection)).inc(
                self._tail_bytes / (2 * self.pacer.sample_rate)
            )
        self.tail.clear()
        self._tail_bytes = 0

    def take_tail(self) -> deque[TailPacket]:
        """Transfer unwritten capture before aborting a leg without a replay ring.

        Freeze the pump synchronously so cancellation cannot mutate the handed
        off packets. Confirmed writes are debited; an ambiguous write remains
        owed to the successor. The original capture timestamps stay intact.
        """
        self._closing = True
        if self._task is not None:
            self._task.cancel()
        self._debit_pending_write()
        self._pending_write = None
        while self.tail and not self.tail[0].data:
            self.tail.popleft()
        tail, self.tail = self.tail, deque()
        self._tail_bytes = 0
        return tail

    async def drain_and_close(self) -> None:
        # Accepted tail remains owed after client departure. Drain it before
        # EOS; only cancellation/death/deadline cuts the tail, and finish meters it.
        self._draining = True
        shutdown_deadline = getattr(getattr(self.host, 'receiver', None), 'shutdown_deadline', None)
        try:
            if self._task is not None and not self._task.done() and not self.is_connection_dead:
                budget = LIVE_TAIL_SECONDS + SHUTDOWN_CLEANUP_SECONDS
                if shutdown_deadline is not None:
                    budget = max(0.0, min(budget, shutdown_deadline - clock()))
                _, pending = await asyncio.wait({self._task}, timeout=budget)
                if pending:
                    self.finish()
            if shutdown_deadline is None:
                await self.connection.drain_and_close()
            else:
                cleanup_left = lambda: max(0.0, shutdown_deadline + SHUTDOWN_CLEANUP_SECONDS - clock())
                remaining = shutdown_deadline - clock()
                if remaining > 0:
                    drain = self.host.spawn(self.connection.drain_and_close(), name='stt_shutdown_provider')
                    done, _ = await asyncio.wait({drain}, timeout=remaining)
                    if not done:
                        drain.cancel()
                        _, _ = await asyncio.wait({drain}, timeout=cleanup_left())
                        await abort_replay_socket(self.connection, timeout=cleanup_left())
                else:
                    await abort_replay_socket(self.connection, timeout=cleanup_left())
        finally:
            self.finish()
            if self._task is not None:
                bound = SHUTDOWN_CLEANUP_SECONDS
                if shutdown_deadline is not None:
                    bound = max(0.0, min(bound, shutdown_deadline + SHUTDOWN_CLEANUP_SECONDS - clock()))
                _, _ = await asyncio.wait({self._task}, timeout=bound)
