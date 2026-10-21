"""One-use, process-owned source identity; retries cannot masquerade as fresh."""

import random
import time
from threading import RLock
from typing import Any, Callable
from uuid import uuid4

from database._client import (
    firestore_failure_reason,
    is_retryable_firestore_transaction_error,
    run_transactional,
)
from utils.observability.held_content import record_publication_retry


class _Unrecovered:
    """Sentinel: the publication error still has to surface."""


UNRECOVERED = _Unrecovered()

# The live socket stops consuming its receive queue while a publication holds
# the sink's lock (the flush awaits the storage executor inline), and the app
# pings every 20s and closes on a missed pong. Every part of one live
# publication — all transaction attempts, the backoff between them, and the
# custody-deciding leaf reads of the fallback — shares one end-to-end deadline
# comfortably inside that heartbeat.
LIVE_PUBLICATION_DEADLINE_SECONDS = 12.0
# The redrive sweep shares seal() with the live path but owns no socket; its
# deadline only bounds one sweep visit, so it stays generous.
RECOVERY_PUBLICATION_DEADLINE_SECONDS = 60.0
# A restart or leaf retry needs enough of the deadline left to be worth its
# RPC budget; below this slice the fallback runs instead of another attempt.
MIN_ATTEMPT_SECONDS = 2.0
# The fallback's confirmation reads may outlive a spent deadline by one slice:
# 'staged hand-off if confirmable, else 1011' needs one readable row.
LEAF_TIMEOUT_FLOOR_SECONDS = 2.0
# Per-RPC ceiling; individual calls shrink below it as the deadline drains.
DEFAULT_RPC_TIMEOUT_SECONDS = 10.0


