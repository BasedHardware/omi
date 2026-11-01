"""Is the GPU ring past its fresh-backlog SLO? The capacity input to vendor overflow (selection).

``saturated(store)`` answers from a process cache and never blocks: a stale entry schedules one
background read on the rollout executor (as ``utils.rollout.runtime_percent`` does) and the call
returns the last answer. The read is ``oldest_admissible_ready`` for the fresh priority, so it
measures work a GPU would run now, never allowance holds or deferred retries. Hysteresis: overflow
starts when that age reaches the enter threshold and stops once it falls below the exit threshold.

Every failure answers "not saturated": the unit stays on GPU and waits, which is today's routing,
with its audio in custody. A cold process answers "not saturated" until its first read lands.
"""

from __future__ import annotations

import contextvars
import logging
import time
from threading import Lock
from typing import Any, Callable

from config.batch_pipeline import Priority
from config.batch_pipeline_vendor_overflow import overflow_enabled, thresholds
from utils.batch_pipeline import vendor_route_metrics as metrics

logger = logging.getLogger(__name__)

REFRESH_SECONDS = 30.0


def _submit(fn: Callable[[], None]) -> Any:
    from utils import executors

    return executors.get_rollout_executor().submit(contextvars.Context().run, fn)  # never inherit request context


class GpuOverflow:
    def __init__(
        self,
        sample: Callable[[float], float | None],
        *,
        clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
        submit: Callable[[Callable[[], None]], Any] | None = None,
    ) -> None:
        self._sample = sample  # now -> enqueue time of the oldest admissible fresh unit, or None
        self._clock = clock
        self._monotonic = monotonic
        self._submit = submit if submit is not None else _submit
        self._lock = Lock()
        self._active = False
        self._expires = float('-inf')
        self._inflight = False

    def saturated(self) -> bool:
        if not overflow_enabled():
            return False
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
            logger.warning('event=batch_vendor_overflow_sample outcome=not_scheduled served=gpu')
            self._settle(False, 0.0)

    def _refresh(self) -> None:
        now = self._clock()
        try:
            oldest = self._sample(now)
            age = 0.0 if oldest is None else max(0.0, now - float(oldest))
        except Exception as error:
            # SDK errors can carry paths; keep the line content-free.
            logger.warning('event=batch_vendor_overflow_sample outcome=error exception_type=%s', type(error).__name__)
            self._settle(False, 0.0)
            return
        enter, exit_ = thresholds()
        with self._lock:
            active = age >= exit_ if self._active else age >= enter
        if active != self._active:
            logger.info('event=batch_vendor_overflow active=%s backlog_age_s=%d', active, int(age))
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
    """The process's answer for ``store`` (bound once). A store without the read never overflows."""
    global _overflow
    if _overflow is None:
        sampler = getattr(store, 'oldest_admissible_ready', None)
        if not callable(sampler):
            return False
        with _bind_lock:
            if _overflow is None:
                _overflow = GpuOverflow(lambda now: sampler(int(Priority.FRESH), now))
    return _overflow.saturated()
