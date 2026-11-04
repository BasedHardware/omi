"""Firestore availability classifier, importable from the utils tree.

``database._client`` hosts the Firestore boundary, so the async-blockers
scanner must treat its imports as blocking persistence calls. The
availability classifier is a pure ``isinstance`` predicate with no I/O,
but the scanner cannot know that — async coordinators importing it from
``database.*`` are flagged as blocking. The predicate lives here instead
(the same pattern as ``utils.storage_retry_types`` for the storage SDK's
replay set); ``database._client`` re-exports it so existing imports keep
working.
"""

from __future__ import annotations

from google.api_core.exceptions import (
    DeadlineExceeded,
    InternalServerError,
    RetryError,
    ServiceUnavailable,
)

# Transport-level transient set the rest of ``database/`` already retries
# (``conversation_scan._scan_retry``, ``mcp_auth_read``): 503
# ``ServiceUnavailable``, 504 ``DeadlineExceeded``, 500 ``InternalServerError``.
_TRANSIENT_AVAILABILITY_ERRORS = (ServiceUnavailable, DeadlineExceeded, InternalServerError)


def _retry_error_cause(error: BaseException) -> BaseException | None:
    """The fault a drained ``google.api_core`` retry budget last saw.

    ``RetryError.cause`` is the documented accessor; the raise site also chains
    it (``raise final_exc from source_exc``), so ``__cause__`` covers an
    envelope type the pinned SDK pins differently.
    """
    if isinstance(error, RetryError):
        cause = getattr(error, "cause", None)
        if cause is not None:
            return cause
    return error.__cause__


def is_transient_availability_error(error: BaseException) -> bool:
    """True for a momentary Firestore availability failure a redial can answer.

    Covers the transport-level transient set the rest of ``database/`` already
    retries (``conversation_scan._scan_retry``, ``mcp_auth_read``): 503
    ``ServiceUnavailable``, 504 ``DeadlineExceeded``, 500 ``InternalServerError``.
    Also true for the SDK's own drained-retry envelope
    (``google.api_core.exceptions.RetryError``) when its cause is in that set:
    the gapic layer wraps every RPC — each transactional read and commit
    included — in a ~60s retry of the same availability set, and when that
    budget drains it raises ``RetryError`` with the last fault chained as the
    cause. ``RetryError`` extends ``GoogleAPIError``, not
    ``GoogleAPICallError``, so ``isinstance`` membership alone misses the
    envelope carrying a 503/504/500 — the same bounded transient, one layer
    up. Deliberately narrower than "any exception": the envelope type alone
    widens nothing (the SDK raises it around permanent refusals and unknown
    failures too, and a cause-less ``RetryError`` carries no transient
    evidence), and permanent refusals
    (``PermissionDenied``, ``FailedPrecondition``, the document-size
    ``InvalidArgument``) and deterministic schema failures keep their callers'
    failed-write classification.
    """
    if isinstance(error, _TRANSIENT_AVAILABILITY_ERRORS):
        return True
    if isinstance(error, RetryError):
        cause = _retry_error_cause(error)
        if cause is not None and isinstance(cause, _TRANSIENT_AVAILABILITY_ERRORS):
            return True
    return False
