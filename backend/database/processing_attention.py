"""Owner-scoped attention ledger and generation-fenced user retry claims."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from database._client import db, run_transactional

LIMIT = 100


def items_ref(uid: str) -> Any:
    return db.collection('users').document(uid).collection('processing_attention_items')


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


def list_items(uid: str, limit: int | None = None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    query = items_ref(uid).where(filter=FieldFilter('active', '==', True))
    if limit is not None:
        query = query.limit(limit)
    for snapshot in query.stream():
        item = snapshot.to_dict() or {}
        conv = db.collection('users').document(uid).collection('conversations').document(item['conversation_id']).get()
        row = conv.to_dict() if conv.exists else None
        if not unresolved(row):
            snapshot.reference.update({'active': False, 'resolved_at': datetime.now(timezone.utc)})
            continue
        claim_ref = conv.reference.collection('processing_retry_claims').document(
            claim_id(item['conversation_id'], item['generation'])
        )
        claim_snapshot = claim_ref.get()
        if claim_snapshot.exists:
            operation = claim_snapshot.to_dict() or {}
            if operation['state'] == 'failed' and item.get('retry', {}).get('state') == 'failed':
                item['retryable'] = True  # Repair items made permanently non-retryable by the old ledger.
            item['retry'] = {'state': operation['state'], 'operation_id': operation['operation_id']}
        item['title'] = (row or {}).get('user_title') or ((row or {}).get('structured') or {}).get('title')
        item.pop('generation', None)
        item.pop('active', None)
        result.append(item)
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


def pending_conversations(uid: str) -> list[dict[str, Any]]:
    collection = db.collection('users').document(uid).collection('conversations')
    rows = collection.where(filter=FieldFilter('status', '==', 'processing')).limit(LIMIT).stream()
    result = []
    for snapshot in rows:
        row = snapshot.to_dict() or {}
        if (
            row.get('deleted')
            or row.get('is_deleted')
            or row.get('discarded')
            or row.get('finalization_status') in {'dead_letter', 'completed'}
        ):
            continue
        result.append(
            {
                'id': 'conv:' + snapshot.id,
                'kind': 'conversation',
                'state': 'queued' if row.get('finalization_status') == 'queued' else 'summarizing',
                'conversation_ids': [snapshot.id],
                **timing(row),
                'updated_at': row.get('updated_at') or row.get('processing_admitted_at') or row.get('created_at'),
            }
        )
    return result
