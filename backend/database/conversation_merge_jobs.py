"""Atomic merge admission and renewable leases in the finalization outbox.

Lifecycle owns every caller. Source rows carry an exact job binding; an expired
worker cannot restore a source admitted by a newer job. Recovery before source
retraction cleans the provisional target before releasing the source claims.
"""

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from google.cloud import firestore

from database.quiet_check_retirement import stop_quiet_checks_for_job
from database._client import get_firestore_client
from database.conversation_merge_policy import source_has_merge_receipt

COLLECTION = 'conversation_finalization_jobs'
KIND = 'conversation_merge'
LEASE = timedelta(minutes=10)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def client_for(client: Any) -> Any:
    return client if client is not None else get_firestore_client()


def _source(client: Any, uid: str, cid: str) -> Any:
    return client.collection('users').document(uid).collection('conversations').document(cid)


def admit(uid: str, conversation_ids: list[str], reprocess: bool, *, firestore_client: Any = None) -> dict | None:
    if not 2 <= len(conversation_ids) <= 100 or len(set(conversation_ids)) != len(conversation_ids):
        raise ValueError('merge requires 2 to 100 distinct sources')
    client = client_for(firestore_client)
    job_id = 'merge-' + str(uuid4())
    job_ref = client.collection(COLLECTION).document(job_id)
    refs = [_source(client, uid, cid) for cid in conversation_ids]

    @firestore.transactional
    def commit(transaction: Any) -> dict | None:
        deleting = client.collection('account_deletions').document(uid).get(transaction=transaction)
        rows = [ref.get(transaction=transaction).to_dict() or {} for ref in refs]
        if deleting.exists or any(
            row.get('status') != 'completed'
            or row.get('deleted')
            or row.get('is_locked')
            or row.get('merge_job_id')
            or source_has_merge_receipt(row)
            for row in rows
        ):
            return None
        tombstones = [
            ref.parent.parent.collection('deleted_conversations').document(ref.id).get(transaction=transaction)
            for ref in refs
        ]
        if any(doc.exists for doc in tombstones):
            return None
        now = _now()
        job = dict(
            kind=KIND,
            uid=uid,
            conversation_ids=conversation_ids,
            reprocess=reprocess,
            merge_target_id=str(uuid4()),
            status='queued',
            phase='preparing',
            lease_epoch=0,
            dispatch_generation=1,
            attempt_count=0,
            created_at=now,
            updated_at=now,
            reconcile_after_at=now + LEASE,
        )
        transaction.create(job_ref, job)
        for ref in refs:
            transaction.update(ref, {'status': 'merging', 'merge_job_id': job_id})
        return job | {'job_id': job_id}

    job = commit(client.transaction())
    if job is not None:
        stop_quiet_checks_for_job(job['job_id'], firestore_client=client)
    return job


def claim(job_id: str, *, generation: int | None = None, firestore_client: Any = None) -> dict | None:
    client = client_for(firestore_client)
    ref = client.collection(COLLECTION).document(job_id)

    @firestore.transactional
    def commit(transaction: Any) -> dict | None:
        row = ref.get(transaction=transaction).to_dict() or {}
        if (
            row.get('kind') != KIND
            or row.get('status') != 'queued'
            or (generation is not None and row.get('dispatch_generation') != generation)
        ):
            return None
        now = _now()
        patch = dict(
            status='leased',
            lease_epoch=int(row.get('lease_epoch') or 0) + 1,
            attempt_count=int(row.get('attempt_count') or 0) + 1,
            lease_expires_at=now + LEASE,
            reconcile_after_at=now + LEASE,
            updated_at=now,
        )
        transaction.update(ref, patch)
        return row | patch | {'job_id': job_id}

    return commit(client.transaction())


def owned(job: dict, epoch: int, now: datetime) -> bool:
    return (
        job.get('kind') == KIND
        and job.get('status') == 'leased'
        and job.get('lease_epoch') == epoch
        and job.get('phase') != 'recovering'
        and isinstance(job.get('lease_expires_at'), datetime)
        and job['lease_expires_at'] > now
    )


