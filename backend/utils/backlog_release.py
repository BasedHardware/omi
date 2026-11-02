"""May this automatic release take its next recording now, and at what priority?

Manual choices never come here. A trial's first ``PRIORITY_HOURS`` run at normal backfill
priority; everything else waits for idle GPUs at DEEP. Both spend the owner's daily limit
and the fleet budgets. Every failure answers no: the audio stays held and the next sweep asks again.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import time
from threading import Lock
from typing import Any, Callable

from config.backlog_release import (
    IDLE_MAX_DEEP_READY,
    IDLE_MAX_FRESH_RECENT_READY,
    IDLE_SAMPLE_MAX_AGE_SECONDS,
    IDLE_SAMPLE_SECONDS,
    OWNER_HOURS_PER_DAY,
    enabled,
)
from config.batch_pipeline import Priority
from config.rate_card import recording_units_per_hour

logger = logging.getLogger(__name__)

# Set around one admission attempt; admit_held reads them to pick the batch priority and to
# tag the batch rows, so hard-3 and the 2h alarm can tell released backfill from fresh audio.
normal_priority: contextvars.ContextVar[bool] = contextvars.ContextVar('backlog_release_normal_priority', default=False)
SOURCES = ('trial', 'conversion')
source: contextvars.ContextVar[str | None] = contextvars.ContextVar('backlog_release_source', default=None)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    normal_priority: bool = False
    updates: dict = field(default_factory=dict)


class IdleGate:
    """Counts the HPA's own ready units. No sample, or a stale one, reads as not idle."""

    def __init__(self, count: Callable[[int, float], int], *, clock: Callable[[], float] = time.time) -> None:
        self._count = count
        self._clock = clock
        self._lock = Lock()
        self._sampled_at = float('-inf')
        self._answer = False

    def idle(self) -> bool:
        now = self._clock()
        with self._lock:
            if now - self._sampled_at < IDLE_SAMPLE_SECONDS:
                return self._answer
        try:
            ahead = self._count(int(Priority.FRESH), now) + self._count(int(Priority.RECENT), now)
            deep = self._count(int(Priority.DEEP), now)
            answer = ahead < IDLE_MAX_FRESH_RECENT_READY and deep < IDLE_MAX_DEEP_READY
        except Exception as error:
            logger.warning('event=backlog_release_idle outcome=unavailable exception_type=%s', type(error).__name__)
            with self._lock:
                return self._answer and now - self._sampled_at < IDLE_SAMPLE_MAX_AGE_SECONDS
        with self._lock:
            self._answer, self._sampled_at = answer, now
        return answer


_gate: IdleGate | None = None


def idle() -> bool:
    global _gate
    try:
        if _gate is None:
            from database.batch_pipeline_store import FirestoreStore
            from utils.sync.stage import current_stage

            _gate = IdleGate(FirestoreStore(f'batch_pipeline_{current_stage()}').ready_for_capacity)
        return _gate.idle()
    except Exception as error:
        logger.warning('event=backlog_release_idle outcome=unavailable exception_type=%s', type(error).__name__)
        return False


def _reserve_fleet(seconds: float) -> bool:
    from database import backlog_release_budget

    return backlog_release_budget.reserve(seconds)


def batch_serves(uid: str) -> bool:
    """Held audio reaches the batch GPUs only once legacy sync is off for this owner.

    While legacy serves the owner, a hold recovers on the live Parakeet pool or a
    vendor, which the idle gate cannot see, so an automatic release waits instead.
    """
    from utils.sync import legacy_dark

    return legacy_dark.current_mode(uid) is not legacy_dark.LegacySyncMode.ON


def decide(
    uid: str,
    job: dict[str, Any],
    units: float,
    *,
    kind: str = 'audio',
    now: float | None = None,
    batch_serving: Callable[[str], bool] = batch_serves,
    idle_now: Callable[[], bool] = idle,
    reserve_fleet: Callable[[float], bool] = _reserve_fleet,
) -> Decision:
    """The checks run cheapest first, and the fleet budget last so a refusal spends nothing.

    A deferred summary (``kind='text'``) uses no GPU: it skips the route and idle checks but
    still spends the owner's day and the fleet budget.
    """
    if not enabled():
        return Decision(False, 'kill_switch')
    rate = float(recording_units_per_hour('batch'))
    day = datetime.fromtimestamp(time.time() if now is None else now, timezone.utc).strftime('%Y-%m-%d')
    spent = float(job.get('release_day_units') or 0) if job.get('release_day') == day else 0.0
    # A single recording longer than the limit still runs alone on an unspent day.
    if spent > 0 and spent + units > OWNER_HOURS_PER_DAY * rate:
        return Decision(False, 'owner_day')
    audio = kind != 'text'
    if audio and not batch_serving(uid):
        return Decision(False, 'legacy_route')
    priority_left = float(job.get('release_priority_units') or 0)
    normal = audio and priority_left > 0
    if audio and not normal and not idle_now():
        return Decision(False, 'not_idle')
    if not reserve_fleet(units / rate * 3600):
        return Decision(False, 'fleet_budget')
    updates: dict[str, Any] = {'release_day': day, 'release_day_units': spent + units}
    if normal:
        updates['release_priority_units'] = max(0.0, priority_left - units)
    return Decision(True, 'granted', normal, updates)
