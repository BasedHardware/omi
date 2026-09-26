"""Candidate integration outbox: claim, complete, list, redrive, and malformed dead-letter."""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast
from uuid import uuid4

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database._client import db
from database.candidates import (
    TASK_INTELLIGENCE_CONTROL_COLLECTION,
    TASK_INTELLIGENCE_CONTROL_DOCUMENT,
)
from database.durable_queue import ProcessOutcome, QueuePolicy, decide_attempt, redrive_patch
from database.read_boundary import parse_snapshot_strict
from models.task_intelligence import TaskWorkflowControl

CANDIDATE_INTEGRATION_OUTBOX_COLLECTION = 'candidate_integration_outbox'
CANDIDATE_INTEGRATION_POLICY = QueuePolicy(max_attempts=5, base_backoff_seconds=30, max_backoff_seconds=1800)


def _integration_outbox_ref(uid: str, candidate_id: str):
    return (
        db.collection('users').document(uid).collection(CANDIDATE_INTEGRATION_OUTBOX_COLLECTION).document(candidate_id)
    )


def _task_control_ref(uid: str):
    return (
        db.collection('users')
        .document(uid)
        .collection(TASK_INTELLIGENCE_CONTROL_COLLECTION)
        .document(TASK_INTELLIGENCE_CONTROL_DOCUMENT)
    )


def _snapshot_dict(snapshot: Any) -> dict[str, Any]:
    payload = snapshot.to_dict()
    return cast(dict[str, Any], payload) if isinstance(payload, dict) else {}


def claim_candidate_integration_dispatch(
    uid: str,
    candidate_id: str,
    *,
    account_generation: int,
    now: Optional[datetime] = None,
    lease_seconds: int = 300,
) -> Optional[str]:
    """Claim a durable accepted-task integration side effect for delivery."""

    outbox_ref = _integration_outbox_ref(uid, candidate_id)
    claim_time = now or datetime.now(timezone.utc)
    transaction = db.transaction()

    @firestore.transactional
    def apply(write_transaction):
        snapshot = outbox_ref.get(transaction=write_transaction)
        if not snapshot.exists:
            return None
        payload = _snapshot_dict(snapshot)
        control_snapshot = _task_control_ref(uid).get(transaction=write_transaction)
        control = TaskWorkflowControl()
        if control_snapshot.exists:
            control = parse_snapshot_strict(TaskWorkflowControl, control_snapshot)
        if payload.get('account_generation') != account_generation or control.account_generation != account_generation:
            write_transaction.update(
                outbox_ref,
                {
                    'status': 'suppressed',
                    'resolution_reason': 'account_generation_mismatch',
                    'updated_at': claim_time,
                },
            )
            return None
        if payload.get('status') in {'completed', 'suppressed', 'dead_letter'}:
            return None
        if payload.get('status') == 'processing':
            claimed_at = payload.get('claimed_at')
            if isinstance(claimed_at, datetime) and claimed_at + timedelta(seconds=lease_seconds) > claim_time:
                return None
        lease_token = uuid4().hex
        write_transaction.update(
            outbox_ref,
            {
                'status': 'processing',
                'attempt_count': int(payload.get('attempt_count', 0)) + 1,
                'lease_token': lease_token,
                'claimed_at': claim_time,
                'updated_at': claim_time,
            },
        )
        return lease_token

    return apply(transaction)


