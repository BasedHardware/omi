"""Owner-scoped attention ledger and generation-fenced user retry claims."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from config.episodes import home_step_projection_enabled
from utils.conversations import home_step

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from utils.conversations import phase_shadow

from database._client import db, get_firestore_client, run_transactional

LIMIT = 100
# Expiry cleanup runs inside the read path, so each query is bounded to
# SCAN_LIMIT rows. A full read pages internally on the last scanned document,
# not the last returned one, so filtering cannot truncate the active set.
SCAN_LIMIT = 500
NON_RETRYABLE_ITEM_TTL = timedelta(days=7)
PERMANENTLY_NON_RETRYABLE_FAILURE_CODES = frozenset({'recovery_structure_unavailable'})


def non_retryable_expiry_enabled() -> bool:
    return os.getenv('PROCESSING_ATTENTION_NON_RETRYABLE_EXPIRY_ENABLED', 'true').strip().lower() != 'false'


def expired_non_retryable(item: dict[str, Any], now: datetime) -> bool:
    created_at = item.get('created_at')
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        except ValueError:
            return False
    if not isinstance(created_at, datetime):
        return False
    created_at = (
        created_at.replace(tzinfo=timezone.utc) if created_at.tzinfo is None else created_at.astimezone(timezone.utc)
    )
    return (
        item.get('failure_code') in PERMANENTLY_NON_RETRYABLE_FAILURE_CODES
        and not item.get('retryable')
        and item.get('retry', {}).get('state') != 'in_progress'
        and created_at <= now - NON_RETRYABLE_ITEM_TTL
    )


def expire_in_transaction(transaction: Any, observed: Any, now: datetime) -> bool:
    """Expire only the exact observed version; retries and deletes win over a stale poll."""
    current = observed.reference.get(transaction=transaction)
    item = current.to_dict() or {}
    if (
        not current.exists
        or item != observed.to_dict()
        or getattr(current, 'update_time', None) != getattr(observed, 'update_time', None)
        or not item.get('active')
        or not expired_non_retryable(item, now)
    ):
        return False
    claim_ref = (
        observed.reference.parent.parent.collection('conversations')
        .document(item['conversation_id'])
        .collection('processing_retry_claims')
        .document(claim_id(item['conversation_id'], item['generation']))
    )
    operation = claim_ref.get(transaction=transaction).to_dict() or {}
    if operation.get('state') == 'in_progress' or (
        operation.get('state') == 'failed' and item.get('retry', {}).get('state') == 'failed'
    ):
        return False
    transaction.update(observed.reference, {'active': False, 'expired_at': now, 'expiry_reason': 'non_retryable_ttl'})
    return True


def items_ref(uid: str, *, firestore_client: Any | None = None) -> Any:
    return (
        (firestore_client or get_firestore_client())
        .collection('users')
        .document(uid)
        .collection('processing_attention_items')
    )


def generation(row: dict[str, Any]) -> str:
    return f"{row.get('finalization_revision', 0)}:{row.get('sync_content_revision', 0)}:{row.get('finalization_job_id', '')}"


def item_id(conversation_id: str, row: dict[str, Any]) -> str:
    return 'conv-summary:' + conversation_id + ':' + hashlib.sha256(generation(row).encode()).hexdigest()[:24]


def timing(row: dict[str, Any]) -> dict[str, Any]:
    start = row.get('started_at') or row.get('created_at')
    end = row.get('finished_at') or start
    duration = max(0, (end - start).total_seconds()) if isinstance(start, datetime) and isinstance(end, datetime) else 0
    return {'started_at': start, 'duration_seconds': duration}


def create_in_transaction(
    transaction: Any,
    uid: str,
    conversation_ref: Any,
    row: dict[str, Any],
    updates: dict[str, Any],
    failure_code: str,
    now: datetime,
) -> None:
    """Call before ANY writes, after photo reads. The job's fence prevents duplicate terminals."""
    ref = conversation_ref.parent.parent.collection('processing_attention_items').document(
        item_id(conversation_ref.id, row)
    )
    snapshot = ref.get(transaction=transaction)
    if snapshot.exists:
        return
    transaction.set(
        ref,
        {
            'id': ref.id,
            'kind': 'conversation_summary_failed',
            'conversation_id': conversation_ref.id,
            'generation': generation(row),
            'title': None,
            **timing(row),
            'failure_code': failure_code,
            'retryable': bool(updates.get('summary_retryable')),
            'created_at': now,
            'seen': False,
            'active': True,
            'retry': {'state': 'none', 'operation_id': None},
        },
    )


