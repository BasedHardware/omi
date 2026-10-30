"""Direct unit receipt reads; references never substitute for privacy/binding checks."""

from datetime import datetime, timezone
import hashlib
import time

from google.cloud import firestore

from database.batch_pipeline_privacy import assert_batch_write_allowed
from database.batch_pipeline_shadow_hook import mirror_refresh
from utils.batch_pipeline.contracts import WorkItem
from utils.batch_pipeline.voice_centroids import deadline


def _ref(store, table, key):
    return store.client.collection(f'{store.namespace}_{table}').document(key)


def _bound(job, result, uid, conversation_id):
    binding = job.get('projection_binding') or {}
    receipts = list((result.get('projection_parts') or {}).values()) or [result.get('projection') or {}]
    return (
        job.get('owner_id') == uid
        and binding.get('owner_id') == uid
        and binding.get('private_cloud_sync_enabled') is False
        and any(
            r.get('conversation_id') == conversation_id
            and r.get('speaker_scope') == f"final:batch:{job.get('segment_id')}"
            for r in receipts
        )
    )


def load_reference(store, uid, segment_id, conversation_id):
    """The returned item is reconstructed from trusted admission, never client input."""

    @firestore.transactional
    def read(transaction):
        job = _ref(store, 'jobs', segment_id).get(transaction=transaction).to_dict() or {}
        result = _ref(store, 'results', segment_id).get(transaction=transaction).to_dict() or {}
        if not _bound(job, result, uid, conversation_id):
            return None
        item = WorkItem(**{k: job[k] for k in WorkItem.__dataclass_fields__ if k in job})
        assert_batch_write_allowed(
            store.client,
            transaction,
            uid,
            conversation_ids=(conversation_id,),
            expected_generation=item.privacy_generation,
        )
        reference = job.get('voice_evidence')
        if not reference:
            return None
        metadata = _ref(store, 'artifacts', reference).get(transaction=transaction).to_dict() or {}
        if (
            metadata.get('kind') != 'voice_evidence'
            or metadata.get('owner_id') != uid
            or metadata.get('segment_id') != segment_id
            or metadata.get('erasure_requested')
            or conversation_id not in metadata.get('conversation_ids', [])
            or metadata.get('privacy_generation') != item.privacy_generation
            or not metadata.get('uri')
            or '#' not in metadata['uri']
        ):
            return None
        due = min(deadline(item.capture_at), metadata['cleanup_after'].timestamp())
        if time.time() >= due:
            return None
        return item, metadata['uri'], due

    return read(store.client.transaction())


def publish(store, item, uri, conversation_id):
    """Pin the registered immutable object and bind it to the persisted projection.

    Completion shortens cleanup_after separately; publishing never refreshes it.
    """
    artifact_id = hashlib.sha256(f"{item.segment_id}\0{uri.split('#')[0]}".encode()).hexdigest()
    artifact_ref = _ref(store, 'artifacts', artifact_id)
    job_ref = _ref(store, 'jobs', item.segment_id)

    @firestore.transactional
    def write(transaction):
        job = job_ref.get(transaction=transaction).to_dict() or {}
        result = _ref(store, 'results', item.segment_id).get(transaction=transaction).to_dict() or {}
        metadata = artifact_ref.get(transaction=transaction).to_dict() or {}
        assert_batch_write_allowed(
            store.client,
            transaction,
            item.owner_id,
            conversation_ids=(conversation_id,),
            expected_generation=item.privacy_generation,
        )
        if not _bound(job, result, item.owner_id, conversation_id):
            raise PermissionError('voice projection binding changed')
        if metadata.get('erasure_requested') or metadata.get('uri') not in {uri, uri.split('#')[0]}:
            raise PermissionError('voice artifact registration changed')
        if time.time() >= deadline(item.capture_at):
            raise PermissionError('voice evidence expired')
        due = min(metadata['cleanup_after'].timestamp(), deadline(item.capture_at))
        transaction.update(
            artifact_ref,
            {
                'uri': uri,
                'cleanup_after': datetime.fromtimestamp(due, timezone.utc),
                'conversation_ids': list(set(metadata['conversation_ids'] + [conversation_id])),
            },
        )
        transaction.update(job_ref, {'voice_evidence': artifact_id})

    write(store.client.transaction())
    mirror_refresh(store.namespace, [('jobs', item.segment_id), ('artifacts', artifact_id)])


def prepared_reference(store, item):
    job = _ref(store, 'jobs', item.segment_id).get().to_dict() or {}
    if job.get('owner_id') != item.owner_id or not job.get('voice_evidence'):
        return None
    data = _ref(store, 'artifacts', job['voice_evidence']).get().to_dict() or {}
    if (
        data.get('kind') == 'voice_evidence'
        and data.get('owner_id') == item.owner_id
        and data.get('privacy_generation') == item.privacy_generation
        and not data.get('erasure_requested')
        and data.get('uri')
        and time.time() < data['cleanup_after'].timestamp()
    ):
        return data['uri']
    return None
