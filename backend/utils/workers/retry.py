"""The only allowed response shape for an expected retry from a task target (contract (d)).

A Cloud Tasks or Cloud Scheduler target returns 2xx when the delivery is consumed, 409
``{"status": "retry", "reason": <RetryReason>}`` for every expected condition, 400 for a malformed task,
and 500 only for an unexpected exception. Never 429 or 503: Cloud Tasks ignores ``Retry-After`` and
system-throttles a queue that sees fast 5xx (10-18 18:14Z and 10-19 04:52Z stalls).

"""

from __future__ import annotations

from fastapi.responses import JSONResponse

from database.firestore_transaction_retry import FirestoreContentionExhausted, is_expired_transaction
from utils.observability.reasons import RetryReason

RETRY_STATUS_CODE = 409


class ExpectedRetry(Exception):
    """Raised by a handler for an expected, transient condition; the route answers ``retry_response``."""

    reason: RetryReason

    def __init__(self, reason: RetryReason):
        self.reason = RetryReason(reason)
        super().__init__(self.reason.value)


def retry_response(reason: RetryReason) -> JSONResponse:
    """409 {"status": "retry", "reason": "<reason>"}. The only allowed shape for an expected retry."""
    return JSONResponse(status_code=RETRY_STATUS_CODE, content={'status': 'retry', 'reason': RetryReason(reason).value})


def exhausted_transaction_retry_class(error: BaseException) -> str | None:
    """Classify only a failed bounded transaction chain, preserving the final cause."""
    if not isinstance(error, FirestoreContentionExhausted):
        return None
    if error.reason == 'deadline_exhausted':
        return 'transaction_retry_deadline'
    cause = error.__cause__
    # The SDK wraps commit-time Aborted in ValueError even with max_attempts=1.
    if isinstance(cause, ValueError):
        cause = cause.__cause__
    if cause is not None and is_expired_transaction(cause):
        return 'transaction_expired'
    return 'transaction_contention'