def unresolved(row: dict[str, Any] | None) -> bool:
    if not row or row.get('deleted') or row.get('is_deleted'):
        return False
    # Terminal minimum titles are not summaries; only generated content resolves an item.
    structured = row.get('structured') or {}
    return not bool(structured.get('overview'))


def _scan_pages(uid: str, start_after: Any | None, *, firestore_client: Any | None = None):
    """Yield active items in bounded pages, advancing on the last scanned document."""
    cursor = start_after
    while True:
        query = items_ref(uid, firestore_client=firestore_client).where(filter=FieldFilter('active', '==', True))
        if cursor is not None:
            query = query.start_after(cursor)
        query = query.limit(SCAN_LIMIT)
        page = list(query.stream())
        yield from page
        if len(page) < SCAN_LIMIT:
            return
        cursor = page[-1]


def list_items(
    uid: str,
    limit: int | None = None,
    start_after: Any | None = None,
    *,
    firestore_client: Any | None = None,
) -> list[dict[str, Any]]:
    if limit is not None and limit <= 0:
        return []
    client = firestore_client or get_firestore_client()
    result: list[dict[str, Any]] = []
    expiry_enabled = non_retryable_expiry_enabled()
    now = now_utc()
    for snapshot in _scan_pages(uid, start_after, firestore_client=client):
        item = snapshot.to_dict() or {}
        conv_ref = (
            client.collection('users').document(uid).collection('conversations').document(item['conversation_id'])
        )
        conv = conv_ref.get()
        row = conv.to_dict() if conv.exists else None
        if not unresolved(row):
            snapshot.reference.update({'active': False, 'resolved_at': datetime.now(timezone.utc)})
            continue
        claim_ref = conv_ref.collection('processing_retry_claims').document(
            claim_id(item['conversation_id'], item['generation'])
        )
        claim_snapshot = claim_ref.get()
        if claim_snapshot.exists:
            operation = claim_snapshot.to_dict() or {}
            if operation['state'] == 'failed' and item.get('retry', {}).get('state') == 'failed':
                item['retryable'] = True  # Repair items made permanently non-retryable by the old ledger.
            item['retry'] = {'state': operation['state'], 'operation_id': operation['operation_id']}
        if expiry_enabled and expired_non_retryable(item, now):
            if run_transactional(client, firestore.transactional(expire_in_transaction), snapshot, now):
                continue
        item['title'] = (row or {}).get('user_title') or ((row or {}).get('structured') or {}).get('title')
        item.pop('generation', None)
        item.pop('active', None)
        result.append(item)
        if limit is not None and len(result) >= limit:
            return result
    return result


# Normal durable processing requests are capped at 1500s in main.py. Match the
# existing sync run lock's 1800s lease, leaving five minutes of headroom.
RETRY_LEASE_SECONDS = 1800


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def claim_id(conversation_id: str, revision: str) -> str:
    return hashlib.sha256((conversation_id + ':' + revision).encode()).hexdigest()


def lease_live(operation: dict[str, Any], now: datetime) -> bool:
    expires = operation.get('lease_expires_at')
    if not isinstance(expires, datetime):
        created = operation.get('created_at')
        expires = created + timedelta(seconds=RETRY_LEASE_SECONDS) if isinstance(created, datetime) else None
    return isinstance(expires, datetime) and expires > now


class ClaimRejected(ValueError):
    pass


