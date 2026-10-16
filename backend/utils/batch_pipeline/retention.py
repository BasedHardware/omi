"""Batch artifact erasure and completion-only retention; no import-time IO.

Object cleanup is due 24h after successful projection. Metadata receipts expire
45d later, matching the existing content-ledger replay window. Pending outboxes
and dead letters have no TTL: accepted audio must not silently expire.
"""

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import hashlib
import os
from typing import Any
from urllib.parse import urlsplit

from google.api_core.exceptions import NotFound
from google.cloud import firestore

from database import batch_pipeline_privacy_queries as queries
from database.batch_pipeline_privacy import BatchPrivacyBlocked, assert_batch_write_allowed, privacy_owner_key

from utils.batch_pipeline.upload_policy import UPLOAD_PENDING_SECONDS

ARTIFACT_RETENTION = timedelta(hours=24)
RECEIPT_RETENTION = timedelta(days=45)


def delete_batch_object(uid: str, uri: str) -> None:
    """Delete only a configured, owner-scoped object; foreign refs fail closed."""
    parsed = urlsplit(uri)
    bucket_name, path = parsed.netloc, parsed.path.lstrip('/')
    allowed_buckets = {
        value
        for name in ('BUCKET_BATCH_PIPELINE', 'BUCKET_TEMPORAL_SYNC_LOCAL')
        if (value := os.getenv(name, '').strip())
    }
    if (
        parsed.scheme != 'gs'
        or bucket_name not in allowed_buckets
        or parsed.query
        or not path.startswith(
            (
                f'batch-pipeline/batch_pipeline_prod/owners/{privacy_owner_key(uid)}/',
                f'batch-pipeline/batch_pipeline_dev/owners/{privacy_owner_key(uid)}/',
                f'syncing/{uid}/',
            )
        )
        or any(part in {'.', '..'} for part in path.split('/'))
    ):
        raise ValueError('batch object reference outside configured owner storage')
    generation = int(parsed.fragment) if parsed.fragment else None
    from utils.other.local_storage import create_storage_client

    storage_client: Any = create_storage_client()
    blob = storage_client.bucket(bucket_name).blob(path, generation=generation)
    try:
        blob.delete(if_generation_match=generation)
    except NotFound:
        pass


def register_batch_artifact(
    store: Any,
    uid: str,
    segment_id: str,
    uri: str,
    kind: str,
    expected_generation: int,
    *,
    item: Any = None,
) -> str:
    """Register BEFORE object upload; rejected late upload must delete its object.

    Caller repeats the privacy guard after storage IO. The pre-upload reference
    remains retryable during any storage/metadata crash, even if the job is gone.
    """
    if kind not in {'audio', 'result', 'results'}:

        raise ValueError('unknown artifact kind')
    artifact_id = hashlib.sha256(f'{segment_id}\0{uri}'.encode()).hexdigest()
    client, namespace = store.client, store.namespace
    reference = client.collection(f'{namespace}_artifacts').document(artifact_id)

    @firestore.transactional
    def register(transaction):
        job = client.collection(f'{namespace}_jobs').document(segment_id).get(transaction=transaction).to_dict() or {}
        binding = job.get('projection_binding') or {}
        conversation_ids = [
            value
            for value in (
                job.get('conversation_id'),
                binding.get('target_conversation_id'),
                getattr(item, 'conversation_id', None),
            )
            if value
        ]
        assert_batch_write_allowed(
            client, transaction, uid, conversation_ids=conversation_ids, expected_generation=expected_generation
        )
        recovery = job.get('recovery') or {}
        recovery_write = (
            job.get('state') == 'quarantined'
            and job.get('recovery_state') == 'running'
            and recovery.get('privacy_generation') == expected_generation
            and bool(recovery.get('token'))
            and uri.endswith(f"/{recovery['token']}.enc")
        )
        if kind != 'audio' and job.get('state') != 'leased' and not recovery_write:
            raise BatchPrivacyBlocked('result_lease_lost')
        if job and job.get('owner_id') != uid:
            raise ValueError('artifact owner mismatch')
        if not job and (item is None or item.owner_id != uid or kind != 'audio'):
            raise ValueError('result requires an existing owner job')
        existing = reference.get(transaction=transaction)
        if not existing.exists:
            transaction.create(
                reference,
                {
                    'owner_key': privacy_owner_key(uid),
                    'owner_id': uid,
                    'segment_id': segment_id,
                    'conversation_ids': conversation_ids,
                    'uri': uri,
                    'kind': kind,
                    'privacy_generation': expected_generation,
                    'write_pending_until': datetime.now(timezone.utc) + timedelta(seconds=UPLOAD_PENDING_SECONDS),
                },
            )

    register(client.transaction())
    return artifact_id


