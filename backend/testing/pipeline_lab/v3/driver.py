"""The v3 day as a discrete-event simulation on the lab's virtual clock.

Events, earliest first (ties: arrival, then task, then sweep):

- **arrival**: a recording's speech lands. The driver seeds it as a fresh capture end and runs
  the real durable finalization; for a recording that ends in ``recording_short_path``, which
  completes it and calls ``triggers.changed`` (mark pending + enqueue a reconcile task).
- **task**: a named Cloud Task the product enqueued (``LoopbackTasks``) comes due: the
  reconcile route's handler body (``service.reconcile(uid)``) runs: outline, plan, commit,
  notes drain (``process_conversation`` per finished window), conversation-created delivery.
- **sweep**: Cloud Scheduler's ``*/5`` UTC sweep (``service.sweep()``), simulated only while
  the owner has pending markers, as production's would be a no-op otherwise.

The virtual clock never moves backwards: an event due earlier than "now" (work took real time
on a ticking clock) runs at "now", exactly as a late Cloud Task would. The loop ends when no
task is due before the horizon and nothing is pending, or at ``max_events``.

Product calls go through the small :class:`V3Ops` protocol, so the loop is unit-tested with
fakes; ``v3/product.py`` holds the real implementation.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
import logging
import time
import traceback
from typing import Any, Callable, Optional, Protocol, Sequence

from testing.pipeline_lab.v3.feed import Arrival
from testing.pipeline_lab.v3.tasks import RECONCILE_PATH, LoopbackTasks

SWEEP_EVERY = timedelta(minutes=5)


class _SizeNotes(logging.Handler):
    """Keep the product's own size warning (kind and byte counts; it never logs ids or content)."""

    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        if str(record.msg).startswith('v3 projection write too large'):
            self.lines.append(record.getMessage())


class V3Ops(Protocol):
    async def arrive(self, uid: str, arrival: Arrival) -> dict[str, Any]: ...

    async def reconcile(self, uid: str) -> str: ...

    async def sweep(self) -> int: ...

    def pending(self, uid: str) -> bool: ...

    async def settle(self) -> dict[str, Any]: ...


class Clock(Protocol):
    def set(self, instant: datetime) -> None: ...

    def now(self) -> datetime: ...


@dataclass
class V3Event:
    at: str
    kind: str  # arrival | task | sweep
    ref: str  # recording id, task name or 'sweep'
    outcome: str = ''
    error: Optional[str] = None
    seconds: float = 0.0
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v not in (None, {}, '')}


