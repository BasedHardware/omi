"""Bounded, identity-free admission aggregates. Never used for scheduling.

Origins survive both request coalescing boundaries as a bitmask. Launch triggers
are exclusive; origin masks are not exclusive sources. Timings are wall time,
including overlapping work, never CPU or billed cost. No IO except summary logs.
"""

from collections import Counter
from contextvars import ContextVar
from dataclasses import dataclass, field
import json
import logging
import time

logger = logging.getLogger(__name__)
MAX_OWNERS = 1024
MAX_CELLS = 256
INTERVAL_SECONDS = 60
ORIGINS = {
    'unknown': 1,
    'discovery_after_assignment': 2,
    'predecessor_replay': 4,
    'targeted_wake': 8,
    'internal_retry': 16,
}
TRIGGERS = frozenset({'external', 'continuation', 'again', 'retry'})
STOPS = frozenset(
    {
        'end',
        'turn_deadline',
        'yield',
        'claim_busy',
        'claim_held',
        'privacy_unchanged',
        'privacy_blocked',
        'blocked_privacy',
        'head_awaiting_live_target',
        'head_error',
        'prefetch_wait',
        'error',
        'cancelled',
        'other',
    }
)
TIMINGS = ('admission', 'executor_wait', 'claim_check', 'claim_acquire', 'prefetch_wait')
BUCKETS_MS = (1, 10, 100, 1000, 10000)


def origin_mask(reason: str) -> int:
    return ORIGINS.get(reason, ORIGINS['unknown'])


@dataclass
class Turn:
    trigger: str
    origins: int
    started: float = field(default_factory=time.monotonic)
    advanced: int = 0
    steps: int = 0
    stop: str = 'error'
    executed: bool = False
    timings: dict = field(default_factory=dict)

    def elapsed(self, name, seconds):
        if name in TIMINGS:
            self.timings[name] = self.timings.get(name, 0.0) + max(0.0, seconds)


CURRENT_TURN: ContextVar[Turn | None] = ContextVar('projection_drain_diagnostic_turn', default=None)


def observe(name, fn, *args, **kwargs):
    """Observe an existing synchronous call only in an instrumented admission."""
    turn = CURRENT_TURN.get()
    if turn is None:
        return fn(*args, **kwargs)
    started = time.monotonic()
    try:
        return fn(*args, **kwargs)
    finally:
        turn.elapsed(name, time.monotonic() - started)


def worker_call(queued, fn, *args, **kwargs):
    turn = CURRENT_TURN.get()
    if turn is not None:
        turn.elapsed('executor_wait', time.monotonic() - queued)
    return fn(*args, **kwargs)


class Diagnostics:
    def __init__(self):
        self.pending: dict[str, tuple[str, int]] = {}
        self.active: dict[str, Turn] = {}
        self.counts = Counter()
        self.cells: dict[tuple, dict] = {}
        self.last_flush = time.monotonic()

    def request(self, owner, mask, disposition):
        self.counts['requests'] += 1
        self.counts[disposition] += 1
        if disposition != 'deferred':
            self.queue(
                owner,
                'again' if disposition == 'active' else 'external',
                mask,
                external_wake=disposition == 'queued' and mask != ORIGINS['internal_retry'],
            )

    def queue(self, owner, trigger, mask=0, *, external_wake=False):
        mask &= 31
        previous = self.pending.get(owner)
        if previous is None and len(self.pending) >= MAX_OWNERS:
            self.counts['owner_overflow'] += 1
            return
        # Productive continuation wins over a concurrent re-request, as in finished().
        if previous:
            mask |= previous[1]
            if trigger == 'external' and not external_wake:
                trigger = previous[0]
        self.pending[owner] = (trigger, mask)

    def requeue(self, owner, trigger):
        active = self.active.get(owner)
        self.queue(owner, trigger, active.origins if active else ORIGINS['internal_retry'])

    def begin(self, owner):
        trigger, mask = self.pending.pop(owner, ('external', ORIGINS['unknown']))
        turn = Turn(trigger if trigger in TRIGGERS else 'external', mask or ORIGINS['unknown'])
        self.active[owner] = turn  # bounded by MAX_OWNER_DRAINS, not backlog size
        return turn

    def finish(self, owner, stop=None, *, cancelled=False, failed=False, flush=True):
        turn = self.active.pop(owner, None)
        if turn is None:
            return
        stop = 'cancelled' if cancelled else 'error' if failed else stop or turn.stop
        if stop.startswith('blocked_privacy_'):
            stop = 'blocked_privacy'
        stop = stop if stop in STOPS else 'other'
        key = (turn.trigger, turn.origins, int(turn.advanced > 0), stop, turn.executed)
        self.counts['completed'] += 1
        if key not in self.cells and len(self.cells) >= MAX_CELLS:
            self.counts['cell_overflow'] += 1
        else:
            cell = self.cells.setdefault(key, {'n': 0, 'rows': 0, 'steps': 0, 'timing_ms': {}, 'timing_buckets': {}})
            cell['n'] += 1
            cell['rows'] += turn.advanced
            cell['steps'] += turn.steps
            turn.elapsed('admission', time.monotonic() - turn.started)
            for name, seconds in list(turn.timings.items()):
                ms = seconds * 1000
                cell['timing_ms'][name] = cell['timing_ms'].get(name, 0) + int(ms)
                buckets = cell['timing_buckets'].setdefault(name, [0] * (len(BUCKETS_MS) + 1))
                buckets[sum(ms > bound for bound in BUCKETS_MS)] += 1
        if flush and time.monotonic() - self.last_flush >= INTERVAL_SECONDS:
            self.flush()

    def flush(self):
        if not self.counts and not self.cells:
            return
        payload = {
            'window_ms': int((time.monotonic() - self.last_flush) * 1000),
            'counts': dict(self.counts),
            'cells': [
                dict(trigger=k[0], origins=k[1], positive=k[2], stop=k[3], executed=k[4], **v)
                for k, v in self.cells.items()
            ],
        }
        try:
            logger.info(
                'event=batch_projection action=admission_diagnostics aggregate=%s',
                json.dumps(payload, separators=(',', ':')),
            )
        except Exception:
            # A diagnostic sink must never interrupt finished() and strand wakes.
            self.last_flush = time.monotonic()
            self.counts['sink_failures'] += 1
            return
        self.cells.clear()
        self.counts.clear()
        self.last_flush = time.monotonic()

    def close(self):
        self.pending.clear()
        self.active.clear()
        # No shutdown IO or awaited flush: the incomplete final window may be lost.
        self.cells.clear()
        self.counts.clear()
