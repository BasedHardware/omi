"""Bounded completed-minimum repair, invoked by the existing scheduled sync sequencer sweep.

Only server-provenance debt is indexed. Historical rows without provenance are
not guessed from their nonempty title. The durable cursor rotates past blocked
owners; one global lease bounds admissions across replicas.
"""

from __future__ import annotations

import time
import uuid
import logging
from typing import Any, Callable, cast

from google.cloud import firestore
from google.api_core.exceptions import FailedPrecondition
from config.summary_guarantee import (
    repair_enabled,
    REPAIR_INTERVAL_SECONDS,
    REPAIR_SCAN_LIMIT,
    REPAIR_QUERY_PAGE_LIMIT,
    REPAIR_SCAN_TIME_BUDGET_SECONDS,
    REPAIR_ADMISSION_LIMIT,
    REPAIR_PER_OWNER_TICK_LIMIT,
)
from database._client import get_firestore_client
from database.account_deletion_marker import account_deletion_blocks_user_work
from database.summary_debt_queries import due_conversations
from database.batch_pipeline_privacy import assert_batch_write_allowed, BatchPrivacyBlocked
from utils.conversations import summary_delivery as delivery
from utils.sync import reprocess
from utils.enrichment.age_gate import max_age_seconds

Row = dict[str, Any]
_scan_clock = time.monotonic
CURSOR = 'maintenance/summary_debt_repair_v1'
logger = logging.getLogger(__name__)