class PublicationBudget:
    """End-to-end wall-clock budget for one publication.

    Every RPC timeout is derived from the time remaining at call time, so a
    hung read, upload, or commit can never push the publication past its
    deadline; restarts and leaf retries simply stop once too little is left.
    ``clock`` is the monotonic time source (tests substitute a fake).
    """

    def __init__(self, seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self._expires_at = clock() + seconds
        self._clock = clock

    def remaining(self) -> float:
        return self._expires_at - self._clock()

    def expired(self) -> bool:
        return self.remaining() <= 0

    def allows_attempt(self) -> bool:
        return self.remaining() >= MIN_ATTEMPT_SECONDS

    def attempt_timeout(self, default: float = DEFAULT_RPC_TIMEOUT_SECONDS) -> float:
        """Timeout for one RPC inside an attempt: capped by the default and by the deadline."""
        return max(0.1, min(default, self.remaining()))

    def leaf_timeout(self, default: float = DEFAULT_RPC_TIMEOUT_SECONDS) -> float:
        """Timeout for one custody-deciding fallback read.

        The confirmation slice is floored: without it, a deadline the retries
        just spent would close the socket with 1011 even when the row that
        confirms staging is one readable call away.
        """
        return min(default, max(self.remaining(), LEAF_TIMEOUT_FLOOR_SECONDS))

    def leaf_kwargs(self) -> dict[str, Any]:
        """Explicit timeout / retry for one fallback-window Firestore call."""
        return {'timeout': self.leaf_timeout(), 'retry': None}

    def clamp_sleep(self, delay: float) -> float:
        return max(0.0, min(delay, self.remaining()))


def new_publication_budget(seconds: float) -> PublicationBudget:
    """Deadline constructor seam: entries build budgets through this factory."""
    return PublicationBudget(seconds)


# Outside ``run_transactional`` there is no restart loop, so a custody-deciding
# recovery read or preconditioned write gets the same attempt budget here. No
# sleep: these leaves run under a session lock the transactional path
# deliberately releases before backoff, and each leaf's own RPC timeout has
# already spent the fault window by the time it raises.
LEAF_RETRY_ATTEMPTS = 3

_PUBLICATION_CAUSE_BY_REASON = {
    'transport_timeout': 'timeout',
    'deadline_exceeded': 'timeout',
    'transport_connection': 'connection',
    'unavailable': 'connection',
    'resource_exhausted': 'throttle',
}


def publication_retry_cause(error: BaseException | None = None, reason: str | None = None) -> str:
    """Closed-set cause label for a publication retry, from a reason token or the error."""
    token = reason or (firestore_failure_reason(error) if error is not None else None)
    return _PUBLICATION_CAUSE_BY_REASON.get(token or '', 'other')


def retry_sleep(delay: float) -> None:
    """Backoff hook. Publication callers sleep only after releasing their lock."""
    time.sleep(delay)


def retry_transient_leaf(budget: PublicationBudget, operation: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run one idempotent recovery leaf with a bounded transient retry.

    Covers the non-transactional reads and preconditioned writes that decide
    custody after ``run_transactional`` has surfaced (receipt verification,
    staging fallback, redrive hand-off). Leaf calls carry an explicit timeout
    and ``retry=None`` derived from the budget — without them the Firestore
    client default is a 60s timeout under a 60s retry deadline, not 10s.
    ``AlreadyExists`` and other non-transient results are never retried, and
    neither is anything once the deadline has drained; a retried leaf counts
    ``retried_ok`` and a spent budget counts ``exhausted`` with the failure's
    cause, so a transport fault is visible even when the transaction itself
    never restarted.
    """
    kwargs.setdefault('timeout', budget.leaf_timeout())
    kwargs.setdefault('retry', None)
    last_error: Exception | None = None
    for attempt in range(1, LEAF_RETRY_ATTEMPTS + 1):
        try:
            result = operation(*args, **kwargs)
        except Exception as error:
            retryable = is_retryable_firestore_transaction_error(error)
            if attempt >= LEAF_RETRY_ATTEMPTS or not retryable or budget.expired():
                if retryable:
                    record_publication_retry('exhausted', publication_retry_cause(error))
                raise
            last_error = error
            continue
        if attempt > 1:
            record_publication_retry('retried_ok', publication_retry_cause(last_error))
        return result
    raise AssertionError('unreachable')


def commit_publication(
    client: Any,
    transactional_fn: Callable[..., Any],
    *,
    budget: PublicationBudget,
    recover: Callable[[BaseException, PublicationBudget], Any] | None = None,
) -> Any:
    """Run one idempotent publication transaction with bounded fresh-transaction retries.

    The callable must re-read before it writes. Backoff happens in
    ``run_transactional``, so the callable has to drop any session lock before
    returning or raising. ``budget`` is the end-to-end deadline every attempt,
    backoff sleep, and fallback leaf shares; it stops restarts early (counted
    ``exhausted``) so the fallback still runs inside the deadline.
    ``recover`` runs only after the error is final and receives the budget for
    its own leaf reads; return ``UNRECOVERED`` to keep today's failure, or a
    value to treat the audio as durable and let the socket stay up.
    """
    outcome: dict[str, str] = {}
    try:
        result = run_transactional(
            client,
            transactional_fn,
            transient=True,
            sleep=retry_sleep,
            random_value=random.random,
            outcome=outcome,
            budget=budget,
        )
    except Exception as error:
        if outcome.get('status') == 'exhausted':
            record_publication_retry('exhausted', publication_retry_cause(error, outcome.get('reason')))
        if recover is None:
            raise
        recovered = recover(error, budget)
        if recovered is UNRECOVERED:
            raise
        return recovered
    if outcome.get('status') == 'retried_ok':
        record_publication_retry('retried_ok', publication_retry_cause(reason=outcome.get('reason')))
    return result


class Publication:
    def __init__(self, uid: str) -> None:
        self._uid = uid
        self._identity = uuid4().hex
        self._attempted = False
        self.lock = RLock()
        self.fields: dict = {}
        self.put_started = False

    @property
    def uid(self) -> str:
        return self._uid

    @property
    def identity(self) -> str:
        return self._identity

    def is_retry(self, uid: str) -> bool:
        if uid != self.uid:
            raise ValueError('live publication owner changed')
        with self.lock:
            previous, self._attempted = self._attempted, True
            return previous
