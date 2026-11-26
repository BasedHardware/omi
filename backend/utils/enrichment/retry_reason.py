"""Closed retry classification shared by enrichment HTTP adapters."""

from fastapi import HTTPException
from utils.observability.reasons import RetryReason

EXPECTED_RETRIES = {
    # Keyed by the defining module: utils.sync.reprocess is only an alias of utils.enrichment.outbox (#22431).
    ('utils.enrichment.outbox', 'FirstSummaryCallbackPending'): 'callback_pending',
    ('utils.enrichment.admission', 'SyncConversationPersistenceFenced'): 'persistence_fenced',
}


def expected_retry_reason(error: BaseException) -> str | None:
    for cls in type(error).__mro__:
        reason = EXPECTED_RETRIES.get((cls.__module__, cls.__qualname__))
        if reason is not None:
            return reason
    if dependency_failure(error):
        return RetryReason.DEPENDENCY_WARMING.value
    return None


def dependency_failure(error: BaseException) -> bool:
    """Conversation processing's HTTP contract for a failed dependency (LLM/provider step or app), not a bug.

    ``process_conversation`` raises 429 (BYOK rate limit or quota), 500 (generic processing failure) or
    502 (selected app failed). Inside a task delivery these are transient dependency outages: answering
    500 would make Cloud Tasks system-throttle the queue (contract (d)). Other 4xx stay unexpected.
    """
    return isinstance(error, HTTPException) and (error.status_code == 429 or error.status_code >= 500)
