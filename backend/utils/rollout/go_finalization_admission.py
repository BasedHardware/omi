# LIFECYCLE: permanent
"""Runtime admission for Go ordinary-sync finalization (SCA-3883 item 3).

The cohort and its kill switch are runtime data, never a code merge or a rebuild:

- Switch: the `_ramp` control document's `go-finalization` percent. It is open only when
  that value is exactly 100.0 **from a successful Firestore read no older than TTL_SECONDS**.
  Absent, any other value, malformed, a read error, or a stale read all mean closed. Unlike
  the shared runtime-percent reader, this never serves last-known-good: an open switch can
  outlive a close by at most TTL_SECONDS plus one refresh.
- Membership: the existing per-uid `rollout_cohorts/{uid}` document, read through the shared
  cached resolver (`in_rollout_cohort`), so a check adds no Firestore operation. The cohort has
  no environment fallback, so an unknown or missing membership is a negative grant.

Call `go_finalization_decision` before entering the transaction that creates the canonical
document with the `pending` marker; that transaction pins the engine and replays honour the
committed pin. Call `record_admission` once, after that creation commits.
"""

from __future__ import annotations

import asyncio
import logging
from threading import Lock, Thread
import time
from typing import Any, Callable, Literal

from prometheus_client import Counter

from config import rollout_cohorts as policy
from database import rollout_cohorts as store
from utils.observability.fallback import record_fallback

COHORT = 'go-finalization'
RAMP_NAME = 'go-finalization'
OPEN_PERCENT = 100.0
TTL_SECONDS = 30.0
# A failed read is cached as closed this long, so an outage costs one read per process per
# interval instead of one serialized read per waiting caller.
ERROR_BACKOFF_SECONDS = 5.0
assert ERROR_BACKOFF_SECONDS < TTL_SECONDS, 'the error backoff is encoded as an aged successful read'

Engine = Literal['python', 'go']
Reason = Literal['closed', 'not_member', 'admitted']

logger = logging.getLogger(__name__)

ADMISSIONS = Counter(
    'omi_finalization_admission_total',
    'Ordinary-sync finalization admissions by engine and reason, counted once after the creating commit.',
    ['engine', 'reason'],
)
SWITCH_READS = Counter(
    'omi_go_finalization_switch_reads_total',
    'Go finalization switch refresh reads by result (open, closed, absent, error, event_loop).',
    ['result'],
)


def _default_read() -> dict[str, Any] | None:
    from utils.rollout.runtime_percent import deployment_env

    document = store.read_ramp()
    if document is None:
        return None
    return document['envs'].get(deployment_env())


class _Switch:
    """One process-wide cached value; concurrent refreshes coalesce on a single read."""

    def __init__(self, reader: Callable[[], dict[str, Any] | None], clock: Callable[[], float] = time.monotonic):
        self._reader = reader
        self._clock = clock
        self._state_lock = Lock()
        self._refresh_lock = Lock()
        self._open = False
        self._read_at: float | None = None
        self._background: Thread | None = None

    def _fresh(self, now: float) -> bool:
        return self._read_at is not None and now - self._read_at < TTL_SECONDS

    def is_open(self) -> bool:
        with self._state_lock:
            if self._fresh(self._clock()):
                return self._open
        if _on_event_loop():
            # A blocking point read must never stall the loop. An event-loop caller with a stale
            # cache gets closed now and starts one background refresh, so later calls see it.
            SWITCH_READS.labels('event_loop').inc()
            self._refresh_in_background()
            return False
        with self._refresh_lock:
            return self._refresh_locked()

    def _refresh_locked(self) -> bool:
        with self._state_lock:
            if self._fresh(self._clock()):  # another caller refreshed while we waited
                return self._open
        result, opened = self._read()
        with self._state_lock:
            self._open = opened
            now = self._clock()
            # A failed read never counts as a successful one: it is cached closed for
            # ERROR_BACKOFF_SECONDS only, shared by every waiter, and then retried.
            self._read_at = now if result != 'error' else now - TTL_SECONDS + ERROR_BACKOFF_SECONDS
        SWITCH_READS.labels(result).inc()
        return opened

    def _refresh_in_background(self) -> None:
        if not self._refresh_lock.acquire(blocking=False):
            return  # a refresh is already running; it serves this caller too

        def run():
            try:
                self._refresh_locked()
            finally:
                self._refresh_lock.release()

        try:
            thread = Thread(target=run, name='go-finalization-switch-refresh', daemon=True)
            self._background = thread
            thread.start()
        except Exception:
            self._refresh_lock.release()

    def _read(self) -> tuple[str, bool]:
        try:
            env_doc = self._reader()
        except Exception:
            _record_python_fallback()
            return 'error', False
        if not env_doc:
            return 'absent', False
        percents = env_doc.get('percents')
        value = percents.get(RAMP_NAME) if isinstance(percents, dict) else None
        # bool is an int subclass, so check exact types: only a numeric 100 opens.
        if (type(value) is int or type(value) is float) and value == OPEN_PERCENT:
            return 'open', True
        return ('absent' if value is None else 'closed'), False


def _record_python_fallback() -> None:
    # A read error routes a would-be Go owner to the incumbent engine: a mode change, so it is
    # reported through the shared fallback contract rather than only a local counter.
    record_fallback(
        component='sync_dispatch',
        from_mode='go_finalization',
        to_mode='python_finalization',
        reason='unavailable',
        outcome='degraded',
        log=logger,
    )


def _on_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


_switch = _Switch(_default_read)


def configure_switch_reader(reader: Callable[[], dict[str, Any] | None], clock: Callable[[], float] = time.monotonic):
    """Tests and tools inject a reader; serving uses the `_ramp` point read."""
    global _switch
    _switch = _Switch(reader, clock)


def go_finalization_decision(uid: str) -> tuple[Engine, Reason]:
    """Decide the engine for a new pending canonical document. Never raises; unknown means Python."""
    if not _switch.is_open():
        return 'python', 'closed'
    try:
        member = policy.in_rollout_cohort(uid, COHORT)
    except Exception:
        _record_python_fallback()
        member = False
    if not member:
        return 'python', 'not_member'
    return 'go', 'admitted'


def record_admission(engine: Engine, reason: Reason) -> None:
    """Call once after the creating transaction commits, so retries and replays do not count."""
    ADMISSIONS.labels(engine, reason).inc()
