"""Bounded failure diagnostics for persisted conversation finalization."""

from __future__ import annotations

import logging
import threading
from enum import Enum

from fastapi import HTTPException
from prometheus_client import Counter

logger = logging.getLogger(__name__)


class FinalizationFailureReason(str, Enum):
    """Closed, low-cardinality reasons safe for metrics and logs."""

    memory_fence = 'memory_fence'
    memory_config = 'memory_config'
    provider = 'provider'
    stale = 'stale'
    processing = 'processing'


FINALIZATION_FAILURES_TOTAL = Counter(
    'omi_capture_finalization_failures_total',
    'Persisted conversation finalization failures by bounded reason.',
    ['reason'],
)
for _reason in FinalizationFailureReason:
    # Export bounded zero-valued children at startup. Absence can then mean the
    # serving metric source is missing, never merely "no failures yet".
    FINALIZATION_FAILURES_TOTAL.labels(reason=_reason.value)

_MEMORY_FENCE_DETAILS = frozenset({'Memory writes are globally paused'})
_MEMORY_CONFIG_DETAILS = frozenset({'Memory write control is invalid'})
_STALE_FINALIZER_CODES = frozenset(
    {
        'fanout_completion_conflict',
        'fanout_lease_conflict',
        'missing_conversation_fanout_claim_conflict',
    }
)
_PROVIDER_MODULE_PREFIXES = (
    'anthropic',
    'google.api_core',
    'httpx',
    'openai',
    'requests',
)
_PROVIDER_EXCEPTION_NAMES = frozenset(
    {
        'APIConnectionError',
        'APIError',
        'APITimeoutError',
        'ConnectError',
        'ConnectionError',
        'HTTPStatusError',
        'ReadTimeout',
        'TimeoutError',
    }
)
_metric_warning_lock = threading.Lock()
_metric_warning_emitted = False


def classify_finalization_failure(error: BaseException) -> FinalizationFailureReason:
    """Map arbitrary exceptions onto a stable reason vocabulary.

    Exception messages may contain transcript or provider response content and
    must never become labels or log fields. Only the two exact, source-owned
    memory fence details are inspected.
    """

    if isinstance(error, HTTPException):
        detail = error.detail
        if error.status_code == 503 and detail in _MEMORY_FENCE_DETAILS:
            return FinalizationFailureReason.memory_fence
        if error.status_code == 503 and detail in _MEMORY_CONFIG_DETAILS:
            return FinalizationFailureReason.memory_config

    if (
        type(error).__name__ == 'ConversationFinalizationError'
        and getattr(error, 'code', None) in _STALE_FINALIZER_CODES
    ):
        return FinalizationFailureReason.stale

    error_type = type(error)
    if error_type.__name__ in _PROVIDER_EXCEPTION_NAMES or error_type.__module__.startswith(_PROVIDER_MODULE_PREFIXES):
        return FinalizationFailureReason.provider

    return FinalizationFailureReason.processing


def record_finalization_failure(reason: FinalizationFailureReason) -> None:
    """Record diagnostics without ever changing finalization behavior."""

    global _metric_warning_emitted
    try:
        FINALIZATION_FAILURES_TOTAL.labels(reason=reason.value).inc()
    except Exception:
        with _metric_warning_lock:
            if _metric_warning_emitted:
                return
            _metric_warning_emitted = True
        logger.warning('finalization_failure_metric_record_failed')


__all__ = [
    'FINALIZATION_FAILURES_TOTAL',
    'FinalizationFailureReason',
    'classify_finalization_failure',
    'record_finalization_failure',
]
