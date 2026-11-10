"""Bounded internal causes for sync persistence and finalize failures.

Every exception in those phases used to surface as the STT ``upstream_error``
outcome, so storage rate limits, Firestore contention and assignment conflicts
read as a vendor fault. Classification uses only the bounded exception class,
never exception text, so it gives the same answer at the segment boundary and
when deferred labels are replayed after a checkpoint.
"""

from __future__ import annotations

import httpx
from google.api_core import exceptions as google_exceptions

from config.sync_telemetry import (
    SYNC_INTERNAL_ERROR_OUTCOME,
    SYNC_REPEATABLE_PERSISTENCE_EXCEPTIONS,
    SyncFailureReason,
    bounded_exception_class,
)
from database._client import is_document_size_limit_error
from utils.stt.outcomes import TranscriptionFailure
from utils.sync.assignment_errors import SyncAssignmentConflict, sync_assignment_conflict_strikes

# Job phases with no STT vendor call. Segment classification only ever sees
# persistence and finalize; postprocess and usage are whole-job coordinator phases.
INTERNAL_PHASES = frozenset({'persistence', 'finalize', 'postprocess', 'usage'})

_CLASS_REASONS = {
    # GCS JSON API 429; Firestore/gRPC throttling is its ResourceExhausted subclass.
    'TooManyRequests': SyncFailureReason.STORAGE_RATE_LIMITED,
    'ResourceExhausted': SyncFailureReason.QUOTA_EXHAUSTED,
    'FirestoreContentionExhausted': SyncFailureReason.FIRESTORE_CONTENTION,
    'Aborted': SyncFailureReason.FIRESTORE_CONTENTION,
    'SyncAssignmentConflict': SyncFailureReason.ASSIGNMENT_CONFLICT,
}

_ERROR_CODES = {
    SyncFailureReason.STORAGE_RATE_LIMITED: 'sync_storage_rate_limited',
    SyncFailureReason.FIRESTORE_CONTENTION: 'sync_firestore_contention',
}
SYNC_INTERNAL_ERROR_CODES = frozenset(_ERROR_CODES.values()) | {'sync_finalize_failed', 'sync_persistence_failed'}


def _provider_typed(failure: object) -> bool:
    # A typed STT failure (ProviderUnavailable included) is a vendor outcome even
    # when the coordinator re-raises it from the persistence loop.
    if bounded_exception_class(failure) == 'TranscriptionFailure':
        return True
    current = failure if isinstance(failure, BaseException) else None
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        if isinstance(current, TranscriptionFailure):
            return True
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return False


def sync_failure_reason(phase: object, failure_class: object) -> SyncFailureReason:
    """Internal cause for a persistence/finalize failure, ``none`` for every other phase."""
    if phase not in INTERNAL_PHASES or _provider_typed(failure_class):
        return SyncFailureReason.NONE
    reason = _CLASS_REASONS.get(bounded_exception_class(failure_class))
    if reason is not None:
        return reason
    return SyncFailureReason.PERSISTENCE_ERROR if phase == 'persistence' else SyncFailureReason.FINALIZE_ERROR


def sync_failure_error_code(reason: SyncFailureReason, phase: str) -> str:
    """Client-visible job error code; unchanged for the generic internal causes."""
    return _ERROR_CODES.get(reason) or ('sync_persistence_failed' if phase == 'persistence' else 'sync_finalize_failed')


def job_failure_reason(errors: list[str], phase: object, failure_class: object) -> SyncFailureReason:
    """A job is internal only when no segment error came from an STT provider."""
    if not errors or not set(errors) <= SYNC_INTERNAL_ERROR_CODES:
        return SyncFailureReason.NONE
    return sync_failure_reason(phase, failure_class)


def stamped_failure_kwargs(error: BaseException) -> dict:
    """Final-attempt finalize kwargs from the cause the pipeline stamped before a task-mode re-raise.

    The Cloud Tasks handler only sees the exception; without the stamp its final
    attempt would publish an internal failure as ``upstream_error`` again.
    """
    stamped = getattr(error, 'sync_failure_reason', None)
    phase = getattr(error, 'sync_failure_phase', None)
    return {
        'failure_phase': phase if isinstance(phase, str) else None,
        'failure_class': bounded_exception_class(error),
        'failure_reason': stamped if isinstance(stamped, SyncFailureReason) else SyncFailureReason.NONE,
    }


def outcome_label(outcome_value: str, reason: SyncFailureReason) -> str:
    return SYNC_INTERNAL_ERROR_OUTCOME if reason is not SyncFailureReason.NONE else outcome_value


def persistence_failure_fingerprint(error: BaseException, phase: str, lane: str = 'fresh') -> str | None:
    """Identify a bounded, classified persistence failure, never an unknown error.

    A fingerprint is one strike toward the three-strike / 24-hour pause, never
    a permanent verdict. Inspect the full cause chain so an apparent classified
    error wrapping a transient transport or Firestore failure cannot record one.
    Assignment conflicts strike by reason (``sync_assignment_conflict_strikes``)
    so a conflict that can never resolve stops retrying paid work forever.
    """
    if phase != 'persistence':
        return None
    structural = None
    if isinstance(error, SyncAssignmentConflict) and sync_assignment_conflict_strikes(error.subtype, lane):
        structural = f'persistence:{error.subtype}'
    if is_document_size_limit_error(error):
        structural = 'persistence:document_size_limit'
    subtype = bounded_exception_class(error)
    if structural is None and subtype not in SYNC_REPEATABLE_PERSISTENCE_EXCEPTIONS:
        return None
    chain: list[BaseException] = []
    current: BaseException | None = error
    while current is not None and all(current is not item for item in chain):
        chain.append(current)
        current = current.__cause__ or current.__context__
    if any(
        type(item).__name__ == 'FirestoreContentionExhausted'
        or isinstance(
            item,
            (
                google_exceptions.Aborted,
                google_exceptions.GoogleAPICallError,
                google_exceptions.DeadlineExceeded,
                google_exceptions.ServiceUnavailable,
                google_exceptions.ResourceExhausted,
                google_exceptions.RetryError,
                TimeoutError,
                ConnectionError,
                httpx.TimeoutException,
                httpx.TransportError,
                httpx.HTTPStatusError,
            ),
        )
        for item in chain
        if not (item is error and structural == 'persistence:document_size_limit')
    ):
        return None
    return structural or f'persistence:{subtype}'
