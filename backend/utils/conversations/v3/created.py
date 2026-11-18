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
from utils.app_integrations import ExternalIntegrationFanoutError, trigger_external_integrations
from utils.conversations.factory import deserialize_conversation
from utils.conversations.v3 import metrics
from utils.conversations.v3.triggers import enqueue
from utils.executors import db_executor, run_blocking

logger = logging.getLogger(__name__)

RETRY = timedelta(minutes=5)


def idempotency_key(cid):
    return 'v3-created:' + cid


async def deliver(uid):
    """Deliver every owed conversation-created fanout for one owner; returns the count delivered."""
    ids = await run_blocking(db_executor, writers.pending_created, uid)
    delivered, retry = 0, False
    for cid in ids:
        attempt = await run_blocking(db_executor, writers.claim_created, uid, cid)
        if not attempt:
            continue
        try:
            data = await run_blocking(db_executor, conversations_db.get_conversation, uid, cid)
            conversation = deserialize_conversation(data) if data else None
            if conversation is not None:
                await trigger_external_integrations(
                    uid,
                    conversation,
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
        metrics.CREATED_DELIVERIES.labels('delivered').inc()
        delivered += 1
    if retry:
        try:
            await run_blocking(db_executor, enqueue, uid, at=datetime.now(timezone.utc) + RETRY)
        except Exception as error:
            # The owner's next capture or wake drains the marker; no cross-owner sweep owns it.
            metrics.RECONCILES.labels('dispatch_error').inc()
            logger.warning('event=v3_created_delivery_wake outcome=deferred exception_type=%s', type(error).__name__)
    return delivered
