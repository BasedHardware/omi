"""Candidate integration outbox: claim, complete, list, redrive, and malformed dead-letter."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast
from uuid import uuid4

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

try:
    from database._client import db
except Exception:
    db = None
from database.durable_queue import ProcessOutcome, QueuePolicy, decide_attempt, redrive_patch
from database.read_boundary import parse_snapshot_strict
from models.task_intelligence import TaskWorkflowControl

logger = logging.getLogger(__name__)

CANDIDATE_INTEGRATION_OUTBOX_COLLECTION = 'candidate_integration_outbox'
TASK_INTELLIGENCE_CONTROL_COLLECTION = 'task_intelligence_control'
TASK_INTELLIGENCE_CONTROL_DOCUMENT = 'state'
CANDIDATE_INTEGRATION_POLICY = QueuePolicy(max_attempts=5, base_backoff_seconds=30, max_backoff_seconds=1800)

MAX_ID_LENGTH = 128
MIN_LEASE_SECONDS = 1
MAX_LEASE_SECONDS = 86400
DEFAULT_LEASE_SECONDS = 300
MIN_QUERY_LIMIT = 1
MAX_QUERY_LIMIT = 1000
DEFAULT_QUERY_LIMIT = 100
MAX_ERROR_TEXT_LENGTH = 2000


def _clean_id(id_val: Any) -> str:
    """Validate and sanitize ID strings against injection, null bytes, and path traversal."""
    if not isinstance(id_val, str):
        return ''
    cleaned = id_val.strip()
    if (
        not cleaned
        or len(cleaned) > MAX_ID_LENGTH
        or '/' in cleaned
        or '\\' in cleaned
        or '..' in cleaned
        or '\x00' in cleaned
    ):
        return ''
    return cleaned


def _ensure_utc(dt: Any) -> datetime | None:
    """Normalize datetime to UTC-aware, preventing naive vs aware comparison/subtraction errors."""
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return None


def _resolve_client(firestore_client: Any = None) -> Any:
    """Resolve Firestore client with DI precedence and module/lazy fallback."""
    if firestore_client is not None:
        return firestore_client
    if db is not None:
        return db
    try:
        from database._client import get_firestore_client

        c = get_firestore_client()
        if c is not None:
            return c
    except Exception:
        pass
    return None


def _integration_outbox_ref(uid: str, candidate_id: str, *, firestore_client: Any = None) -> Any:
    cleaned_uid = _clean_id(uid)
    if not cleaned_uid:
        raise ValueError(f'Invalid or missing uid: {uid!r}')
    cleaned_candidate_id = _clean_id(candidate_id)
    if not cleaned_candidate_id:
        raise ValueError(f'Invalid or missing candidate_id: {candidate_id!r}')

    client = _resolve_client(firestore_client)
    if client is None:
        raise RuntimeError('Firestore client unavailable for _integration_outbox_ref')

    return (
        client.collection('users')
        .document(cleaned_uid)
        .collection(CANDIDATE_INTEGRATION_OUTBOX_COLLECTION)
        .document(cleaned_candidate_id)
    )


def _task_control_ref(uid: str, *, firestore_client: Any = None) -> Any:
    cleaned_uid = _clean_id(uid)
    if not cleaned_uid:
        raise ValueError(f'Invalid or missing uid: {uid!r}')

    client = _resolve_client(firestore_client)
    if client is None:
        raise RuntimeError('Firestore client unavailable for _task_control_ref')

    return (
        client.collection('users')
        .document(cleaned_uid)
        .collection(TASK_INTELLIGENCE_CONTROL_COLLECTION)
        .document(TASK_INTELLIGENCE_CONTROL_DOCUMENT)
    )


def _snapshot_dict(snapshot: Any) -> dict[str, Any]:
    if not getattr(snapshot, 'exists', False):
        return {}
    payload = snapshot.to_dict()
    return cast(dict[str, Any], payload) if isinstance(payload, dict) else {}


def claim_candidate_integration_dispatch(
    uid: str,
    candidate_id: str,
    *,
    account_generation: int,
    now: Optional[datetime] = None,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    firestore_client: Any = None,
) -> Optional[str]:
    """Claim a durable accepted-task integration side effect for delivery."""
    cleaned_uid = _clean_id(uid)
    cleaned_candidate_id = _clean_id(candidate_id)
    if not cleaned_uid or not cleaned_candidate_id:
        return None

    client = _resolve_client(firestore_client)
    if client is None:
        logger.warning('Firestore client unavailable for claim_candidate_integration_dispatch')
        return None

    try:
        clamped_lease_seconds = max(MIN_LEASE_SECONDS, min(MAX_LEASE_SECONDS, int(lease_seconds)))
    except (TypeError, ValueError):
        clamped_lease_seconds = DEFAULT_LEASE_SECONDS

    claim_time = _ensure_utc(now) or datetime.now(timezone.utc)
    outbox_ref = _integration_outbox_ref(cleaned_uid, cleaned_candidate_id, firestore_client=client)

    def apply(write_transaction: Any) -> Optional[str]:
        snapshot = outbox_ref.get(transaction=write_transaction)
        if not getattr(snapshot, 'exists', False):
            return None
        payload = _snapshot_dict(snapshot)

        control = TaskWorkflowControl()
        try:
            control_snapshot = _task_control_ref(cleaned_uid, firestore_client=client).get(
                transaction=write_transaction
            )
            if getattr(control_snapshot, 'exists', False):
                control = parse_snapshot_strict(TaskWorkflowControl, control_snapshot)
        except Exception as exc:
            logger.warning('Failed to parse task workflow control for uid %s: %s', cleaned_uid, exc)

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
            claimed_at = _ensure_utc(payload.get('claimed_at'))
            if claimed_at is not None and claimed_at + timedelta(seconds=clamped_lease_seconds) > claim_time:
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

    if hasattr(client, 'transaction'):
        try:
            txn = client.transaction()
            if hasattr(firestore, 'transactional'):
                return firestore.transactional(apply)(txn)
            return apply(txn)
        except TypeError:
            return apply(client)
    return apply(client)


def complete_candidate_integration_dispatch(
    uid: str,
    candidate_id: str,
    *,
    account_generation: int,
    lease_token: str,
    succeeded: bool,
    now: Optional[datetime] = None,
    error_text: Optional[str] = None,
    firestore_client: Any = None,
) -> bool:
    cleaned_uid = _clean_id(uid)
    cleaned_candidate_id = _clean_id(candidate_id)
    if not cleaned_uid or not cleaned_candidate_id or not lease_token or not lease_token.strip():
        return False

    client = _resolve_client(firestore_client)
    if client is None:
        logger.warning('Firestore client unavailable for complete_candidate_integration_dispatch')
        return False

    completion_time = _ensure_utc(now) or datetime.now(timezone.utc)
    outbox_ref = _integration_outbox_ref(cleaned_uid, cleaned_candidate_id, firestore_client=client)

    def apply(write_transaction: Any) -> bool:
        snapshot = outbox_ref.get(transaction=write_transaction)
        if not getattr(snapshot, 'exists', False):
            return False
        payload = _snapshot_dict(snapshot)

        control = TaskWorkflowControl()
        try:
            control_snapshot = _task_control_ref(cleaned_uid, firestore_client=client).get(
                transaction=write_transaction
            )
            if getattr(control_snapshot, 'exists', False):
                control = parse_snapshot_strict(TaskWorkflowControl, control_snapshot)
        except Exception as exc:
            logger.warning('Failed to parse task workflow control for uid %s: %s', cleaned_uid, exc)

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
        if payload.get('status') != 'processing' or payload.get('lease_token') != lease_token.strip():
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

        sanitized_error = (error_text or 'integration_failed')[:MAX_ERROR_TEXT_LENGTH]
        decision = decide_attempt(
            attempt_count=max(int(payload.get('attempt_count') or 0), 1),
            outcome=ProcessOutcome.retry(sanitized_error, reason='integration_failed'),
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

    if hasattr(client, 'transaction'):
        try:
            txn = client.transaction()
            if hasattr(firestore, 'transactional'):
                return firestore.transactional(apply)(txn)
            return apply(txn)
        except TypeError:
            return apply(client)
    return apply(client)


def redrive_candidate_integration_dead_letter(
    uid: str,
    candidate_id: str,
    *,
    account_generation: int,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
) -> bool:
    """Move a dead-lettered integration item back to ready by identity."""
    cleaned_uid = _clean_id(uid)
    cleaned_candidate_id = _clean_id(candidate_id)
    if not cleaned_uid or not cleaned_candidate_id:
        return False

    client = _resolve_client(firestore_client)
    if client is None:
        logger.warning('Firestore client unavailable for redrive_candidate_integration_dead_letter')
        return False

    completion_time = _ensure_utc(now) or datetime.now(timezone.utc)
    outbox_ref = _integration_outbox_ref(cleaned_uid, cleaned_candidate_id, firestore_client=client)

    def apply(write_transaction: Any) -> bool:
        snapshot = outbox_ref.get(transaction=write_transaction)
        if not getattr(snapshot, 'exists', False):
            return False
        payload = _snapshot_dict(snapshot)
        if payload.get('account_generation') != account_generation:
            return False
        if payload.get('status') != 'dead_letter':
            return False
        write_transaction.update(outbox_ref, redrive_patch(now=completion_time))
        return True

    if hasattr(client, 'transaction'):
        try:
            txn = client.transaction()
            if hasattr(firestore, 'transactional'):
                return firestore.transactional(apply)(txn)
            return apply(txn)
        except TypeError:
            return apply(client)
    return apply(client)


def dead_letter_malformed_candidate_integration(
    uid: str,
    candidate_id: str,
    *,
    account_generation: int,
    error_text: str,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
) -> bool:
    """Park a malformed outbox row to dead_letter instead of retrying it forever."""
    cleaned_uid = _clean_id(uid)
    cleaned_candidate_id = _clean_id(candidate_id)
    if not cleaned_uid or not cleaned_candidate_id:
        return False

    client = _resolve_client(firestore_client)
    if client is None:
        logger.warning('Firestore client unavailable for dead_letter_malformed_candidate_integration')
        return False

    completion_time = _ensure_utc(now) or datetime.now(timezone.utc)
    outbox_ref = _integration_outbox_ref(cleaned_uid, cleaned_candidate_id, firestore_client=client)
    sanitized_error = (error_text or 'malformed')[:MAX_ERROR_TEXT_LENGTH]

    def apply(write_transaction: Any) -> bool:
        snapshot = outbox_ref.get(transaction=write_transaction)
        if not getattr(snapshot, 'exists', False):
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
                'last_error_text': sanitized_error,
                'dead_letter_reason': 'malformed',
            },
        )
        return True

    if hasattr(client, 'transaction'):
        try:
            txn = client.transaction()
            if hasattr(firestore, 'transactional'):
                return firestore.transactional(apply)(txn)
            return apply(txn)
        except TypeError:
            return apply(client)
    return apply(client)


def list_candidate_integration_dispatches(
    uid: str,
    *,
    account_generation: int,
    limit: int = DEFAULT_QUERY_LIMIT,
    now: Optional[datetime] = None,
    firestore_client: Any = None,
) -> list[dict[str, Any]]:
    cleaned_uid = _clean_id(uid)
    if not cleaned_uid:
        return []

    client = _resolve_client(firestore_client)
    if client is None:
        logger.warning('Firestore client unavailable for list_candidate_integration_dispatches')
        return []

    try:
        clamped_limit = max(MIN_QUERY_LIMIT, min(MAX_QUERY_LIMIT, int(limit)))
    except (TypeError, ValueError):
        clamped_limit = DEFAULT_QUERY_LIMIT

    query = (
        client.collection('users')
        .document(cleaned_uid)
        .collection(CANDIDATE_INTEGRATION_OUTBOX_COLLECTION)
        .where(filter=FieldFilter('account_generation', '==', account_generation))
        .where(filter=FieldFilter('status', 'in', ['pending', 'failed', 'processing']))
        .limit(clamped_limit)
    )
    rows = [_snapshot_dict(snapshot) for snapshot in query.stream()]
    safe_now = _ensure_utc(now) or datetime.now(timezone.utc)
    ready: list[dict[str, Any]] = []
    for row in rows:
        available_at = row.get('available_at')
        safe_available_at = _ensure_utc(available_at)
        if safe_available_at is not None and safe_available_at > safe_now:
            continue
        ready.append(row)
    return ready


__all__ = [
    'CANDIDATE_INTEGRATION_POLICY',
    'claim_candidate_integration_dispatch',
    'complete_candidate_integration_dispatch',
    'db',
    'dead_letter_malformed_candidate_integration',
    'list_candidate_integration_dispatches',
    'redrive_candidate_integration_dead_letter',
]
