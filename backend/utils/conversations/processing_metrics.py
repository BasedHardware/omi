"""Bounded metrics for retryable synchronous conversation failures."""

from prometheus_client import Counter

RETRYABLE_PROCESSING_FAILURE_CLASSES = frozenset({'timeout', 'transport', 'provider_status'})
RETRYABLE_PROCESSING_ROUTES = frozenset(
    {
        'conversation_processing',
        'conversation_processing/app_result',
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


def record_retryable_processing_response(failure_class: str, route: str) -> None:
    RETRYABLE_PROCESSING_RESPONSES_TOTAL.labels(
        failure_class=failure_class if failure_class in RETRYABLE_PROCESSING_FAILURE_CLASSES else 'other',
        route=route if route in RETRYABLE_PROCESSING_ROUTES else 'other',
    ).inc()
