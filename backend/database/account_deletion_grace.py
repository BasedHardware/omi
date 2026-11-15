"""Persistence and transactional transitions for restorable deletions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal, TypedDict

from google.cloud.firestore_v1 import transactional

from database.account_deletion_marker import (
    account_deletion_document,
    account_deletion_firestore_client,
)
from database.account_deletion_policy import ACCOUNT_DELETION_GRACE_STATUS
from database.fsr_read_cache import cache_writer


class DeletionGraceIntent(TypedDict):
    """Result of admitting or joining a grace-window deletion intent."""

    wipe_job_id: str
    dispatch_claimed: bool
    mode: Literal['created', 'joined', 'legacy']
    wipe_status: str
    wipe_due_at: datetime | None


def aware_utc_datetime(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@transactional
def _mark_user_deletion_grace_intent_txn(transaction, doc_ref, wipe_job_id: str, wipe_due_at: datetime):
    snapshot = doc_ref.get(transaction=transaction)
    data = (snapshot.to_dict() or {}) if snapshot.exists else {}
    status = data.get('wipe_status')
    existing_job_id = data.get('wipe_job_id')

    if status == ACCOUNT_DELETION_GRACE_STATUS and isinstance(existing_job_id, str) and existing_job_id:
        return {
            'wipe_job_id': existing_job_id,
            'dispatch_claimed': False,
            'mode': 'joined' if data.get('grace_actions_complete') is True else 'created',
            'wipe_status': status,
            'wipe_due_at': data.get('wipe_due_at'),
        }

    if status in {'deleting_auth', 'pending', 'retrying', 'running', 'failed', 'billing_failed', 'completed'}:
        return {
            'wipe_job_id': existing_job_id if isinstance(existing_job_id, str) else '',
            'dispatch_claimed': False,
            'mode': 'legacy',
            'wipe_status': status,
            'wipe_due_at': data.get('wipe_due_at'),
        }

    now = datetime.now(timezone.utc)
    transaction.set(
        doc_ref,
        {
            'uid': doc_ref.id,
            'wipe_status': ACCOUNT_DELETION_GRACE_STATUS,
            'wipe_intent_at': now,
            'wipe_queued_at': now,
            'wipe_job_id': wipe_job_id,
            'wipe_due_at': wipe_due_at,
            'grace_actions_complete': False,
            'wipe_requested_erase_now': False,
        },
        merge=True,
    )
    return {
        'wipe_job_id': wipe_job_id,
        'dispatch_claimed': True,
        'mode': 'created',
        'wipe_status': ACCOUNT_DELETION_GRACE_STATUS,
        'wipe_due_at': wipe_due_at,
    }


@cache_writer('deletion_marker_cache')
def mark_user_deletion_grace_intent(uid: str, wipe_due_at: datetime) -> DeletionGraceIntent:
    """Create or join a restorable deletion marker without dispatching a wipe."""
    if wipe_due_at.tzinfo is None:
        raise ValueError('wipe_due_at must be timezone-aware')
    client = account_deletion_firestore_client()
    doc_ref = account_deletion_document(uid, firestore_client=client)
    result = _mark_user_deletion_grace_intent_txn(client.transaction(), doc_ref, uuid.uuid4().hex, wipe_due_at)
    return result  # type: ignore[return-value]


@transactional
def _promote_grace_to_immediate_txn(transaction, doc_ref, generated_job_id: str) -> dict | None:
    snapshot = doc_ref.get(transaction=transaction)
    if not snapshot.exists:
        return None
    data = snapshot.to_dict() or {}
    if data.get('wipe_status') != ACCOUNT_DELETION_GRACE_STATUS:
        return None
    job_id = data.get('wipe_job_id')
    if not isinstance(job_id, str) or not job_id:
        job_id = generated_job_id
    now = datetime.now(timezone.utc)
    transaction.update(
        doc_ref,
        {
            'wipe_status': 'pending',
            'wipe_job_id': job_id,
            'wipe_due_at': now,
            'wipe_queued_at': now,
            'wipe_requested_erase_now': True,
        },
    )
    return {'wipe_job_id': job_id, 'dispatch_claimed': True}


@cache_writer('deletion_marker_cache')
def promote_grace_to_immediate(uid: str) -> dict | None:
    """Make an existing grace intent immediately wipeable for an erase-now request."""
    client = account_deletion_firestore_client()
    doc_ref = account_deletion_document(uid, firestore_client=client)
    return _promote_grace_to_immediate_txn(client.transaction(), doc_ref, uuid.uuid4().hex)


@transactional
def _mark_user_deletion_grace_actions_complete_txn(transaction, doc_ref, wipe_job_id: str) -> bool:
    snapshot = doc_ref.get(transaction=transaction)
    data = (snapshot.to_dict() or {}) if snapshot.exists else {}
    if data.get('wipe_status') != ACCOUNT_DELETION_GRACE_STATUS or data.get('wipe_job_id') != wipe_job_id:
        return False
    now = datetime.now(timezone.utc)
    transaction.update(
        doc_ref,
        {
            'grace_actions_complete': True,
            'billing_cancelled_at': now,
            'sessions_revoked_at': now,
            'grace_actions_completed_at': now,
        },
    )
    return True


@cache_writer('deletion_marker_cache')
def mark_user_deletion_grace_actions_complete(uid: str, wipe_job_id: str) -> bool:
    client = account_deletion_firestore_client()
    doc_ref = account_deletion_document(uid, firestore_client=client)
    return _mark_user_deletion_grace_actions_complete_txn(client.transaction(), doc_ref, wipe_job_id)


@transactional
def _restore_user_deletion_txn(transaction, doc_ref) -> str:
    snapshot = doc_ref.get(transaction=transaction)
    if not snapshot.exists:
        return 'not_pending'
    data = snapshot.to_dict() or {}
    if data.get('wipe_status') != ACCOUNT_DELETION_GRACE_STATUS:
        return 'not_pending'
    if data.get('grace_actions_complete') is not True:
        return 'actions_incomplete'
    due_at = aware_utc_datetime(data.get('wipe_due_at'))
    now = datetime.now(timezone.utc)
    if due_at is None or due_at <= now:
        return 'window_expired'
    transaction.update(doc_ref, {'wipe_status': 'cancelled', 'wipe_cancelled_at': now, 'wipe_restored_at': now})
    return 'restored'


@cache_writer('deletion_marker_cache')
def restore_user_deletion(uid: str) -> str:
    """Cancel a grace-period wipe unless the due-time worker has won the race."""
    client = account_deletion_firestore_client()
    doc_ref = account_deletion_document(uid, firestore_client=client)
    return _restore_user_deletion_txn(client.transaction(), doc_ref)


def grace_wipe_is_due(data: dict, now: datetime) -> bool:
    due_at = aware_utc_datetime(data.get('wipe_due_at'))
    return data.get('grace_actions_complete') is True and due_at is not None and due_at <= now


def pending_grace_wipes(docs, limit: int, now: datetime) -> list[dict]:
    """Select incomplete admission receipts and deadline-expired grace wipes."""
    results: list[dict] = []
    if limit <= 0:
        return results
    for doc in docs:
        if len(results) >= limit:
            break
        data = doc.to_dict() or {}
        if data.get('grace_actions_complete') is not True or grace_wipe_is_due(data, now):
            results.append(data | {'uid': doc.id})
    return results


def claim_due_grace_txn(transaction, doc_ref, uid: str, data: dict, now: datetime) -> str | None:
    if not grace_wipe_is_due(data, now):
        return None
    transaction.update(doc_ref, {'wipe_status': 'retrying', 'wipe_claimed_at': now})
    return uid
