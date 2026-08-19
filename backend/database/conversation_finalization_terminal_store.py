"""Durable ownership for final-attempt enrichment cleanup."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from google.cloud import firestore

from database import conversation_finalization_effects as effects
from database import conversation_finalization_jobs as jobs
from database._client import get_firestore_client

DEAD_LETTER_CLEANUP_STATUS = jobs.DEAD_LETTER_CLEANUP_STATUS
DEAD_LETTER_CLEANUP_EPOCH_FIELD = jobs.DEAD_LETTER_CLEANUP_EPOCH_FIELD
PROVIDER_REQUEST_TIMEOUT_SECONDS = 30
PROVIDER_DELETE_BATCH_SIZE = 1000
PROVIDER_CLEANUP_HANDOFF_GRACE_SECONDS = 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _job_ref(client: Any, job_id: str) -> Any:
    return client.collection(jobs.FINALIZATION_JOBS_COLLECTION).document(job_id)


def _cleanup_lease_duration(transcript_vector_count: int) -> timedelta:
    provider_calls = 1 + (transcript_vector_count + PROVIDER_DELETE_BATCH_SIZE - 1) // PROVIDER_DELETE_BATCH_SIZE
    provider_bound = timedelta(
        seconds=provider_calls * PROVIDER_REQUEST_TIMEOUT_SECONDS + PROVIDER_CLEANUP_HANDOFF_GRACE_SECONDS
    )
    return max(provider_bound, jobs.get_finalization_reconcile_stale_after())


def _cleanup_result(status: str, job: dict[str, Any] | None = None) -> dict[str, Any]:
    if job is None:
        return {'status': status}
    return {
        'status': status,
        'uid': job.get('uid'),
        'conversation_id': job.get('conversation_id'),
        'finalization_vector_generation_id': effects.finalization_vector_generation_id(job),
        'transcript_vector_count': effects.transcript_vector_count(job),
        'created_at': job.get('created_at'),
    }


def _claim_finalization_dead_letter_cleanup_txn(
    transaction: Any,
    job_ref: Any,
    dispatch_generation: int,
    lease_epoch: int,
    now: datetime,
) -> dict[str, Any]:
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return _cleanup_result('stale')
    job = snapshot.to_dict() or {}
    if (
        job.get('status') == DEAD_LETTER_CLEANUP_STATUS
        and job.get('fanout_status') == DEAD_LETTER_CLEANUP_STATUS
        and int(job.get('dispatch_generation') or 1) == dispatch_generation
        and int(job.get(DEAD_LETTER_CLEANUP_EPOCH_FIELD) or 0) == lease_epoch
    ):
        cleanup_deadline = job.get('lease_expires_at')
        if not isinstance(cleanup_deadline, datetime) or cleanup_deadline <= now:
            return _cleanup_result('stale')
        return _cleanup_result('claimed', job)
    if not jobs.is_current_finalization_lease(job, dispatch_generation, lease_epoch):
        return _cleanup_result('stale')
    if job.get('fanout_status') == 'leased':
        return _cleanup_result('draining')
    if (
        effects.fanout_plan_version(job) != effects.FINALIZATION_FANOUT_PLAN_VERSION
        or effects.completed_effects(job) == effects.REQUIRED_EFFECT_KEYS
    ):
        return _cleanup_result('not_required', job)

    result = _cleanup_result('claimed', job)
    if not all(
        isinstance(result.get(field), str) and bool(result[field])
        for field in ('uid', 'conversation_id', 'finalization_vector_generation_id')
    ):
        return _cleanup_result('invalid')
    if result.get('transcript_vector_count') is None:
        if 'transcript_vectors' in effects.completed_effects(job):
            return _cleanup_result('invalid')
        result['transcript_vector_count'] = 0
    cleanup_deadline = now + _cleanup_lease_duration(int(result['transcript_vector_count']))
    transaction.update(
        job_ref,
        {
            'status': DEAD_LETTER_CLEANUP_STATUS,
            'fanout_status': DEAD_LETTER_CLEANUP_STATUS,
            DEAD_LETTER_CLEANUP_EPOCH_FIELD: lease_epoch,
            'updated_at': now,
            'lease_expires_at': cleanup_deadline,
            'reconcile_after_at': firestore.DELETE_FIELD if bool(job.get('requires_byok')) else cleanup_deadline,
        },
    )
    return result


def claim_finalization_dead_letter_cleanup(
    job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    *,
    firestore_client: Any = None,
) -> dict[str, Any]:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    transactional = firestore.transactional(_claim_finalization_dead_letter_cleanup_txn)
    return transactional(
        client.transaction(),
        _job_ref(client, job_id),
        dispatch_generation,
        lease_epoch,
        _now(),
    )


def _abort_finalization_dead_letter_cleanup_txn(
    transaction: Any,
    job_ref: Any,
    dispatch_generation: int,
    lease_epoch: int,
    now: datetime,
    projection_collection: Any | None = None,
) -> bool:
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    job = snapshot.to_dict() or {}
    if (
        job.get('status') != DEAD_LETTER_CLEANUP_STATUS
        or job.get('fanout_status') != DEAD_LETTER_CLEANUP_STATUS
        or int(job.get('dispatch_generation') or 1) != dispatch_generation
        or int(job.get(DEAD_LETTER_CLEANUP_EPOCH_FIELD) or 0) != lease_epoch
    ):
        return False
    transaction.update(
        job_ref,
        {
            'status': 'queued',
            'fanout_status': 'pending',
            'completed_effects': [],
            'updated_at': now,
            'lease_expires_at': now,
            'reconcile_after_at': (
                firestore.DELETE_FIELD
                if bool(job.get('requires_byok'))
                else now + jobs.get_finalization_reconcile_stale_after()
            ),
            'last_failure_code': 'dead_letter_cleanup_failed',
            DEAD_LETTER_CLEANUP_EPOCH_FIELD: firestore.DELETE_FIELD,
        },
    )
    jobs.record_finalization_projection_delta(transaction, projection_collection, job, leased=-1, queued=1)
    return True


def abort_finalization_dead_letter_cleanup(
    job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    *,
    firestore_client: Any = None,
) -> bool:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    transactional = firestore.transactional(_abort_finalization_dead_letter_cleanup_txn)
    return transactional(
        client.transaction(),
        _job_ref(client, job_id),
        dispatch_generation,
        lease_epoch,
        _now(),
        client.collection(jobs.FINALIZATION_PROJECTION_COLLECTION),
    )
