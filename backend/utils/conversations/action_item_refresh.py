"""Automatic refresh orchestration. Persistence precedes vectors, claim, and delivery.

Existing rows never enter task-app delivery or reminder rescheduling. This includes
Apple-linked tasks: preserving their original IDs and fields avoids replacement's
last-writer-wins problem. Delivery of newly added rows is claimed once, not retried
on an ambiguous provider outcome. The legacy writer handles all other triggers.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from config.action_item_identity import action_item_refresh_preserve_enabled
from database import action_item_refresh as refresh_db
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.executors import postprocess_executor, submit_with_context
from utils.metrics import OMI_ACTION_ITEM_REFRESH_TOTAL
from utils.notification_dispatch import dispatch_action_item_reminder
from utils.task_sync import auto_sync_action_items_batch

logger = logging.getLogger(__name__)
OUTCOMES = ('kept_existing', 'added_new', 'transferred_from_donor', 'skipped_duplicate', 'disabled')


def _emit(counts: dict[str, int]) -> None:
    for outcome in OUTCOMES:
        OMI_ACTION_ITEM_REFRESH_TOTAL.labels(outcome=outcome).inc(counts.get(outcome, 0))
    logger.info(
        'event=action_item_identity mode=preserve kept_existing=%d added_new=%d '
        'transferred_from_donor=%d skipped_duplicate=%d disabled=%d',
        *(counts.get(outcome, 0) for outcome in OUTCOMES),
    )


def preserve(uid: str, conversation: Any, items: list[dict], trigger: Any, vectors: Callable) -> bool:
    if trigger not in (ProcessingTrigger.SMART_MERGE, ProcessingTrigger.SYNC_UPDATE):
        return False
    if not action_item_refresh_preserve_enabled():
        _emit({'disabled': 1})
        return False
    result = refresh_db.reconcile(
        uid, conversation.id, items, expected_revision=getattr(conversation, 'sync_content_revision', None)
    )
    if result is None:
        return False
    _emit(result['counts'])
    # Read persisted rows at claim, after vectors. Never enqueue before durable task creation.
    # Vector payload uses current state on retry, not a possibly edited extraction.
    pending = result['pending']
    if pending:
        # Vector writes are projections only. Claim remains pending if persistence fails.
        from_rows = {item['id']: item for item in refresh_db.pending_rows(uid, conversation.id, pending)}
        vectors(uid, [{'action_item_id': tid, 'description': row['description']} for tid, row in from_rows.items()])
    deliverable = refresh_db.claim_delivery(uid, conversation.id, pending)
    if deliverable:
        submit_with_context(postprocess_executor, _deliver, uid, conversation.id, deliverable)
    return True


def _deliver(uid: str, conversation_id: str, rows: list[dict]) -> None:
    rows = [
        row
        for row in refresh_db.pending_rows(uid, conversation_id, [item['id'] for item in rows])
        if not row.get('completed')
        and not row.get('exported')
        and not row.get('sync_requested')
        and not row.get('apple_reminder_id')
    ]
    for row in rows:
        if row.get('due_at'):
            dispatch_action_item_reminder(
                user_id=uid,
                action_item_id=row['id'],
                description=row['description'],
                due_at=row['due_at'].isoformat(),
            )
    asyncio.run(auto_sync_action_items_batch(uid, rows))


def transfer_donor(uid: str, donor_id: str, survivor_id: str) -> None:
    if not action_item_refresh_preserve_enabled():
        _emit({'disabled': 1})
        return
    result = refresh_db.reconcile(uid, survivor_id, [], expected_revision=None, donor_id=donor_id)
    if result is not None:
        _emit(result['counts'])