def complete_candidate_integration_dispatch(
    uid: str,
    candidate_id: str,
    *,
    account_generation: int,
    lease_token: str,
    succeeded: bool,
    now: Optional[datetime] = None,
    error_text: Optional[str] = None,
) -> bool:
    completion_time = now or datetime.now(timezone.utc)
    outbox_ref = _integration_outbox_ref(uid, candidate_id)
    transaction = db.transaction()

    @firestore.transactional
    def apply(write_transaction):
        snapshot = outbox_ref.get(transaction=write_transaction)
        if not snapshot.exists:
            return False
        payload = _snapshot_dict(snapshot)
        control_snapshot = _task_control_ref(uid).get(transaction=write_transaction)
        control = TaskWorkflowControl()
        if control_snapshot.exists:
            control = parse_snapshot_strict(TaskWorkflowControl, control_snapshot)
        if payload.get('account_generation') != account_generation or control.account_generation != account_generation:
            write_transaction.update(
                outbox_ref,
                {
                    'status': 'suppressed',
                    'resolution_reason': 'account_generation_mismatch',
                    'updated_at': completion_time,
                },
            )
            return False
        if payload.get('status') != 'processing' or payload.get('lease_token') != lease_token:
            return False
        if succeeded:
            write_transaction.update(
                outbox_ref,
                {
                    'status': 'completed',
                    'completed_at': completion_time,
                    'lease_token': None,
                    'updated_at': completion_time,
                    'last_error_text': None,
                    'dead_letter_reason': None,
                },
            )
            return True
        decision = decide_attempt(
            attempt_count=max(int(payload.get('attempt_count') or 0), 1),
            outcome=ProcessOutcome.retry(error_text or 'integration_failed', reason='integration_failed'),
            policy=CANDIDATE_INTEGRATION_POLICY,
            now=completion_time,
        )
        patch = {
            'status': 'dead_letter' if decision.terminal else 'failed',
            'completed_at': None,
            'lease_token': None,
            'updated_at': completion_time,
            'last_error_text': decision.error_text,
            'dead_letter_reason': decision.reason if decision.terminal else None,
        }
        if decision.available_at is not None:
            patch['available_at'] = decision.available_at
        write_transaction.update(outbox_ref, patch)
        return True

    return apply(transaction)


def redrive_candidate_integration_dead_letter(
    uid: str,
    candidate_id: str,
    *,
    account_generation: int,
    now: Optional[datetime] = None,
) -> bool:
    """Move a dead-lettered integration item back to ready by identity."""
    completion_time = now or datetime.now(timezone.utc)
    outbox_ref = _integration_outbox_ref(uid, candidate_id)
    transaction = db.transaction()

    @firestore.transactional
    def apply(write_transaction):
        snapshot = outbox_ref.get(transaction=write_transaction)
        if not snapshot.exists:
            return False
        payload = _snapshot_dict(snapshot)
        if payload.get('account_generation') != account_generation:
            return False
        if payload.get('status') != 'dead_letter':
            return False
        write_transaction.update(outbox_ref, redrive_patch(now=completion_time))
        return True

    return apply(transaction)


def dead_letter_malformed_candidate_integration(
    uid: str,
    candidate_id: str,
    *,
    account_generation: int,
    error_text: str,
    now: Optional[datetime] = None,
) -> bool:
    """Park a malformed outbox row to dead_letter instead of retrying it forever."""
    completion_time = now or datetime.now(timezone.utc)
    outbox_ref = _integration_outbox_ref(uid, candidate_id)
    transaction = db.transaction()

    @firestore.transactional
    def apply(write_transaction):
        snapshot = outbox_ref.get(transaction=write_transaction)
        if not snapshot.exists:
            return False
        payload = _snapshot_dict(snapshot)
        if payload.get('account_generation') != account_generation:
            return False
        if payload.get('status') in {'completed', 'suppressed', 'dead_letter'}:
            return False
        write_transaction.update(
            outbox_ref,
            {
                'status': 'dead_letter',
                'lease_token': None,
                'updated_at': completion_time,
                'last_error_text': error_text[:2000],
                'dead_letter_reason': 'malformed',
            },
        )
        return True

    return apply(transaction)


def list_candidate_integration_dispatches(
    uid: str,
    *,
    account_generation: int,
    limit: int = 100,
) -> list[dict[str, Any]]:
    query = (
        db.collection('users')
        .document(uid)
        .collection(CANDIDATE_INTEGRATION_OUTBOX_COLLECTION)
        .where(filter=FieldFilter('account_generation', '==', account_generation))
        .where(filter=FieldFilter('status', 'in', ['pending', 'failed', 'processing']))
        .limit(limit)
    )
    rows = [_snapshot_dict(snapshot) for snapshot in query.stream()]
    now = datetime.now(timezone.utc)
    ready: list[dict[str, Any]] = []
    for row in rows:
        available_at = row.get('available_at')
        if isinstance(available_at, datetime) and available_at > now:
            continue
        ready.append(row)
    return ready


__all__ = [
    'CANDIDATE_INTEGRATION_POLICY',
    'claim_candidate_integration_dispatch',
    'complete_candidate_integration_dispatch',
    'dead_letter_malformed_candidate_integration',
    'list_candidate_integration_dispatches',
    'redrive_candidate_integration_dead_letter',
]
