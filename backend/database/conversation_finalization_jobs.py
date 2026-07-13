"""Firestore outbox and lease state for durable listen finalization.

Cloud Tasks is deliberately only a wake-up mechanism.  The durable source of
truth is one Firestore job per ``(uid, conversation_id, finalization_revision)``.
No transcript, credential, request header, or raw exception is stored here.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal, TypedDict

from google.cloud import firestore

from database._client import document_id_from_seed, get_firestore_client

CONVERSATIONS_COLLECTION = 'conversations'
FINALIZATION_JOBS_COLLECTION = 'conversation_finalization_jobs'

FinalizationJobStatus = Literal['queued', 'leased', 'completed', 'dead_letter', 'blocked_byok']
TERMINAL_JOB_STATUSES = frozenset({'completed', 'dead_letter'})
NONTERMINAL_JOB_STATUSES = frozenset({'queued', 'leased', 'blocked_byok'})
DEFAULT_LEASE_SECONDS = 1500


class FinalizationIntent(TypedDict):
    job_id: str | None
    status: str
    dispatch_generation: int | None
    requires_byok: bool


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _client(firestore_client: Any = None) -> Any:
    return firestore_client if firestore_client is not None else get_firestore_client()


def _conversation_ref(client: Any, uid: str, conversation_id: str) -> Any:
    return client.collection('users').document(uid).collection(CONVERSATIONS_COLLECTION).document(conversation_id)


def _job_ref(client: Any, job_id: str) -> Any:
    return client.collection(FINALIZATION_JOBS_COLLECTION).document(job_id)


def _job_id(uid: str, conversation_id: str, revision: int) -> str:
    return document_id_from_seed(f'listen-finalization:{uid}:{conversation_id}:{revision}')


def _intent_from_job(job_id: str, data: dict[str, Any]) -> FinalizationIntent:
    return {
        'job_id': job_id,
        'status': str(data.get('status') or 'queued'),
        'dispatch_generation': int(data.get('dispatch_generation') or 1),
        'requires_byok': bool(data.get('requires_byok')),
    }


def _create_or_get_finalization_intent_txn(
    transaction: Any,
    conversation_ref: Any,
    jobs_collection: Any,
    uid: str,
    conversation_id: str,
    requires_byok: bool,
    now: datetime,
) -> FinalizationIntent:
    """Persist finalization ownership before any pusher or task handoff."""
    conversation_snapshot = conversation_ref.get(transaction=transaction)
    if not getattr(conversation_snapshot, 'exists', False):
        return {'job_id': None, 'status': 'missing', 'dispatch_generation': None, 'requires_byok': False}

    conversation = conversation_snapshot.to_dict() or {}
    if conversation.get('deferred'):
        return {'job_id': None, 'status': 'deferred', 'dispatch_generation': None, 'requires_byok': False}
    if not (conversation.get('transcript_segments') or conversation.get('photos')):
        return {'job_id': None, 'status': 'no_content', 'dispatch_generation': None, 'requires_byok': False}
    if conversation.get('status') == 'completed':
        return {'job_id': None, 'status': 'completed', 'dispatch_generation': None, 'requires_byok': False}

    existing_job_id = conversation.get('finalization_job_id')
    if isinstance(existing_job_id, str) and existing_job_id:
        existing_ref = jobs_collection.document(existing_job_id)
        existing_snapshot = existing_ref.get(transaction=transaction)
        if getattr(existing_snapshot, 'exists', False):
            return _intent_from_job(existing_job_id, existing_snapshot.to_dict() or {})

    revision = int(conversation.get('finalization_revision') or 0) + 1
    job_id = _job_id(uid, conversation_id, revision)
    job_ref = jobs_collection.document(job_id)
    job_snapshot = job_ref.get(transaction=transaction)
    if getattr(job_snapshot, 'exists', False):
        job = job_snapshot.to_dict() or {}
        transaction.update(
            conversation_ref,
            {
                'status': 'processing',
                'finalization_job_id': job_id,
                'finalization_revision': revision,
                'finalization_status': job.get('status', 'queued'),
            },
        )
        return _intent_from_job(job_id, job)

    status: FinalizationJobStatus = 'blocked_byok' if requires_byok else 'queued'
    job = {
        'schema_version': 1,
        'uid': uid,
        'conversation_id': conversation_id,
        'finalization_revision': revision,
        'status': status,
        'requires_byok': requires_byok,
        'dispatch_generation': 1,
        'attempt_count': 0,
        'task_retry_count': 0,
        'created_at': now,
        'updated_at': now,
        'dispatch_requested_at': now,
    }
    transaction.set(job_ref, job)
    transaction.update(
        conversation_ref,
        {
            'status': 'processing',
            'finalization_job_id': job_id,
            'finalization_revision': revision,
            'finalization_status': status,
        },
    )
    return _intent_from_job(job_id, job)


def create_or_get_finalization_intent(
    uid: str,
    conversation_id: str,
    *,
    requires_byok: bool,
    firestore_client: Any = None,
) -> FinalizationIntent:
    client = _client(firestore_client)
    conversation_ref = _conversation_ref(client, uid, conversation_id)
    transaction = client.transaction()
    transactional = firestore.transactional(_create_or_get_finalization_intent_txn)
    return transactional(
        transaction,
        conversation_ref,
        client.collection(FINALIZATION_JOBS_COLLECTION),
        uid,
        conversation_id,
        requires_byok,
        _now(),
    )


def _resume_blocked_byok_job_txn(transaction: Any, job_ref: Any, now: datetime) -> FinalizationIntent:
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return {'job_id': None, 'status': 'missing', 'dispatch_generation': None, 'requires_byok': False}
    job = snapshot.to_dict() or {}
    if job.get('status') == 'blocked_byok' and job.get('requires_byok'):
        transaction.update(job_ref, {'status': 'queued', 'updated_at': now, 'last_byok_resume_at': now})
        job['status'] = 'queued'
    return _intent_from_job(snapshot.id, job)


def resume_blocked_byok_job_for_live_session(job_id: str, *, firestore_client: Any = None) -> FinalizationIntent:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_resume_blocked_byok_job_txn)
    return transactional(transaction, _job_ref(client, job_id), _now())


def _claim_finalization_job_txn(
    transaction: Any,
    job_ref: Any,
    dispatch_generation: int,
    allow_byok: bool,
    lease_seconds: int,
    now: datetime,
    expected_uid: str | None = None,
    expected_conversation_id: str | None = None,
) -> str:
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return 'missing'
    job = snapshot.to_dict() or {}
    status = str(job.get('status') or '')
    if expected_uid is not None and job.get('uid') != expected_uid:
        return 'identity_mismatch'
    if expected_conversation_id is not None and job.get('conversation_id') != expected_conversation_id:
        return 'identity_mismatch'
    if status in TERMINAL_JOB_STATUSES:
        return status
    if bool(job.get('requires_byok')) and not allow_byok:
        return 'blocked_byok'
    if status == 'blocked_byok':
        return 'blocked_byok'
    if int(job.get('dispatch_generation') or 1) != dispatch_generation:
        return 'stale_generation'
    if status == 'leased':
        lease_expires_at = job.get('lease_expires_at')
        if isinstance(lease_expires_at, datetime) and lease_expires_at > now:
            return 'leased'
    if status not in ('queued', 'leased'):
        return 'not_actionable'

    transaction.update(
        job_ref,
        {
            'status': 'leased',
            'leased_at': now,
            'lease_expires_at': now + timedelta(seconds=lease_seconds),
            'updated_at': now,
            'attempt_count': int(job.get('attempt_count') or 0) + 1,
        },
    )
    return 'claimed'


def claim_finalization_job(
    job_id: str,
    dispatch_generation: int,
    *,
    allow_byok: bool = False,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    expected_uid: str | None = None,
    expected_conversation_id: str | None = None,
    firestore_client: Any = None,
) -> str:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_claim_finalization_job_txn)
    return transactional(
        transaction,
        _job_ref(client, job_id),
        dispatch_generation,
        allow_byok,
        lease_seconds,
        _now(),
        expected_uid,
        expected_conversation_id,
    )


def _mark_finalization_completed_txn(transaction: Any, job_ref: Any, dispatch_generation: int, now: datetime) -> bool:
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    job = snapshot.to_dict() or {}
    if job.get('status') == 'completed':
        return True
    if job.get('status') != 'leased' or int(job.get('dispatch_generation') or 1) != dispatch_generation:
        return False
    transaction.update(
        job_ref,
        {
            'status': 'completed',
            'completed_at': now,
            'updated_at': now,
            'lease_expires_at': now,
            'last_failure_code': None,
        },
    )
    return True


def mark_finalization_completed(job_id: str, dispatch_generation: int, *, firestore_client: Any = None) -> bool:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_mark_finalization_completed_txn)
    return transactional(transaction, _job_ref(client, job_id), dispatch_generation, _now())


def _mark_finalization_retryable_txn(
    transaction: Any, job_ref: Any, dispatch_generation: int, failure_code: str, now: datetime
) -> bool:
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    job = snapshot.to_dict() or {}
    if job.get('status') != 'leased' or int(job.get('dispatch_generation') or 1) != dispatch_generation:
        return False
    transaction.update(
        job_ref,
        {
            'status': 'queued',
            'updated_at': now,
            'lease_expires_at': now,
            'last_failure_code': failure_code,
        },
    )
    return True


def mark_finalization_retryable(
    job_id: str, dispatch_generation: int, failure_code: str = 'processing_failed', *, firestore_client: Any = None
) -> bool:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_mark_finalization_retryable_txn)
    return transactional(transaction, _job_ref(client, job_id), dispatch_generation, failure_code, _now())


def _mark_finalization_dead_letter_txn(
    transaction: Any, job_ref: Any, dispatch_generation: int, retry_count: int, now: datetime
) -> bool:
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    job = snapshot.to_dict() or {}
    if job.get('status') != 'leased' or int(job.get('dispatch_generation') or 1) != dispatch_generation:
        return False
    transaction.update(
        job_ref,
        {
            'status': 'dead_letter',
            'updated_at': now,
            'terminal_at': now,
            'lease_expires_at': now,
            'task_retry_count': retry_count,
            'last_failure_code': 'final_attempt_failed',
        },
    )
    return True


def mark_finalization_dead_letter(
    job_id: str, dispatch_generation: int, retry_count: int, *, firestore_client: Any = None
) -> bool:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_mark_finalization_dead_letter_txn)
    return transactional(transaction, _job_ref(client, job_id), dispatch_generation, retry_count, _now())


def get_finalization_job(job_id: str, *, firestore_client: Any = None) -> dict[str, Any] | None:
    snapshot = _job_ref(_client(firestore_client), job_id).get()
    if not getattr(snapshot, 'exists', False):
        return None
    return snapshot.to_dict() or {}


def _claim_finalization_replay_txn(
    transaction: Any, job_ref: Any, stale_after: timedelta, now: datetime
) -> FinalizationIntent:
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return {'job_id': None, 'status': 'missing', 'dispatch_generation': None, 'requires_byok': False}
    job = snapshot.to_dict() or {}
    status = str(job.get('status') or '')
    if status == 'blocked_byok' or status in TERMINAL_JOB_STATUSES:
        return _intent_from_job(snapshot.id, job)
    if status == 'leased':
        lease_expires_at = job.get('lease_expires_at')
        if isinstance(lease_expires_at, datetime) and lease_expires_at > now:
            return _intent_from_job(snapshot.id, job)
    if status == 'queued':
        dispatch_requested_at = job.get('dispatch_requested_at')
        if isinstance(dispatch_requested_at, datetime) and dispatch_requested_at > now - stale_after:
            return _intent_from_job(snapshot.id, job)
    if status not in ('queued', 'leased'):
        return _intent_from_job(snapshot.id, job)

    generation = int(job.get('dispatch_generation') or 1) + 1
    transaction.update(
        job_ref,
        {
            'status': 'queued',
            'dispatch_generation': generation,
            'dispatch_requested_at': now,
            'updated_at': now,
            'lease_expires_at': now,
        },
    )
    job['status'] = 'queued'
    job['dispatch_generation'] = generation
    return _intent_from_job(snapshot.id, job)


def claim_finalization_replay(
    job_id: str, *, stale_after: timedelta, firestore_client: Any = None
) -> FinalizationIntent:
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_claim_finalization_replay_txn)
    return transactional(transaction, _job_ref(client, job_id), stale_after, _now())


def get_finalization_replay_candidates(
    *, limit: int = 100, stale_after: timedelta, firestore_client: Any = None
) -> list[dict[str, Any]]:
    """Return old queued jobs and expired leases without requiring composite indexes."""
    client = _client(firestore_client)
    cutoff = _now() - stale_after
    result: list[dict[str, Any]] = []
    collection = client.collection(FINALIZATION_JOBS_COLLECTION)
    for status in ('queued', 'leased'):
        for snapshot in collection.where('status', '==', status).stream():
            job = snapshot.to_dict() or {}
            timestamp = job.get('dispatch_requested_at') if status == 'queued' else job.get('lease_expires_at')
            if isinstance(timestamp, datetime) and timestamp > cutoff:
                continue
            result.append(job | {'job_id': snapshot.id})
            if len(result) >= limit:
                return result
    return result


def get_finalization_job_summary(*, firestore_client: Any = None) -> dict[str, float | int]:
    """Small, privacy-safe operational summary for the reconciler and metrics."""
    client = _client(firestore_client)
    now = _now()
    counts: dict[str, int] = {status: 0 for status in (*NONTERMINAL_JOB_STATUSES, *TERMINAL_JOB_STATUSES)}
    oldest_age_seconds = 0.0
    collection = client.collection(FINALIZATION_JOBS_COLLECTION)
    for status in counts:
        for snapshot in collection.where('status', '==', status).stream():
            counts[status] += 1
            if status in NONTERMINAL_JOB_STATUSES:
                created_at = (snapshot.to_dict() or {}).get('created_at')
                if isinstance(created_at, datetime):
                    oldest_age_seconds = max(oldest_age_seconds, max(0.0, (now - created_at).total_seconds()))
    return {
        'queued': counts['queued'],
        'leased': counts['leased'],
        'blocked_byok': counts['blocked_byok'],
        'completed': counts['completed'],
        'dead_letter': counts['dead_letter'],
        'oldest_nonterminal_age_seconds': oldest_age_seconds,
    }