def claim_in_transaction(
    transaction: Any,
    conv_ref: Any,
    uid: str,
    attention_ref: Any = None,
    expected_generation: str | None = None,
    staged_writes: list[Any] | None = None,
    idempotency_key: str | None = None,
    restart_succeeded: bool = False,
) -> tuple[dict[str, Any], bool]:
    """One current lease per input generation, immutable attempt/key identities.

    All reads precede writes, including when retry-all stages multiple claims.
    Keys joining a running attempt remain pinned to that attempt after failure
    or abandonment. Attention keys always replay; explicit reprocess may admit
    a fresh attempt after success, while still sharing the active writer.
    """
    snapshot = conv_ref.get(transaction=transaction)
    row = snapshot.to_dict() if snapshot.exists else None
    item_snapshot = attention_ref.get(transaction=transaction) if attention_ref is not None else None
    if not row or row.get('deleted') or row.get('is_deleted'):
        raise ClaimRejected('not_found')
    revision = generation(row)
    current_ref = conv_ref.collection('processing_retry_claims').document(claim_id(conv_ref.id, revision))
    current_snapshot = current_ref.get(transaction=transaction)
    current = current_snapshot.to_dict() or {} if current_snapshot.exists else {}
    key_ref = (
        current_ref.collection('keys').document(hashlib.sha256(idempotency_key.encode()).hexdigest())
        if idempotency_key
        else None
    )
    key_snapshot = key_ref.get(transaction=transaction) if key_ref is not None else None
    replay = None
    if key_snapshot is not None and key_snapshot.exists:
        attempt_ref = current_ref.collection('attempts').document(key_snapshot.to_dict()['operation_id'])
        replay = attempt_ref.get(transaction=transaction).to_dict()
        if not replay:
            raise ClaimRejected('missing_attempt')  # Fail closed; never repay an unknown keyed attempt.
    item = None
    if item_snapshot is not None:
        item = item_snapshot.to_dict() if item_snapshot.exists else None
        if not item:
            raise ClaimRejected('not_found')
        if item.get('generation') != revision:
            raise ClaimRejected('not_retryable')
    if expected_generation is not None and expected_generation != revision:
        raise ClaimRejected('not_retryable')
    if replay is not None:
        return replay, False

    now = now_utc()
    owned = (
        not current
        or current.get('state') == 'failed'
        or (restart_succeeded and current.get('state') == 'succeeded')
        or (current.get('state') == 'in_progress' and not lease_live(current, now))
    )
    if item is not None and owned:
        retryable = item.get('retryable') or (
            current.get('state') == 'failed' and item.get('retry', {}).get('state') == 'failed'
        )
        if not item.get('active') or not retryable:
            raise ClaimRejected('not_retryable')
    writes: list[Any] = []
    if owned:
        attempt = int(current.get('attempt', 1 if current else 0)) + 1
        operation = {
            'operation_id': current_ref.id + ':' + str(attempt),
            'state': 'in_progress',
            'generation': revision,
            'conversation_id': conv_ref.id,
            'claim_id': current_ref.id,
            'attempt': attempt,
            'created_at': now,
            'lease_expires_at': now + timedelta(seconds=RETRY_LEASE_SECONDS),
        }
        if current.get('state') == 'in_progress':
            abandoned = {**current, 'state': 'failed', 'failure_code': 'lease_expired', 'completed_at': now}
            writes.append(
                ('set', (current_ref.collection('attempts').document(current['operation_id']), abandoned), {})
            )
        writes.append(('set', (current_ref, operation), {}))
        writes.append(('set', (current_ref.collection('attempts').document(operation['operation_id']), operation), {}))
    else:
        operation = current
        # Persist history for a pre-attempt-ledger claim when a key joins it.
        writes.append(('set', (current_ref.collection('attempts').document(operation['operation_id']), operation), {}))
    if key_ref is not None:
        writes.append(('set', (key_ref, {'operation_id': operation['operation_id']}), {}))
    if attention_ref is not None:
        writes.append(
            (
                'update',
                (
                    attention_ref,
                    {
                        'retry': {'state': operation['state'], 'operation_id': operation['operation_id']},
                        **({'retryable': True} if owned else {}),
                    },
                ),
                {},
            )
        )
    if staged_writes is not None:
        staged_writes.extend(writes)
    else:
        for method, args, kwargs in writes:
            getattr(transaction, method)(*args, **kwargs)
    return operation, owned


def claim(
    uid: str,
    conversation_id: str,
    attention_id: str | None = None,
    expected_generation: str | None = None,
    idempotency_key: str | None = None,
    restart_succeeded: bool = False,
) -> tuple[dict[str, Any], bool]:
    conv_ref = db.collection('users').document(uid).collection('conversations').document(conversation_id)
    return run_transactional(
        db,
        firestore.transactional(claim_in_transaction),
        conv_ref,
        uid,
        items_ref(uid).document(attention_id) if attention_id else None,
        expected_generation,
        idempotency_key=idempotency_key,
        restart_succeeded=restart_succeeded,
    )


def owns_live_claim(uid: str, operation: dict[str, Any]) -> bool:
    """Check ownership immediately before paid work, including delayed batch entries."""
    conv_ref = db.collection('users').document(uid).collection('conversations').document(operation['conversation_id'])
    snapshot = (
        conv_ref.collection('processing_retry_claims')
        .document(operation.get('claim_id') or claim_id(conv_ref.id, operation['generation']))
        .get()
    )
    current = snapshot.to_dict() or {} if snapshot.exists else {}
    return (
        current.get('operation_id') == operation['operation_id']
        and current.get('state') == 'in_progress'
        and lease_live(current, now_utc())
    )


