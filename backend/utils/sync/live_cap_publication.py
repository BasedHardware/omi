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


def retry_transient_leaf(operation: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run one idempotent recovery leaf with a bounded transient retry.

    Covers the non-transactional reads and preconditioned writes that decide
    custody after ``run_transactional`` has surfaced (receipt verification,
    staging fallback, redrive hand-off). ``AlreadyExists`` and other
    non-transient results are never retried; a retried leaf counts
    ``retried_ok`` and a spent budget counts ``exhausted`` with the failure's
    cause, so a transport fault is visible even when the transaction itself
    never restarted.
    """
    last_error: Exception | None = None
    for attempt in range(1, LEAF_RETRY_ATTEMPTS + 1):
        try:
            result = operation(*args, **kwargs)
        except Exception as error:
            retryable = is_retryable_firestore_transaction_error(error)
            if attempt >= LEAF_RETRY_ATTEMPTS or not retryable:
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
    recover: Callable[[BaseException], Any] | None = None,
) -> Any:
    """Run one idempotent publication transaction with bounded fresh-transaction retries.

    The callable must re-read before it writes. Backoff happens in
    ``run_transactional``, so the callable has to drop any session lock before
    returning or raising. ``recover`` runs only after the error is final; return
    ``UNRECOVERED`` to keep today's failure, or a value to treat the audio as
    durable and let the socket stay up.
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
        )
    except Exception as error:
        if outcome.get('status') == 'exhausted':
            record_publication_retry('exhausted', publication_retry_cause(error, outcome.get('reason')))
        if recover is None:
            raise
        recovered = recover(error)
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
