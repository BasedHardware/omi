"""Audio-time pacing and bounded, ordered live delivery behind a replay prefix."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, Awaitable, Callable, cast

REPLAY_WALL_BUDGET = 25.0
REPLAY_CONNECT_SECONDS = 5.0
REPLAY_PREFIX_SECONDS = REPLAY_WALL_BUDGET - REPLAY_CONNECT_SECONDS
LIVE_TAIL_SECONDS = REPLAY_WALL_BUDGET + 1.0
# Adapter-owned limits, deliberately not routing configuration. There is no
# documented accelerated-stream ceiling for these adapters; use real time.
REPLAY_RATES = {'soniox': 1.0, 'modulate': 1.0, 'deepgram': 1.0, 'parakeet': 1.0}
clock = time.monotonic
sleep = asyncio.sleep


def family(socket: Any, fallback: str = 'unknown') -> str:
    service = getattr(socket, 'service', None)
    name = getattr(service, 'value', service)
    if name in REPLAY_RATES:
        return name
    raw = getattr(socket, 'raw', socket)
    name = type(raw).__name__.lower()
    return next((key for key in REPLAY_RATES if key in name), fallback if fallback in REPLAY_RATES else 'unknown')


class ReplayPacer:
    def __init__(self, sample_rate: int, successor: str, socket: Any = None) -> None:
        self.sample_rate = sample_rate
        declared = getattr(socket, 'max_replay_rate', REPLAY_RATES.get(successor, 1.0))
        self.rate = float(declared) if type(declared) in (float, int) and 0 < declared <= 1.0 else 1.0
        self.next_send = clock()

    async def send(self, socket: Any, data: bytes, start: int, active: Callable[[], bool], *, replay: bool) -> bool:
        # Owner departure and death are checked at each bounded packet interval;
        # missed slots never earn burst credit. Cancellation interrupts sleep.
        while clock() < self.next_send:
            if not active() or socket.is_connection_dead:
                return False
            await sleep(max(0.000001, self.next_send - clock()))
        if not active() or socket.is_connection_dead:
            return False
        wait = getattr(socket, 'wait_send_capacity', None)
        if callable(wait) and not await cast(Callable[[], Awaitable[bool]], wait)():
            return False
        if not active() or socket.is_connection_dead:
            return False
        send = getattr(socket, 'replay_send', None) if replay else None
        accepted = send(data, start) if callable(send) else socket.send(data, start_sample=start)
        self.next_send = clock() + len(data) / (2 * self.sample_rate * self.rate)
        await sleep(0)
        return accepted is True and not socket.is_connection_dead


async def abort_replay_socket(socket: Any) -> None:
    """Close a rejected replay leg, including its adapter's receive task."""
    socket.finish()
    raw = getattr(socket, 'raw', socket)
    if hasattr(raw, '_closed'):
        raw._closed = True
    tasks = [
        task for name in ('_send_task', '_recv_task') if isinstance((task := getattr(raw, name, None)), asyncio.Task)
    ]
    for task in tasks:
        task.cancel()
    if tasks:
        # Bound cancellation even if a transport suppresses CancelledError.
        _, pending = await asyncio.wait(tasks, timeout=2.0)
        for task in pending:
            task.cancel()
        transport = getattr(raw, '_ws', None)
        if transport is not None:
            try:
                async with asyncio.timeout(2.0):
                    await transport.close()
            except (TimeoutError, OSError):
                pass


def bounded_snapshot(ring: Any, source: str, successor: str) -> tuple[tuple[int, bytes], ...]:
    """Keep the newest unanswered AUDIO duration; capture gaps consume no quota."""
    from utils.stt.live_metrics import REPLAY_SKIPPED

    remaining = int(REPLAY_PREFIX_SECONDS * REPLAY_RATES.get(successor, 1.0) * ring.sample_rate) * 2
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
        ring.finalize_through(kept[0][0])
    return tuple(kept)


class ReplayTailSocket:
    """Keep live input ordered and paced after prefix admission, without a lock.

    The receiver's supervisor owns the tail task. At real-time input, <=26s
    PCM is retained here; overload rejects the leg instead of dropping audio.
    """

    def __init__(self, socket: Any, pacer: ReplayPacer, tail: deque[tuple[int, bytes]], host: Any) -> None:
        self.connection, self.pacer, self.tail, self.host = socket, pacer, tail, host
        self._task: asyncio.Task[Any] | None = None
        self._pumping = True
        self._dead = False
        self._local_reason: str | None = None
        self._closing = False
        self._finalize_pending = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self.connection, name)

    @property
    def is_connection_dead(self) -> bool:
        return self._dead or self.connection.is_connection_dead

    @property
    def typed_death_reason(self) -> str | None:
        return self._local_reason or self.connection.typed_death_reason

    def send(self, data: bytes, start_sample: int | None = None) -> bool:
        if self._closing or self.is_connection_dead:
            return False
        if not self._pumping:
            return self.connection.send(data, start_sample=start_sample)
        if sum(len(chunk) for _, chunk in self.tail) + len(data) > LIVE_TAIL_SECONDS * self.pacer.sample_rate * 2:
            self._dead = True
            self._local_reason = 'capacity_full'
            return False
        assert start_sample is not None
        self.tail.append((start_sample, data))
        return True

    def start_tail(self) -> None:
        if self.tail:
            self._task = self.host.spawn(self._pump_tail(), name='stt_replay_live_tail')
        else:
            self._pumping = False

    async def _pump_tail(self) -> None:
        from utils.stt.resilient_stream import replay_packets

        try:
            while self.tail:
                start, data = self.tail[0]
                for position, packet in replay_packets(((start, data),)):
                    if not await self.pacer.send(self.connection, packet, position, self.active, replay=False):
                        self._dead = True
                        return
                self.tail.popleft()
            self._pumping = False
            if self._finalize_pending:
                self.connection.finalize()
        except asyncio.CancelledError:
            raise
        except Exception:
            self._dead = True

    def active(self) -> bool:
        return self.host.state.active and not self._closing and not self.host.state.stt_terminal_failure

    def finalize(self) -> None:
        if self._pumping:
            self._finalize_pending = True
        else:
            self.connection.finalize()

    def finish(self) -> None:
        self._closing = True
        if self._task is not None:
            self._task.cancel()
        self.connection.finish()
        self.tail.clear()

    async def drain_and_close(self) -> None:
        # A disconnected owner cannot wait a replay-lag duration for live tail.
        self.finish()
        if self._task is not None:
            await asyncio.gather(self._task, return_exceptions=True)
        await self.connection.drain_and_close()