def finish_in_transaction(
    transaction: Any, conv_ref: Any, operation: dict[str, Any], state: str, attention_ref: Any = None
) -> bool:
    current_ref = conv_ref.collection('processing_retry_claims').document(
        operation.get('claim_id') or claim_id(conv_ref.id, operation['generation'])
    )
    snapshot = current_ref.get(transaction=transaction)
    current = snapshot.to_dict() or {} if snapshot.exists else {}
    item_snapshot = attention_ref.get(transaction=transaction) if attention_ref is not None else None
    # An abandoned worker cannot overwrite a newer attempt or its item's state.
    if current.get('operation_id') != operation['operation_id'] or current.get('state') != 'in_progress':
        return False
    completed = {**current, 'state': state, 'completed_at': now_utc()}
    transaction.set(current_ref, completed)
    transaction.set(current_ref.collection('attempts').document(operation['operation_id']), completed)
    if item_snapshot is not None and item_snapshot.exists:
        updates: dict[str, Any] = {'retry': {'state': state, 'operation_id': operation['operation_id']}}
        if state == 'succeeded':
            updates['active'] = False
        transaction.update(attention_ref, updates)
    return True


def finish(uid: str, operation: dict[str, Any], state: str, attention_id: str | None = None) -> bool:
    conv_ref = db.collection('users').document(uid).collection('conversations').document(operation['conversation_id'])
    return run_transactional(
        db,
        firestore.transactional(finish_in_transaction),
        conv_ref,
        operation,
        state,
        items_ref(uid).document(attention_id) if attention_id else None,
    )


def pending_conversations(uid: str, *, exclude: Callable[[dict[str, Any]], bool] | None = None) -> list[dict[str, Any]]:
    """Filter-independent pending Home rows, without deciding the viewer's local day.

    Single-field indexes bound each candidate page; no account-history scan.
    Debt timestamps are cleared by successful summary processing. Supplemental
    captures use Home classification; its deadline never completes a stored job.
    """
    collection = db.collection('users').document(uid).collection('conversations')
    today_only = home_step_projection_enabled()
    filters = (
        [FieldFilter('status', 'in', ['processing', 'merging'])]
        if today_only
        else [FieldFilter('status', '==', 'processing')]
    )
    if today_only:
        filters.extend(
            [
                FieldFilter('home_transcription_deadline_at', '>', now_utc()),
                FieldFilter('summary_due_at', '>', 0),
            ]
        )
    result = []
    seen: set[str] = set()
    for candidate_filter in filters:
        query = collection.where(filter=candidate_filter).limit(LIMIT)
        while True:
            page = list(query.stream())
            owned_excluded = False
            stored_excluded = False
            for snapshot in page:
                if snapshot.id in seen:
                    continue
                seen.add(snapshot.id)
                row = snapshot.to_dict() or {}
                excluded = bool(
                    row.get('deleted')
                    or row.get('is_deleted')
                    or row.get('discarded')
                    or row.get('finalization_status') == 'dead_letter'
                    or (
                        row.get('status') in {'processing', 'merging'} and row.get('finalization_status') == 'completed'
                    )
                )
                step = home_step.classify(row) if today_only and not excluded else None
                # Home's age bound is presentation, not job completion. Preserve
                # the existing pending-work consumers until the job is terminal.
                stored_pending = row.get('status') in {'processing', 'merging'} and row.get(
                    'finalization_status'
                ) not in {'dead_letter', 'completed'}
                excluded = excluded or (
                    not stored_pending and step not in {home_step.TRANSCRIBING, home_step.WRITING_NOTES}
                    if today_only
                    else row.get('finalization_status') in {'dead_letter', 'completed'}
                )
                phase_shadow.observe('processing_attention', row, not excluded)
                if excluded:
                    if stored_pending or row.get('status') in {'processing', 'merging'}:
                        stored_excluded = True
                    continue
                if exclude is not None and exclude(dict(row, id=snapshot.id)):
                    owned_excluded = True
                    continue
                result.append(
                    {
                        'id': 'conv:' + snapshot.id,
                        'kind': 'conversation',
                        **({'home_step': step} if today_only and step is not None else {}),
                        'state': (
                            'transcribing'
                            if step == home_step.TRANSCRIBING
                            else ('queued' if row.get('finalization_status') == 'queued' else 'summarizing')
                        ),
                        'conversation_ids': [snapshot.id],
                        **timing(row),
                        'updated_at': row.get('updated_at')
                        or row.get('processing_admitted_at')
                        or row.get('created_at'),
                    }
                )
            if len(result) >= LIMIT:
                return result[:LIMIT]
            # Keep the existing owner-gap pagination, but never page through
            # history just because stale candidates failed Home classification.
            if len(page) < LIMIT or not (owned_excluded or stored_excluded):
                break
            query = query.start_after(page[-1])
    return result
