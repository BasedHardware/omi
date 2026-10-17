"""Bounded completed-minimum repair, invoked by the existing scheduled sync sequencer sweep.

Only server-provenance debt is indexed. Historical rows without provenance are
not guessed from their nonempty title. The durable cursor rotates past blocked
owners; one global lease bounds admissions across replicas.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Callable, cast

from google.cloud import firestore
from config.summary_guarantee import (
    enabled,
    repair_enabled,
    REPAIR_INTERVAL_SECONDS,
    REPAIR_SCAN_LIMIT,
    REPAIR_ADMISSION_LIMIT,
)
from database._client import get_firestore_client
from database.summary_debt_queries import due_conversations
from database.batch_pipeline_privacy import assert_batch_write_allowed, BatchPrivacyBlocked
from utils.conversations import summary_delivery as delivery
from utils.sync import reprocess

Row = dict[str, Any]
CURSOR = 'maintenance/summary_debt_repair_v1'


def redrive(client: Any, uid: str, conversation_id: str, *, now: float) -> bool:
    """Reuse the same obligation; no new finalization generation is admitted."""
    if not enabled(uid):
        return False
    admitted = False
    blocked_receipt: Row | None = None

    def mutate(document_id: str, operation: Callable[[Row | None], tuple[Row, tuple[Row, bool]]]) -> tuple[Row, bool]:
        @firestore.transactional
        def commit(transaction: Any) -> tuple[Row, bool]:
            nonlocal admitted, blocked_receipt
            admitted = False
            blocked_receipt = None
            ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)
            snapshot = ref.get(transaction=transaction)
            row: Row = snapshot.to_dict() or {}
            due = row.get('summary_due_at')
            if delivery.refusal(row) or not isinstance(due, (int, float)) or due > now:
                return {}, True
            assert_batch_write_allowed(client, transaction, uid, conversation_ids=[conversation_id])
            user: Row = client.collection('users').document(uid).get(transaction=transaction).to_dict() or {}
            # No credentials in background tasks, and never substitute Omi keys.
            if cast(Row, user.get('byok') or {}).get('active'):
                if row.get('summary_blocked_reason') != 'blocked_byok':
                    transaction.update(ref, {'summary_blocked_reason': 'blocked_byok'})
                    blocked_receipt = dict(lane=delivery.lane(row), reason='blocked_byok', present=False, latency=None)
                return {}, True
            outbox = client.collection(reprocess.COLLECTION).document(document_id)
            prior = outbox.get(transaction=transaction)
            old: Row | None = prior.to_dict() if prior.exists else None
            if old and (
                old.get('lease_until', 0) > now
                or old.get('summary_seen')
                or old.get('summary_blocked_reason') == 'empty_output_exhausted'
            ):
                return {}, True
            new, _ = operation(old)
            new['first_pending_at'] = min(new['first_pending_at'], row['summary_first_pending_at'])
            new['summary_deadline_at'] = min(new.get('summary_deadline_at', due), due)
            new['due_at'] = min(new['due_at'], due)
            new['language'] = row.get('language') or (old.get('language') if old else None) or 'en'
            new['summary_lane'] = row.get('summary_lane', 'unknown')
            new['summary_repair'] = True
            new['summary_expected_revision'] = row.get('sync_content_revision')
            # A repair wake must not invalidate an earlier delivery still
            # waiting for capacity. Leases and the conversation owner fence
            # duplicates; later revisions rotate the token as before.
            new.update(wake_generation=new.get('wake_generation', 0) + 1, task_due_at=now)
            transaction.set(outbox, new)
            admitted = True
            return {**new, '_wake': True}, False

        try:
            result = commit(client.transaction())
            delivery.emit(blocked_receipt)
            return result
        except BatchPrivacyBlocked:
            return {}, True

    reprocess.mark(uid, conversation_id, 'en', now=now, mutate=mutate)
    return admitted


def tick(*, now: float | None = None, client: Any = None) -> dict[str, int]:
    counts = {'scanned': 0, 'admitted': 0, 'errors': 0}
    if not repair_enabled():
        return counts
    current = time.time() if now is None else now
    client = client if client is not None else get_firestore_client()
    cursor_ref = client.document(CURSOR)
    owner = uuid.uuid4().hex

    @firestore.transactional
    def claim(transaction: Any) -> Row | None:
        old: Row = cursor_ref.get(transaction=transaction).to_dict() or {}
        if old.get('lease_until', 0) > current or old.get('next_at', 0) > current:
            return None
        transaction.set(
            cursor_ref,
            {
                **old,
                'owner': owner,
                'lease_until': current + REPAIR_INTERVAL_SECONDS,
                'next_at': current + REPAIR_INTERVAL_SECONDS,
            },
        )
        return old

    cursor = claim(client.transaction())
    if cursor is None:
        return counts
    page = due_conversations(now=current, limit=REPAIR_SCAN_LIMIT, after=cursor, firestore_client=client)
    attempts = 0
    overdue = 0
    oldest = 0.0
    for snapshot in page:
        counts['scanned'] += 1
        row: Row = snapshot.to_dict() or {}
        if delivery.refusal(row):
            continue
        parts = snapshot.reference.path.split('/')
        if len(parts) != 4 or parts[0] != 'users' or parts[2] != 'conversations' or not enabled(parts[1]):
            continue
        overdue += 1
        oldest = max(oldest, current - row['summary_due_at'])
        if attempts >= REPAIR_ADMISSION_LIMIT:
            continue
        attempts += 1
        try:
            counts['admitted'] += int(redrive(client, parts[1], parts[3], now=current))
        except Exception:
            # Existing sweep owns retry. Do not print document contents/errors.
            counts['errors'] += 1
    delivery.DEBT.set(overdue)
    delivery.OLDEST.set(oldest)
    delivery.SAMPLED_AT.set(current)

    @firestore.transactional
    def finish(transaction: Any) -> None:
        old: Row = cursor_ref.get(transaction=transaction).to_dict() or {}
        if old.get('owner') != owner:
            return
        last = page[-1] if len(page) == REPAIR_SCAN_LIMIT else None
        transaction.update(
            cursor_ref,
            {
                'lease_until': 0,
                'path': last.reference.path if last else None,
                'due': cast(Row, last.to_dict() or {}).get('summary_due_at') if last else None,
            },
        )

    finish(client.transaction())
    return counts
