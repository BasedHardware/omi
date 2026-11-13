"""Bounded outer retries for the Chat-first intent and candidate-outbox lanes.

Twenty-five transactional entries across ``chat_first_intents``,
``chat_first_delivery_attempts`` and ``candidate_integration_outbox`` handed
their bodies to the Firestore SDK's bare transaction path: one transaction id
replayed by the SDK's same-id commit loop, a read-time ``Aborted`` fault
escaping as an unclassified server error that fails the user-visible flow on
the first collision, and an exhausted chain surfacing as an anonymous fault
with no label. This runner joins every entry to the shared bounded engine —
five fresh transactions, equal-jitter rungs, replayed aborts and expiries,
and a typed, per-entry-labeled ``FirestoreContentionExhausted`` — the same
doctrine the batch pipeline lanes ride through
``run_batch_pipeline_transaction``, minus the storm damper these lanes have
not adopted.

A fresh transaction is a safe replay here: every joined body re-reads its
documents inside the transaction and keeps its idempotency checks inside the
same atomic scope, so an aborted or expired chain that wrote nothing can be
replayed without double effects. Foreign domain refusals (a continuity-key
conflict, a proactive turn budget exhausted, an unsupported outcome token)
are never contention: they pass through single-shot exactly as before, on the
first attempt.

The engine and the expiry-restarting inner helper are imported at call time
so a test can pin either boundary the way the storm-gate harness does. The
``max_attempts`` parameter exists for a caller that owns a narrower budget;
every production entry keeps the default chain.

Failure-Class: FC-bare-chat-first-and-candidate-outbox-transactions-fail-on-first-contention
"""

import logging
from typing import Any, Callable, TypeVar

T = TypeVar("T")

DEFAULT_LANE_MAX_ATTEMPTS = 5

logger = logging.getLogger(__name__)


def run_bounded_lane_transaction(
    client: Any,
    operation: Callable[[Any], T],
    *,
    operation_name: str,
    logger: Any = None,
    max_attempts: int = DEFAULT_LANE_MAX_ATTEMPTS,
) -> T:
    """Run one Chat-first/candidate-outbox transaction on the bounded engine.

    A bare ``operation(client.transaction())`` hands contention to the SDK's
    same-id commit replay: one transaction id retried inside the exact
    collision that aborted it, a mid-read abort escaping unclassified, and an
    exhaustion with no label. Here every outer attempt mints a fresh
    transaction with a single SDK commit attempt — the outer engine is the
    only contention budget (five bodies, not 5 x 5 same-id replays) — and the
    inner expiry-restarting helper runs with ``attempts=1`` so one budget
    bounds the whole chain count. ``operation_name`` labels the engine's
    contention channel; ``logger`` routes the lane's own exhaustion marker to
    the calling module's logger.
    """
    from database._client import run_transactional
    from database.firestore_transaction_retry import (
        FirestoreContentionExhausted,
        run_with_transaction_contention_retry,
    )

    lane_logger = logger if logger is not None else logging.getLogger(__name__)

    def fresh_transaction() -> Any:
        # One SDK commit attempt per fresh transaction: the outer helper is
        # the only commit-contention budget.
        return client.transaction(max_attempts=1)

    try:
        return run_with_transaction_contention_retry(
            fresh_transaction,
            lambda transaction: run_transactional(client, operation, initial_transaction=transaction, attempts=1),
            operation_name=operation_name,
            max_attempts=max_attempts,
        )
    except FirestoreContentionExhausted as error:
        lane_logger.error(
            'event=%s_contention_exhausted operation=%s reason=%s retry_after_ms=%d',
            operation_name,
            operation_name,
            error.reason,
            round(error.retry_after * 1000),
        )
        raise