def redrive(client: Any, uid: str, conversation_id: str, *, now: float) -> bool:
    """Reuse the same obligation; no new finalization generation is admitted."""
    if account_deletion_blocks_user_work(uid):
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
            from utils.enrichment.age_gate import expired, parked, park_row

            if old and parked(old):
                return {}, True
            if old and (old.get('lease_until', 0) > now or old.get('summary_seen')):
                return {}, True
            if old and old.get('summary_blocked_reason') == 'empty_output_exhausted':
                # The conversation's transactional revision writer reopened its
                # debt. Its current eligibility is authoritative; reopen the
                # matching dormant outbox in this same admission transaction.
                old = {**old, 'summary_blocked_reason': None, 'summary_empty_failures': 0}
            new, _ = operation(old)
            # With the age gate off, legacy due-only debt may lack pending
            # metadata. Its existing due time conservatively bounds the wake.
            if max_age_seconds():
                pending = row['summary_first_pending_at']
            else:
                pending = row.get('summary_first_pending_at')
                if pending is None:
                    pending = due
            new['first_pending_at'] = min(new['first_pending_at'], pending)
            new['summary_deadline_at'] = min(new.get('summary_deadline_at', due), due)
            new['due_at'] = min(new['due_at'], due)
            new['language'] = row.get('language') or (old.get('language') if old else None) or 'en'
            new['summary_lane'] = row.get('summary_lane', 'unknown')
            new['summary_repair'] = True
            new['summary_expected_revision'] = row.get('sync_content_revision')
            if expired(new, row.get('created_at'), now=now):
                transaction.set(outbox, park_row(new, now=now))
                return {}, True
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
    counts = {'scanned': 0, 'admitted': 0, 'near_expiry_admitted': 0, 'errors': 0, 'expired_seen': 0}
    if not repair_enabled():
        return counts
    scan_deadline = _scan_clock() + REPAIR_SCAN_TIME_BUDGET_SECONDS
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
    # Scan/account only after the claim commits: Firestore may replay its
    # callback. Keep counts and gauge publication outside retryable callbacks.
    # Versioned nested cursors coexist with the legacy flat fields. An old
    # ASC cursor must never be reused for the new DESC phase.
    progress: Row = dict(cursor.get('phases') or {}) if cursor.get('version') == 2 else {}
    window = max_age_seconds()
    if not window:
        # Gate-off pagination retains the legacy flat due/name cursor. Never
        # reinterpret the newer pending-time phase cursor in this order.
        progress = {'newest': cursor if cursor.get('pending') is None else None}
    attempts = 0
    owner_attempts: dict[str, int] = {}
    overdue = 0
    oldest = 0.0
    for phase in ('near_expiry', 'newest'):
        if (
            attempts >= REPAIR_ADMISSION_LIMIT
            or counts['scanned'] >= REPAIR_SCAN_LIMIT
            or _scan_clock() >= scan_deadline
        ):
            break
        walk = progress.get(phase)
        last = None
        interrupted = False
        exhausted = False
        while (
            attempts < REPAIR_ADMISSION_LIMIT
            and counts['scanned'] < REPAIR_SCAN_LIMIT
            and _scan_clock() < scan_deadline
        ):
            limit = min(REPAIR_QUERY_PAGE_LIMIT, REPAIR_SCAN_LIMIT - counts['scanned'])
            try:
                page = due_conversations(now=current, phase=phase, limit=limit, after=walk, firestore_client=client)
            except FailedPrecondition:
                if phase != 'newest':
                    raise
                # Hard-fail only this phase; finish still commits near-expiry
                # progress and publishes this tick's counts. No alternate query.
                logger.warning('event=summary_debt_repair_newest_index_unavailable outcome=error')
                counts['errors'] += 1
                break
            # Count every returned document, including a fetched tail left for
            # next tick. No later RPC starts once attempts/time are exhausted.
            counts['scanned'] += len(page)
            exhausted = len(page) < limit
            for snapshot in page:
                if attempts >= REPAIR_ADMISSION_LIMIT or _scan_clock() >= scan_deadline:
                    interrupted = True
                    break
                previous = last
                last = snapshot
                row: Row = snapshot.to_dict() or {}
                if delivery.refusal(row):
                    continue
                parts = snapshot.reference.path.split('/')
                if (len(parts) != 4) or (parts[0] != 'users') or (parts[2] != 'conversations'):
                    continue
                if account_deletion_blocks_user_work(parts[1]):
                    continue
                from utils.enrichment.age_gate import expired

                if expired(
                    {'first_pending_at': row.get('summary_first_pending_at')}, row.get('created_at'), now=current
                ):
                    counts['expired_seen'] += 1
                    continue
                overdue += 1
                oldest = max(oldest, current - row['summary_due_at'])
                if owner_attempts.get(parts[1], 0) >= REPAIR_PER_OWNER_TICK_LIMIT:
                    # Discovery progress is independent of admission. Keep the
                    # conversation's durable due debt for a later pass/wrap;
                    # pinning this cursor here can hide every later owner.
                    continue
                if _scan_clock() >= scan_deadline:
                    last = previous
                    interrupted = True
                    break
                attempts += 1
                owner_attempts[parts[1]] = owner_attempts.get(parts[1], 0) + 1
                try:
                    admitted = int(redrive(client, parts[1], parts[3], now=current))
                    counts['admitted'] += admitted
                    if phase == 'near_expiry':
                        counts['near_expiry_admitted'] += admitted
                except Exception:
                    # Existing sweep owns retry. Do not print document contents/errors.
                    counts['errors'] += 1
            # Every examined row advances discovery, including owner deferrals.
            # Fetched rows left unexamined by admission/time limits do not.
            # Use the last examined row, never a previous phase's page tail
            # (which may be empty when a later phase query fails).
            if last is not None:
                row = last.to_dict() or {}
                walk = {
                    'phase': phase,
                    'window': max_age_seconds(),
                    'path': last.reference.path,
                    'due': row.get('summary_due_at'),
                    'pending': row.get('summary_first_pending_at') if window else None,
                }
            if exhausted or attempts >= REPAIR_ADMISSION_LIMIT or _scan_clock() >= scan_deadline:
                break
        if last is not None and (interrupted or not exhausted):
            progress[phase] = walk
        elif exhausted and not interrupted:
            progress[phase] = None
        # A first-row interruption preserves the input cursor (or a rewind).
    delivery.DEBT.set(overdue)
    delivery.OLDEST.set(oldest)
    delivery.SAMPLED_AT.set(current)
    delivery.EXPIRED_SEEN.set(counts['expired_seen'])
    delivery.NEAR_EXPIRY_ADMITTED.set(counts['near_expiry_admitted'])

    @firestore.transactional
    def finish(transaction: Any) -> None:
        old: Row = cursor_ref.get(transaction=transaction).to_dict() or {}
        if old.get('owner') != owner:
            return
        transaction.update(
            cursor_ref,
            {
                'lease_until': 0,
                'version': 2,
                'phases': progress if window else {},
                'path': (progress.get('newest') or {}).get('path') if not window else None,
                'due': (progress.get('newest') or {}).get('due') if not window else None,
                'pending': None,
            },
        )

    finish(client.transaction())
    # Count completed ticks once, outside Firestore's replayable callbacks.
    delivery.REPAIR.labels(outcome='scanned').inc(counts['scanned'])
    delivery.REPAIR.labels(outcome='admitted').inc(counts['admitted'])
    delivery.REPAIR.labels(outcome='error').inc(counts['errors'])
    delivery.REPAIR.labels(outcome='expired_seen').inc(counts['expired_seen'])
    delivery.REPAIR.labels(outcome='near_expiry_admitted').inc(counts['near_expiry_admitted'])
    return counts