def expire_completed_segment(store: Any, uid: str, segment_id: str, now: float) -> bool:
    """Arm cleanup only after C has durably checkpointed successful projection."""
    client, namespace = store.client, store.namespace
    completed_at = datetime.fromtimestamp(now, timezone.utc)

    @firestore.transactional
    def expire(transaction):
        job_ref = client.collection(f'{namespace}_jobs').document(segment_id)
        result_ref = client.collection(f'{namespace}_results').document(segment_id)
        job = job_ref.get(transaction=transaction).to_dict() or {}
        result = result_ref.get(transaction=transaction).to_dict() or {}
        artifacts = queries.segment_artifacts(client, namespace, segment_id, transaction)
        intake_id = (job.get('projection_binding') or {}).get('job_id')
        intake_ref = client.collection(f'{namespace}_intakes').document(intake_id) if intake_id else None
        intake = intake_ref.get(transaction=transaction) if intake_ref is not None else None
        if not result or result.get('projection_state') not in {'ready', 'projected', 'completed'}:
            return False
        if job.get('owner_id') != uid or result.get('owner_key') != privacy_owner_key(uid):
            raise ValueError('completion owner mismatch')
        if result.get('expires_at'):
            return True
        expires = completed_at + RECEIPT_RETENTION
        transaction.update(job_ref, {'expires_at': expires})
        transaction.update(result_ref, {'expires_at': expires})
        if intake_ref is not None and intake is not None and intake.exists:
            transaction.update(intake_ref, {'expires_at': expires})
        for artifact in artifacts:
            transaction.update(artifact.reference, {'cleanup_after': completed_at + ARTIFACT_RETENTION})
        return True

    return expire(client.transaction())


def cleanup_completed_artifacts(
    store: Any,
    now: datetime,
    *,
    delete_uri: Callable[[str, str], None] = delete_batch_object,
    limit: int = 100,
) -> int:
    """Erase objects first; only then permit TTL to remove their last reference."""
    cleaned = 0
    for artifact in queries.due_artifacts(store.client, store.namespace, now, limit):
        data = artifact.to_dict() or {}
        delete_uri(data['owner_id'], data['uri'])
        # Deletion races must never recreate a purged metadata document.
        try:
            if data.get('erasure_requested'):
                artifact.reference.delete()
                cleaned += 1
                continue
            artifact.reference.update(
                {
                    'uri': firestore.DELETE_FIELD,
                    'cleanup_after': firestore.DELETE_FIELD,
                    'expires_at': now + RECEIPT_RETENTION,
                }
            )
        except NotFound:
            pass
        cleaned += 1
    return cleaned


def batch_artifact_authorize(store: Any, item: Any):
    """B's required authorize(item) callback, using uncached transactional reads."""
    from utils.batch_pipeline.artifacts import ProtectionContext

    @firestore.transactional
    def authorize(transaction):
        generation = assert_batch_write_allowed(
            store.client,
            transaction,
            item.owner_id,
            conversation_ids=(item.conversation_id,) if item.conversation_id else (),
            expected_generation=item.privacy_generation,
        )
        user = store.client.collection('users').document(item.owner_id).get(transaction=transaction).to_dict() or {}
        return ProtectionContext(user.get('data_protection_level', 'enhanced'), generation)

    return authorize(store.client.transaction())


def batch_artifact_register(store: Any, item: Any, uri: str, kind: str, context: Any) -> None:
    """B's register_artifact(item, uri, kind, context) callback (before upload)."""
    register_batch_artifact(store, item.owner_id, item.segment_id, uri, kind, context.generation, item=item)


def purge_batch_storage_owner(uid: str, namespace: str) -> None:
    """Sweep all versions of the deterministic owner prefix, including orphans."""
    bucket_name = os.getenv('BUCKET_BATCH_PIPELINE', '').strip()
    if not bucket_name:
        return  # No artifact store can be constructed without an explicit bucket.
    from utils.other.local_storage import create_storage_client

    client: Any = create_storage_client()
    bucket = client.bucket(bucket_name)
    prefix = f'batch-pipeline/{namespace}/owners/{privacy_owner_key(uid)}/'
    for blob in bucket.list_blobs(prefix=prefix, versions=True):
        try:
            blob.delete(if_generation_match=int(blob.generation))
        except NotFound:
            pass
    if list(bucket.list_blobs(prefix=prefix, versions=True, max_results=1)):
        raise RuntimeError('batch owner storage purge did not converge')
