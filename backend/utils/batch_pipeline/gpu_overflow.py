"""Is the GPU ring past its fresh-backlog SLO? The capacity input to overflow at admission.

``saturated(store)`` answers from a process cache and never blocks: a stale entry schedules one
background read on the rollout executor (as ``utils.rollout.runtime_percent`` does) and the call
returns the last answer. Each read takes two numbers for the fresh priority: the enqueue time of the
oldest admissible ready unit (``oldest_admissible_ready``: never allowance holds or deferred retries)
and the admissible ready count (``ready_for_capacity``, the HPA's own signal). Saturation starts when
the age reaches the enter threshold with at least ``min_ready_units`` waiting, and stops once the
age falls below the exit threshold or fewer than half that many units wait. The count gate keeps a
few stuck heads (old age, idle ring) from reading as a backlog.

Every failure answers "not saturated": the unit stays on GPU and waits, which is today's routing,
with its audio in custody. A cold process answers "not saturated" until its first read lands.
Callers apply their own kill switch (vendor overflow, legacy capacity fallback).
"""

from __future__ import annotations

import contextvars
import logging
import time
from threading import Lock
from typing import Any, Callable

from config.batch_pipeline import Priority
from config.batch_pipeline_vendor_overflow import min_ready_units, thresholds
from utils.batch_pipeline import vendor_route_metrics as metrics

logger = logging.getLogger(__name__)

REFRESH_SECONDS = 30.0

# now -> (enqueue time of the oldest admissible fresh unit or None, admissible fresh ready count)
Sample = Callable[[float], tuple[float | None, int]]


def _submit(fn: Callable[[], None]) -> Any:
    from utils import executors

    return executors.get_rollout_executor().submit(contextvars.Context().run, fn)  # never inherit request context


class GpuOverflow:
    def __init__(
        self,
        sample: Sample,
        *,
        clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
        submit: Callable[[Callable[[], None]], Any] | None = None,
    ) -> None:
        self._sample = sample
        self._clock = clock
        self._monotonic = monotonic
        self._submit = submit if submit is not None else _submit
        self._lock = Lock()
        self._active = False
        self._expires = float('-inf')
        self._inflight = False

    def saturated(self) -> bool:
        self._start_refresh()
        with self._lock:
            return self._active

    def _start_refresh(self) -> None:
        with self._lock:
            if self._inflight or self._monotonic() < self._expires:
                return
            self._inflight = True
        try:
            self._submit(self._refresh)
        except Exception:
            logger.warning('event=batch_gpu_overflow_sample outcome=not_scheduled served=not_saturated')
            self._settle(False, 0.0)

    def _refresh(self) -> None:
        now = self._clock()
        try:
            oldest, waiting = self._sample(now)
            age = 0.0 if oldest is None else max(0.0, now - float(oldest))
            waiting = int(waiting)
        except Exception as error:
            # SDK errors can carry paths; keep the line content-free.
            logger.warning('event=batch_gpu_overflow_sample outcome=error exception_type=%s', type(error).__name__)
            self._settle(False, 0.0)
            return
        enter, exit_ = thresholds()
        units = min_ready_units()
        with self._lock:
            was = self._active
        active = (age >= exit_ and waiting * 2 >= units) if was else (age >= enter and waiting >= units)
        if active != was:
            logger.info('event=batch_gpu_overflow active=%s backlog_age_s=%d waiting=%d', active, int(age), waiting)
        self._settle(active, age)

    def _settle(self, active: bool, age: float) -> None:
        with self._lock:
            self._active = active
            self._expires = self._monotonic() + REFRESH_SECONDS
            self._inflight = False
        metrics.gpu_overflow(active, age)


_overflow: GpuOverflow | None = None
_bind_lock = Lock()


def saturated(store: Any) -> bool:
    """The process's answer for ``store`` (bound once). A store without the reads never saturates."""
    global _overflow
    if _overflow is None:
        oldest = getattr(store, 'oldest_admissible_ready', None)
        count = getattr(store, 'ready_for_capacity', None)
        if not callable(oldest) or not callable(count):
            return False
        fresh = int(Priority.FRESH)
        with _bind_lock:
            if _overflow is None:
                _overflow = GpuOverflow(lambda now: (oldest(fresh, now), count(fresh, now)))
    return _overflow.saturated()
