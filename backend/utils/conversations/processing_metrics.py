"""Bounded metrics for retryable synchronous conversation failures."""

from contextlib import contextmanager
from contextvars import ContextVar

from prometheus_client import Counter

FROM_SEGMENTS_METRIC_ROUTE = 'from_segments'
RETRYABLE_PROCESSING_FAILURE_CLASSES = frozenset({'timeout', 'transport', 'provider_status'})
RETRYABLE_PROCESSING_ROUTES = frozenset(
    {
        'conversation_processing',
        'conversation_processing/app_result',
        FROM_SEGMENTS_METRIC_ROUTE,
        # Internal Cloud Tasks builder routes answer the same contract so a
        # provider 5xx on the v3 outline path is retried, not an unhandled 500.
        'conversations_v3_reconcile',
        'conversations_v3_backfill',
    }
)

RETRYABLE_PROCESSING_RESPONSES_TOTAL = Counter(
    'omi_conversation_processing_retryable_responses_total',
    'Conversation processing and internal task failures answered with the typed retryable response',
    ['failure_class', 'route'],
)

_response_count_deferred = ContextVar('retryable_processing_response_count_deferred', default=False)


@contextmanager
def defer_retryable_processing_response_count():
    """Let the from-segments HTTP boundary count the response it actually sends."""
    token = _response_count_deferred.set(True)
    try:
        yield
    finally:
        _response_count_deferred.reset(token)


def record_retryable_processing_response(failure_class: str, route: str) -> None:
    if _response_count_deferred.get():
        return
    RETRYABLE_PROCESSING_RESPONSES_TOTAL.labels(
        failure_class=failure_class if failure_class in RETRYABLE_PROCESSING_FAILURE_CLASSES else 'other',
        route=route if route in RETRYABLE_PROCESSING_ROUTES else 'other',
    ).inc()