@dataclass
class V3Report:
    events: list[V3Event] = field(default_factory=list)
    seconds: float = 0.0
    stopped: str = 'drained'
    warnings: list[str] = field(default_factory=list)

    def counts(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for event in self.events:
            bucket = out.setdefault(event.kind, {})
            bucket[event.outcome or 'ok'] = bucket.get(event.outcome or 'ok', 0) + 1
        return out

    def summary(self) -> dict[str, Any]:
        failed = sum(1 for e in self.events if e.outcome == 'error')
        return {
            'status': 'failed' if failed and failed == len(self.events) else ('partial' if failed else 'ok'),
            'events': len(self.events),
            'failed': failed,
            'counts': self.counts(),
            'stopped': self.stopped,
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            'summary': self.summary(),
            'seconds': round(self.seconds, 3),
            'warnings': self.warnings,
            'events': [e.as_dict() for e in self.events],
        }


def next_sweep(after: datetime, every: timedelta = SWEEP_EVERY) -> datetime:
    """The first ``*/5`` UTC grid instant strictly after ``after``."""
    step = every.total_seconds()
    epoch = after.timestamp()
    return datetime.fromtimestamp((epoch // step + 1) * step, timezone.utc)


class V3Driver:
    def __init__(
        self,
        *,
        uid: str,
        ops: V3Ops,
        tasks: LoopbackTasks,
        clock: Clock,
        horizon: datetime,
        max_events: int = 20000,
        sweeps: bool = True,
        on_event: Optional[Callable[[V3Event], None]] = None,
    ):
        self.uid = uid
        self.ops = ops
        self.tasks = tasks
        self.clock = clock
        self.horizon = horizon
        self.max_events = max_events
        self.sweeps = sweeps
        self.on_event = on_event

    def _advance(self, due: datetime) -> datetime:
        now = self.clock.now()
        target = due if due > now else now
        self.clock.set(target)
        return target

    async def _run(self, event: V3Event, work: Callable[[], Any]) -> None:
        started = time.monotonic()
        notes = _SizeNotes()
        logging.getLogger().addHandler(notes)
        try:
            result = await work()
            if isinstance(result, dict):
                event.outcome = str(result.pop('outcome', 'ok'))
                event.detail.update(result)
            else:
                event.outcome = str(result) if result is not None else 'ok'
            settled = await self.ops.settle()
            if settled.get('left'):
                event.detail['left_running'] = settled['left']
        except Exception as error:  # noqa: BLE001 - one failed event must not hide the rest of the day
            event.outcome = 'error'
            event.error = type(error).__name__
            # Where it failed (file:line function), never the message: messages can carry owner data.
            frames = traceback.extract_tb(error.__traceback__)
            own = [f for f in frames if 'site-packages' not in f.filename and 'testing/pipeline_lab' not in f.filename]
            event.detail['where'] = [f'{Path(f.filename).name}:{f.lineno} {f.name}' for f in (own[-6:] + frames[-2:])]
            # The exception class's own words are code, not owner data (e.g. "document too large").
            event.detail['kind'] = type(error).__module__ + '.' + type(error).__qualname__
            if type(error).__module__.startswith('google.api_core'):
                # Storage errors describe the request ("transaction too big"); quoted values are dropped.
                import re

                event.detail['reason'] = re.sub(r'"[^"]*"|\'[^\']*\'', '…', str(getattr(error, 'message', '')))[:200]
            if notes.lines:
                event.detail['too_large'] = notes.lines[-3:]
        finally:
            logging.getLogger().removeHandler(notes)
        event.seconds = round(time.monotonic() - started, 3)

    async def run(self, arrivals: Sequence[Arrival]) -> V3Report:
        report = V3Report()
        started = time.monotonic()
        queue = list(arrivals)
        index = 0
        sweep_at: Optional[datetime] = None
        while len(report.events) < self.max_events:
            candidates: list[tuple[datetime, int, str]] = []
            if index < len(queue):
                candidates.append((queue[index].instant, 0, 'arrival'))
            due = self.tasks.next_due()
            if due is not None:
                candidates.append((datetime.fromtimestamp(due, timezone.utc), 1, 'task'))
            if self.sweeps and sweep_at is not None:
                candidates.append((sweep_at, 2, 'sweep'))
            candidates = [c for c in candidates if c[2] == 'arrival' or c[0] <= self.horizon]
            if not candidates:
                break
            at, _, kind = min(candidates, key=lambda c: (c[0], c[1]))
            now = self._advance(at)
            if kind == 'arrival':
                arrival = queue[index]
                index += 1
                event = V3Event(at=now.isoformat(), kind='arrival', ref=arrival.recording_id)
                event.detail['instant_source'] = arrival.instant_source
                await self._run(event, lambda: self.ops.arrive(self.uid, arrival))
            elif kind == 'task':
                task = self.tasks.pop_due(now.timestamp())
                if task is None:  # pragma: no cover - next_due said otherwise; re-plan
                    continue
                event = V3Event(at=now.isoformat(), kind='task', ref=task.name)
                if task.path == RECONCILE_PATH and task.payload.get('uid') == self.uid:
                    await self._run(event, lambda: self.ops.reconcile(self.uid))
                else:
                    event.outcome = 'unsupported'
                    event.detail['path'] = task.path
                    report.warnings.append(f'task {task.path} not run by the v3 replay')
            else:
                event = V3Event(at=now.isoformat(), kind='sweep', ref='sweep')
                await self._run(event, self.ops.sweep)
                sweep_at = None
            report.events.append(event)
            if self.on_event is not None:
                self.on_event(event)
            if self.sweeps:
                pending = await asyncio.to_thread(self.ops.pending, self.uid)
                sweep_at = next_sweep(self.clock.now()) if pending else None
        else:
            report.stopped = 'max_events'
            report.warnings.append(f'stopped after {self.max_events} events')
        if self.tasks.pending():
            report.warnings.append(f'{self.tasks.pending()} tasks were due after the horizon and did not run')
        report.seconds = time.monotonic() - started
        return report


def default_horizon(arrivals: Sequence[Arrival], day_end: datetime, tail: timedelta = timedelta(hours=2)) -> datetime:
    last = max([a.instant for a in arrivals] + [day_end])
    return last + tail
