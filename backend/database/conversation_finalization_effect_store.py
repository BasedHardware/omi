"""Firestore wrappers for fenced conversation finalization effects."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from google.cloud import firestore

from database import conversation_finalization_effects as effects
from database import conversation_finalization_jobs as jobs
from database._client import get_firestore_client

FinalizationEffectBoundaryStatus = effects.FinalizationEffectBoundaryStatus


def _client(firestore_client: Any = None) -> Any:
    return firestore_client if firestore_client is not None else get_firestore_client()


def _job_ref(client: Any, job_id: str) -> Any:
    return client.collection(jobs.FINALIZATION_JOBS_COLLECTION).document(job_id)


def _conversation_ref(client: Any, uid: str, conversation_id: str) -> Any:
    return client.collection('users').document(uid).collection(jobs.CONVERSATIONS_COLLECTION).document(conversation_id)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _prepare_finalization_effect_txn(
    transaction: Any,
    job_ref: Any,
    dispatch_generation: int,
    lease_epoch: int,
    effect: str,
    resource_count: int,
    now: datetime,
    conversation_ref_for_job: Callable[[str, str], Any],
) -> FinalizationEffectBoundaryStatus:
    return effects.prepare_effect_txn(
        transaction,
        job_ref,
        dispatch_generation,
        lease_epoch,
        effect,
        resource_count,
        now,
        is_current_lease=jobs.is_current_finalization_lease,
        conversation_ref_for_job=conversation_ref_for_job,
        conversation_admits_fanout=effects.conversation_admits_fanout,
    )


def prepare_finalization_effect(
    job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    effect: str,
    resource_count: int,
    *,
    firestore_client: Any = None,
) -> FinalizationEffectBoundaryStatus:
    client = _client(firestore_client)
    transactional = firestore.transactional(_prepare_finalization_effect_txn)
    return transactional(
        client.transaction(),
        _job_ref(client, job_id),
        dispatch_generation,
        lease_epoch,
        effect,
        resource_count,
        _now(),
        lambda uid, conversation_id: _conversation_ref(client, uid, conversation_id),
    )


def _mark_finalization_effect_completed_txn(
    transaction: Any,
    job_ref: Any,
    dispatch_generation: int,
    lease_epoch: int,
    effect: str,
    now: datetime,
    conversation_ref_for_job: Callable[[str, str], Any],
    persist_effect: bool = True,
) -> FinalizationEffectBoundaryStatus:
    return effects.complete_effect_txn(
        transaction,
        job_ref,
        dispatch_generation,
        lease_epoch,
        effect,
        now,
        is_current_lease=jobs.is_current_finalization_lease,
        conversation_ref_for_job=conversation_ref_for_job,
        conversation_admits_fanout=effects.conversation_admits_fanout,
        persist_effect=persist_effect,
    )


def mark_finalization_effect_completed(
    job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    effect: str,
    *,
    persist_effect: bool = True,
    firestore_client: Any = None,
) -> FinalizationEffectBoundaryStatus:
    client = _client(firestore_client)
    transactional = firestore.transactional(_mark_finalization_effect_completed_txn)
    return transactional(
        client.transaction(),
        _job_ref(client, job_id),
        dispatch_generation,
        lease_epoch,
        effect,
        _now(),
        lambda uid, conversation_id: _conversation_ref(client, uid, conversation_id),
        persist_effect,
    )


def mark_finalization_enrichment_cleaned(
    job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    *,
    firestore_client: Any = None,
) -> bool:
    client = _client(firestore_client)
    projection_collection = client.collection(jobs.FINALIZATION_PROJECTION_COLLECTION)
    transactional = firestore.transactional(effects.cleanup_fence_txn)
    return transactional(
        client.transaction(),
        _job_ref(client, job_id),
        dispatch_generation,
        lease_epoch,
        _now(),
        is_current_lease=jobs.is_current_finalization_lease,
        conversation_ref_for_job=lambda uid, conversation_id: _conversation_ref(client, uid, conversation_id),
        conversation_admits_fanout=effects.conversation_admits_fanout,
        fenced_update=jobs.fenced_finalization_update,
        record_projection=lambda txn, job: jobs.record_finalization_projection_delta(
            txn,
            projection_collection,
            job,
            leased=-1,
            completed=1,
            stale=1,
        ),
    )


def _release_finalization_fanout_txn(
    transaction: Any,
    job_ref: Any,
    dispatch_generation: int,
    lease_epoch: int,
    now: datetime,
) -> bool:
    """Close one fanout epoch only after its worker has stopped mutating."""
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    job = snapshot.to_dict() or {}
    if (
        int(job.get('dispatch_generation') or 1) != dispatch_generation
        or job.get('fanout_status') != 'leased'
        or int(job.get('fanout_lease_epoch') or 0) != lease_epoch
    ):
        return False
    transaction.update(
        job_ref,
        {
            'fanout_status': 'drained',
            'fanout_drained_at': now,
            'updated_at': now,
        },
    )
    return True


def release_finalization_fanout(
    job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    *,
    firestore_client: Any = None,
) -> bool:
    """Record that a claimed worker has returned from every fanout mutation."""
    client = _client(firestore_client)
    transactional = firestore.transactional(_release_finalization_fanout_txn)
    return transactional(
        client.transaction(),
        _job_ref(client, job_id),
        dispatch_generation,
        lease_epoch,
        _now(),
    )


def _force_drain_finalization_worker_txn(
    transaction: Any,
    job_ref: Any,
    fanout_lease_epoch: int,
    terminated_before: datetime,
    now: datetime,
) -> bool:
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    job = snapshot.to_dict() or {}
    lease_expires_at = job.get('lease_expires_at')
    if (
        terminated_before.tzinfo is None
        or terminated_before > now
        or not isinstance(lease_expires_at, datetime)
        or lease_expires_at.tzinfo is None
        or lease_expires_at > terminated_before
        or job.get('status') != 'leased'
        or int(job.get('lease_epoch') or 0) != fanout_lease_epoch
        or job.get('fanout_status') != 'leased'
        or int(job.get('fanout_lease_epoch') or 0) != fanout_lease_epoch
    ):
        return False
    transaction.update(
        job_ref,
        {
            'fanout_status': 'drained',
            'fanout_drained_at': now,
            'fanout_operator_recovered_at': now,
            'fanout_operator_terminated_before': terminated_before,
            'updated_at': now,
        },
    )
    return True


def force_drain_finalization_worker_after_confirmed_termination(
    job_id: str,
    fanout_lease_epoch: int,
    *,
    terminated_before: datetime,
    firestore_client: Any = None,
) -> bool:
    """Recover a hard-killed worker only after an operator confirms termination."""
    client = _client(firestore_client)
    transactional = firestore.transactional(_force_drain_finalization_worker_txn)
    return transactional(
        client.transaction(),
        _job_ref(client, job_id),
        fanout_lease_epoch,
        terminated_before,
        _now(),
    )