def renew(job_id: str, epoch: int, *, phase: str | None = None, firestore_client: Any = None) -> bool:
    client = client_for(firestore_client)
    ref = client.collection(COLLECTION).document(job_id)

    @firestore.transactional
    def commit(transaction: Any) -> bool:
        row = ref.get(transaction=transaction).to_dict() or {}
        now = _now()
        if not owned(row, epoch, now):
            return False
        if phase is not None:
            refs = [_source(client, row['uid'], cid) for cid in row['conversation_ids']]
            sources = [source.get(transaction=transaction).to_dict() or {} for source in refs]
            deleting = client.collection('account_deletions').document(row['uid']).get(transaction=transaction)
            tombstones = [
                source.parent.parent.collection('deleted_conversations')
                .document(source.id)
                .get(transaction=transaction)
                for source in refs
            ]
            if (
                deleting.exists
                or any(doc.exists for doc in tombstones)
                or any(
                    data.get('merge_job_id') != job_id
                    or data.get('status') != 'merging'
                    or data.get('deleted')
                    or data.get('is_locked')
                    for data in sources
                )
            ):
                return False
        patch: dict[str, Any] = dict(lease_expires_at=now + LEASE, reconcile_after_at=now + LEASE, updated_at=now)
        if phase is not None:
            if phase not in {'preparing', 'target_started', 'source_retraction'}:
                raise ValueError('unknown merge phase')
            patch['phase'] = phase
        transaction.update(ref, patch)
        return True

    return commit(client.transaction())


def finish(job_id: str, epoch: int, *, firestore_client: Any = None) -> bool:
    client = client_for(firestore_client)
    ref = client.collection(COLLECTION).document(job_id)

    @firestore.transactional
    def commit(transaction: Any) -> bool:
        row = ref.get(transaction=transaction).to_dict() or {}
        if not owned(row, epoch, _now()):
            return False
        transaction.update(ref, dict(status='completed', updated_at=_now(), reconcile_after_at=firestore.DELETE_FIELD))
        return True

    return commit(client.transaction())


def begin_recovery(job_id: str, *, firestore_client: Any = None) -> dict | None:
    client = client_for(firestore_client)
    ref = client.collection(COLLECTION).document(job_id)

    @firestore.transactional
    def commit(transaction: Any) -> dict | None:
        row = ref.get(transaction=transaction).to_dict() or {}
        now = _now()
        if row.get('kind') != KIND or row.get('status') not in {'queued', 'leased'}:
            return None
        due = row.get('reconcile_after_at')
        if not isinstance(due, datetime) or due > now:
            return None
        if row.get('phase') == 'source_cleanup':
            if int(row.get('attempt_count') or 0) >= 5:
                transaction.update(
                    ref,
                    dict(
                        status='dead_letter',
                        failure_code='merge_cleanup_exhausted',
                        updated_at=now,
                        reconcile_after_at=firestore.DELETE_FIELD,
                    ),
                )
                return row | {'recovery': 'manual', 'job_id': job_id}
            patch = dict(
                status='queued',
                lease_epoch=int(row.get('lease_epoch') or 0) + 1,
                dispatch_generation=int(row.get('dispatch_generation') or 1) + 1,
                updated_at=now,
                reconcile_after_at=now + LEASE,
            )
            transaction.update(ref, patch)
            return row | patch | {'recovery': 'resume_cleanup', 'job_id': job_id}
        epoch = int(row.get('lease_epoch') or 0) + 1
        patch = dict(
            status='leased',
            phase='recovering',
            lease_epoch=epoch,
            reconcile_after_at=now + LEASE,
            lease_expires_at=now + LEASE,
            updated_at=now,
        )
        transaction.update(ref, patch)
        return row | patch | {'job_id': job_id, 'recovery': 'rollback'}

    return commit(client.transaction())


def finish_recovery(job_id: str, epoch: int, *, firestore_client: Any = None) -> bool:
    client = client_for(firestore_client)
    ref = client.collection(COLLECTION).document(job_id)

    @firestore.transactional
    def commit(transaction: Any) -> bool:
        row = ref.get(transaction=transaction).to_dict() or {}
        if row.get('kind') != KIND or row.get('phase') != 'recovering' or row.get('lease_epoch') != epoch:
            return False
        refs = [_source(client, row['uid'], cid) for cid in row['conversation_ids']]
        sources = [source.get(transaction=transaction).to_dict() or {} for source in refs]
        for source, data in zip(refs, sources):
            if data.get('status') == 'merging' and data.get('merge_job_id') == job_id:
                transaction.update(source, {'status': 'completed', 'merge_job_id': firestore.DELETE_FIELD})
        transaction.update(
            ref,
            dict(
                status='dead_letter',
                phase='rolled_back',
                failure_code='merge_lease_expired',
                updated_at=_now(),
                reconcile_after_at=firestore.DELETE_FIELD,
            ),
        )
        return True

    finished = commit(client.transaction())
    if finished:
        stop_quiet_checks_for_job(job_id, firestore_client=client)
    return finished
