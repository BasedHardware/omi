"""Conversation-created delivery for v3-derived rows.

Source recordings suppress the legacy finalizer/close fanout, so a derived conversation owes it
exactly once, when it first becomes a visible completed conversation with notes. The obligation is a
durable row marker armed by the notes settle (or a hidden-to-visible flip); this module drains it
through the existing `trigger_external_integrations`, with a stable idempotency key so a replay after
a lost acknowledgement deduplicates at the receiver, as the legacy durable finalizer does.
"""

import logging
from datetime import datetime, timedelta, timezone

from database import conversations as conversations_db, conversations_v3_processing as writers
from models.finalization_owner import python_owns_finalization
from utils.app_integrations import ExternalIntegrationFanoutError, trigger_external_integrations
from utils.conversations.factory import deserialize_conversation
from utils.conversations.v3 import metrics, policy
from utils.conversations.v3.budget import Stage, measure_stage, require_headroom
from utils.conversations.v3.triggers import enqueue
from utils.executors import db_executor, run_blocking

logger = logging.getLogger(__name__)

RETRY = timedelta(minutes=5)


def idempotency_key(cid):
    return 'v3-created:' + cid


async def deliver(uid, *, budget=None):
    """Deliver every owed conversation-created fanout for one owner; returns the count delivered."""
    ids = await run_blocking(db_executor, writers.pending_created, uid)
    delivered, retry = 0, False
    for cid in ids:
        require_headroom(budget, Stage.DELIVER)
        attempt = await run_blocking(db_executor, writers.claim_created, uid, cid)
        if not attempt:
            continue
        try:
            data = await run_blocking(db_executor, conversations_db.get_conversation, uid, cid)
            if data is None:
                # The claim saw the row, so an empty read is a failed decode, not an absence: retry it
                # (the attempt cap bounds a row that never reads back).
                raise LookupError('v3_created_payload_unreadable')
            if not python_owns_finalization(data):
                continue
            if not policy.created_eligible(data):
                # Re-checked on the payload actually sent: a row that turned private, hidden, locked or
                # deleted after the claim must never reach an external integration.
                await run_blocking(
                    db_executor, writers.finish_created, uid, cid, attempt, delivered=False, dropped=True
                )
                metrics.CREATED_DELIVERIES.labels('dropped').inc()
                continue
            with measure_stage(budget, Stage.DELIVER):
                await trigger_external_integrations(
                    uid,
                    deserialize_conversation(data),
                    idempotency_key=idempotency_key(cid),
                    require_delivery=True,
                    last_delivery_attempt=attempt >= writers.CREATED_MAX_ATTEMPTS,
                )
        except Exception as error:
            # The marker stays owed; the claim is released for a later wake, never a tight loop.
            metrics.CREATED_DELIVERIES.labels('retry').inc()
            logger.warning(
                'event=v3_created_delivery outcome=retry attempt=%d exception_type=%s',
                attempt,
                type(error).__name__ if not isinstance(error, ExternalIntegrationFanoutError) else 'fanout',
            )
            await run_blocking(db_executor, writers.finish_created, uid, cid, attempt, delivered=False)
            retry = True
            continue
        await run_blocking(db_executor, writers.finish_created, uid, cid, attempt, delivered=True)
        # The final attempt drops per-app failures itself, so it is counted apart from a clean delivery.
        final = attempt >= writers.CREATED_MAX_ATTEMPTS
        metrics.CREATED_DELIVERIES.labels('final_attempt' if final else 'delivered').inc()
        delivered += 1
    if len(ids) >= writers.CREATED_PAGE:
        # A full page may hide more owed rows; continue them on a later owner wake.
        retry = True
    if retry:
        # No cross-owner sweep owns this marker, so a wake that cannot be scheduled fails the current
        # task: Cloud Tasks retries it instead of the obligation waiting for the owner's next capture.
        await run_blocking(db_executor, enqueue, uid, at=datetime.now(timezone.utc) + RETRY)
    return delivered
