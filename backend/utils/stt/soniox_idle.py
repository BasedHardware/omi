"""Planned Soniox transport suspension without ending the logical provider leg.

VAD's admitted onset (including its original PCM pre-roll) is held until the
old receive loop has flushed, then the identical connector opens a new socket.
Only provider audio time is rebased; the existing send ledger / WallTimeMapper
still owns capture and wall placement. No recovery episode is opened for idle.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, Awaitable, Callable

from utils.stt.soniox_wire_ledger import capture_spans, observed_audio
from config.soniox_idle import idle_max_closes_per_hour, idle_rearm_seconds
from utils.async_tasks import create_named_task
from utils.stt.socket import STTSocket
from utils.stt.soniox_capture_axis import disable_socket_diagnostics
from utils.stt.replay_delivery import abort_replay_socket
from utils.stt.live_metrics import soniox_idle_metrics
from utils.observability.routing_cohort import current_routing_cohort
from utils.stt.connect_metrics import CONNECT_FAILURE, CONNECT_SUCCESS, record_stt_provider_connect
from utils.stt.live_reason import normalize_live_stt_reason

IDLE_DRAIN_SECONDS = 2.0


class SonioxIdleBudget:
    """Session-owned churn limits, retained through leg rotation/recovery."""

    def __init__(self):
        self.rearm_seconds = idle_rearm_seconds()
        self.max_closes_per_hour = idle_max_closes_per_hour()
        self.rearm_at = 0.0
        self.close_times: deque[float] = deque()

    def reserve_close(self, now: float) -> bool:
        while self.close_times and now - self.close_times[0] >= 3600.0:
            self.close_times.popleft()
        if now < self.rearm_at or len(self.close_times) >= self.max_closes_per_hour:
            return False
        self.close_times.append(now)
        return True


class IdleSonioxSocket(STTSocket):
    idle_close_enabled = True

    def __init__(
        self,
        transport: Any,
        connect: Callable[..., Awaitable[Any]],
        callback: Any,
        rate: int,
        seconds: float,
        *,
        idle_budget: SonioxIdleBudget | None = None,
    ):
        self._transport = transport
        self._connect = connect
        self._callback = callback
        self._rate = rate
        self._seconds = seconds
        self._idle_budget = idle_budget if idle_budget is not None else SonioxIdleBudget()
        self.recovery_enabled = transport.recovery_enabled
        self._finishing = False
        self._closed = False
        self._dead = False
        self.idle_reopen_failed = False
        self._reason: str | None = None
        self._silent_since: float | None = None
        self._idle_since: float | None = None
        self._idle_closed_at: float | None = None
        self._close_task: asyncio.Task[Any] | None = None
        self._reopen_task: asyncio.Task[bool] | None = None
        self._pending = bytearray()
        self._wire_epoch: Any = None
        self._pending_spans: list[tuple[int, int]] = []
        self._pending_unknown = False
        self._resumed_audio = b''
        self._resume_offset: float | None = None
        self._admitted_samples = 0
        self._routing_cohort = current_routing_cohort.get()
        self._metrics = soniox_idle_metrics()
        self._writer_pacing: tuple[Any, ...] | None = None
        self._socket_epoch = 0
        self._last_end = 0.0
        self._capture_axis_ledger: Callable[[], int | None] | None = None
        transport._stream_transcript = self._socket_callback(0.0, 0)

    def set_wire_ledger(self, epoch: Any) -> None:
        self._wire_epoch = epoch
        self._transport.set_wire_ledger(epoch)

    def set_capture_axis_ledger(self, ledger: Callable[[], int | None]) -> None:
        self._capture_axis_ledger = ledger
        try:
            self._transport.set_capture_axis_ledger(ledger)
        except Exception:
            disable_socket_diagnostics(self._transport)

    def disable_capture_axis_diagnostics(self) -> None:
        disable_socket_diagnostics(self._transport)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._transport, name)

    @property
    def is_connection_dead(self) -> bool:
        return self._dead or self._transport.is_connection_dead

    @property
    def death_reason(self) -> str | None:
        return self._reason or self._transport.death_reason

    @property
    def typed_death_reason(self) -> str | None:
        return self._reason or self._transport.typed_death_reason

    def observe_vad(self, output: Any, mode: str) -> None:
        if mode != 'active' or self._finishing or self.is_connection_dead:
            return
        now = time.monotonic()
        if output.is_speech:
            self._silent_since = None
        elif self._silent_since is None:
            self._silent_since = now
        elif not output.audio_to_send and self._idle_since is None and now - self._silent_since >= self._seconds:
            if not self._idle_budget.reserve_close(now):
                return
            # Reserve before scheduling so repeated VAD callbacks cannot spend
            # the same rolling-hour slot. These limits belong to the logical
            # session and survive each replacement transport.
            # Fence death publication before any await. The logical leg stays
            # alive while the paid transport finishes its last committed text.
            self._transport._planned_close = True
            self._idle_since = now
            self._close_task = create_named_task(self._close_idle(), name='soniox_idle_close')

    async def _close_idle(self) -> None:
        transport = self._transport
        transport.finalize()
        task = create_named_task(transport.drain_and_close(), name='soniox_idle_drain')
        try:
            done, _ = await asyncio.wait({task}, timeout=IDLE_DRAIN_SECONDS)
            if not done:
                task.cancel()
                await abort_replay_socket(transport, timeout=0.5)
                task.cancel()
                await asyncio.wait({task}, timeout=0.25)
        finally:
            if not task.done():
                task.cancel()
                await abort_replay_socket(transport, timeout=0.5)
            if task.done() and not task.cancelled():
                task.exception()
            # Avoided time starts only after the transport is actually closed.
            self._idle_closed_at = time.monotonic()
            self._metrics.closes.inc()

    def send(self, data: bytes, start_sample: int | None = None) -> bool:
        if self._finishing or self.is_connection_dead:
            return False
        if self._idle_since is not None:
            # The serving send boundary awaits complete_send before accepting
            # this frame. Retain at most ten seconds, including VAD pre-roll.
            if len(self._pending) + len(data) > self._rate * 2 * 10:
                self._dead, self._reason = True, 'capacity_full'
                return False
            self._pending.extend(data)
            if self._wire_epoch is not None:
                audio = observed_audio(data, self._wire_epoch, capture_spans.get())
                self._pending_unknown |= not bool(audio.spans)
                self._pending_spans.extend(audio.spans)
            return True
        accepted = self._transport.send(data)
        if accepted:
            self._admitted_samples += len(data) // 2
            if self._routing_cohort is not None:
                self._routing_cohort.paid_audio('soniox', len(data) / (self._rate * 2))
        return accepted

    async def complete_send(self) -> bool:
        if not self._pending:
            return not self.is_connection_dead
        if self._reopen_task is None or self._reopen_task.done():
            self._reopen_task = create_named_task(self._resume(), name='soniox_idle_reopen')
        return await self._reopen_task

    async def _resume(self) -> bool:
        started = time.monotonic()
        if self._close_task is not None:
            await self._close_task
            self._close_task = None
        if self._finishing:
            return False
        self._account_avoided()
        if self._wire_epoch is not None:
            # complete_send can run before the old writer finishes its queue.
            # Freeze the replacement origin only after the old drain above.
            offset = (self._wire_epoch.wire_provider_samples or 0) / self._rate
        else:
            offset = self._resume_offset if self._resume_offset is not None else self._admitted_samples / self._rate
        self._resume_offset = None

        self._socket_epoch += 1
        callback = self._socket_callback(offset, self._socket_epoch)

        try:
            self._transport = await self._connect(callback)
            if self._wire_epoch is not None:
                self._transport.set_wire_ledger(self._wire_epoch)
            if self._capture_axis_ledger is not None:
                try:
                    self._transport.set_capture_axis_ledger(
                        self._capture_axis_ledger,
                        (
                            (self._wire_epoch.wire_audio_samples or 0)
                            if self._wire_epoch is not None
                            else round(offset * self._rate)
                        ),
                        'reopened',
                    )
                except Exception:
                    disable_socket_diagnostics(self._transport)
            if self._writer_pacing is not None:
                self._transport.enable_writer_pacing(*self._writer_pacing)
            if self._transport.is_connection_dead:
                self._reason = normalize_live_stt_reason(
                    self._transport.typed_death_reason, self._transport.death_reason
                )
                raise RuntimeError('Soniox rejected reopened transport')
            if self._finishing:
                await abort_replay_socket(self._transport)
                return False
            self._idle_budget.rearm_at = time.monotonic() + self._idle_budget.rearm_seconds
            self._idle_since = None
            self._idle_closed_at = None
            data = bytes(self._pending)
            self._pending.clear()
            token = capture_spans.set(() if self._pending_unknown else tuple(self._pending_spans))
            try:
                accepted = self.send(data)
            finally:
                capture_spans.reset(token)
            self._pending_spans.clear()
            self._pending_unknown = False
            if not accepted:
                self._pending.extend(data)
            if accepted:
                self._resumed_audio = data
                self._metrics.reopens.inc()
                record_stt_provider_connect(provider='soniox', outcome=CONNECT_SUCCESS)
            return accepted
        except asyncio.CancelledError:
            await abort_replay_socket(self._transport)
            raise
        except Exception as error:
            from utils.stt.live_chain import failure_reason

            self._metrics.failures.inc()
            self._dead = True
            self._reason = normalize_live_stt_reason(self._reason, failure_reason(error), default='other')
            self.idle_reopen_failed = True
            record_stt_provider_connect(provider='soniox', outcome=CONNECT_FAILURE, reason=self._reason)
            return False
        finally:
            self._metrics.latency.observe(time.monotonic() - started)

    def _socket_callback(self, offset: float, epoch: int) -> Any:
        def callback(segments: list[dict[str, Any]]) -> None:
            segments.sort(key=lambda segment: segment['start'])
            for segment in segments:
                native_start, native_end = segment['start'] + offset, segment['end'] + offset
                visible_start = max(self._last_end, native_start)
                visible_end = max(visible_start, native_end)
                self._last_end = visible_end
                if self._wire_epoch is not None:
                    # Capture containment must see the complete native interval.
                    # A stale old endpoint can clip a cross-gap token entirely
                    # into a later span. Restore the legacy visible clamp only
                    # after translation has decided capture placement.
                    segment['start'], segment['end'] = native_start, native_end
                    segment['_provider_visible_times'] = (visible_start, visible_end)
                else:
                    segment['start'], segment['end'] = visible_start, visible_end
                segment['_provider_socket_epoch'] = epoch
                ranges = segment.get('_provider_word_ranges')
                if ranges:
                    segment['_provider_word_ranges'] = [(a + offset, b + offset) for a, b in ranges]
            self._callback(segments)

        return callback

    def take_unsent_audio(self) -> bytes:
        data = bytes(self._pending) or self._resumed_audio
        self._pending.clear()
        self._pending_spans.clear()
        self._pending_unknown = False
        self._resumed_audio = b''
        return data

    def set_resume_provider_offset(self, sample: int) -> None:
        if self._idle_since is not None and self._pending:
            self._resume_offset = sample / self._rate

    def commit_send(self) -> None:
        # Release only after the serving boundary has checked the death latch.
        self._resumed_audio = b''

    def _account_avoided(self) -> None:
        if self._idle_closed_at is not None:
            self._metrics.avoided.inc(max(0.0, time.monotonic() - self._idle_closed_at))
            self._idle_closed_at = time.monotonic()

    def enable_writer_pacing(self, *args: Any) -> None:
        self._writer_pacing = args
        self._transport.enable_writer_pacing(*args)

    async def wait_send_capacity(self, **kwargs: Any) -> bool:
        if self._idle_since is not None:
            return not self._dead
        return await self._transport.wait_send_capacity(**kwargs)

    def finalize(self) -> None:
        if self._idle_since is None:
            self._transport.finalize()

    def finish(self) -> None:
        if self._finishing:
            return
        self._finishing = True
        if self._reopen_task is not None and not self._reopen_task.done():
            self._reopen_task.cancel()
        self._account_avoided()
        if self._idle_since is None:
            self._transport.finish()

    async def drain_and_close(self) -> None:
        self.finish()
        if self._reopen_task is not None:
            await asyncio.gather(self._reopen_task, return_exceptions=True)
        if self._close_task is not None:
            await self._close_task
            self._close_task = None
        elif self._idle_since is None:
            await self._transport.drain_and_close()
        self._account_avoided()
        self._closed = True

    async def abort_transport(self, timeout: float) -> None:
        self.finish()
        deadline = time.monotonic() + max(0.0, timeout)
        tasks = [task for task in (self._close_task, self._reopen_task) if task is not None]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=max(0.0, deadline - time.monotonic()))
        await abort_replay_socket(self._transport, timeout=max(0.0, deadline - time.monotonic()))
        self._closed = True


def unaccepted_onset(data: bytes, spans: Any, tracker: Any) -> tuple[bytes, tuple[tuple[int, int], ...]]:
    """Exclude only capture prefixes proven accepted by a successor's replay."""
    if tracker is None or not spans:
        return data, tuple(spans)
    ledger = tracker.send_map
    boundary = ledger.last_capture_sample or 0
    pieces = []
    remaining = []
    offset = 0
    for start, length in spans:
        cut = min(length, max(0, boundary - start))
        if ledger.accepted_samples_in_capture_range(start, start + cut) != cut:
            cut = 0
        if cut < length:
            pieces.append(data[(offset + cut) * 2 : (offset + length) * 2])
            remaining.append((start + cut, length - cut))
        offset += length
    return b''.join(pieces), tuple(remaining)
