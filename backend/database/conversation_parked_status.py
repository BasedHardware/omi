"""SCA-3590 status-only migration for conversation rows with a durable parked disposition."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from google.protobuf.timestamp_pb2 import Timestamp

from config.record_audio import record_identity
from database.batch_account_authority_schema import ACCOUNT_DELETION_COLLECTION
from database.conversation_finalization_schema import FINALIZATION_JOBS_COLLECTION
from database.conversation_tombstones import COLLECTION as TOMBSTONES
from models.finalization_owner import python_owns_finalization
from utils.conversations.terminal_relevance import valid_decision
from utils.enrichment import outbox

OWNERSHIP_FIELDS = (
    'record_lane_owner',
    'recording',
    'record_upload_revision',
    'sync_content_revision',
    'sync_live_target',
    'sync_merged_into',
    'sync_merged_from',
    'v3_derived',
    'v3_process_pending',
    'processing_deferred',
    'is_locked',
)

ROW_FIELDS = (
    'status',
    'finished_at',
    'source',
    'deleted',
    'discarded',
    'deferred',
    'relevance_decision.verdict',
    'relevance_decision.decided_by',
    'relevance_decision.reason',
    'relevance_decision.trigger',
    'sync_relevance_user_kept',
    'finalization_id',
    'finalization_engine',
    'finalization_owner_epoch',
    'finalization_job_id',
    'finalization_revision',
    'finalization_status',
    'processing_state',
    'processing_admitted_at',
    'client_processing.schema_version',
    *OWNERSHIP_FIELDS,
)


def classify(row: Mapping[str, Any], *, cutoff: datetime, discard_deletion_only: bool = False) -> str:
    if row.get('status') != 'processing':
        return 'changed'
    deferred = row.get('deferred')
    if discard_deletion_only and 'deferred' in row and deferred is not False:
        return 'deferred_excluded'
    if not python_owns_finalization(row) or any(row.get(field) for field in OWNERSHIP_FIELDS):
        return 'other_owner'
    admitted_at = row.get('processing_admitted_at')
    if not isinstance(admitted_at, datetime) or admitted_at.tzinfo is None or admitted_at >= cutoff:
        return 'recent_or_unknown_admission'
    if (
        row.get('processing_state') == 'local_pending'
        or row.get('sync_relevance_user_kept')
        or row.get('client_processing')
    ):
        return 'other_owner'
    if row.get('deleted') is True:
        return 'deleted'
    if row.get('discarded') is True:
        decision = row.get('relevance_decision')
        if isinstance(decision, Mapping) and valid_decision(decision) and decision.get('verdict') == 'discard':
            return 'discarded'
        return 'discard_unproven'
    if deferred is True and row.get('source') == 'desktop':
        return 'deferred'
    return 'unclassified'


CANDIDATES = frozenset({'deleted', 'discarded', 'deferred'})


def _settled_job(uid: str, cid: str, row: Mapping[str, Any], job: Mapping[str, Any]) -> bool:
    if row.get('finalization_job_id') is None:
        return not any(row.get(key) for key in ('finalization_revision', 'finalization_status', 'finalization_id'))
    return (
        python_owns_finalization(job)
        and job.get('finalization_owner_epoch') == row.get('finalization_owner_epoch')
        and job.get('uid') == uid
        and job.get('conversation_id') == cid
        and type(job.get('finalization_revision')) is int
        and job['finalization_revision'] == row.get('finalization_revision')
        and job.get('status') == 'completed'
        and job.get('fanout_status') in {None, 'completed', 'fenced'}
    )


def _read(client: Any, transaction: Any, refs, fields) -> dict[str, Any]:
    if not refs:
        return {}
    results = {
        snapshot.reference.path: snapshot
        for snapshot in client.get_all(refs, field_paths=fields, transaction=transaction, retry=None, timeout=30)
    }
    if results.keys() != {ref.path for ref in refs}:
        raise RuntimeError('incomplete custody read')
    return results


def _revision(value: object) -> Timestamp | None:
    # Collection-group queries return protobuf timestamps, while batch gets
    # return DatetimeWithNanoseconds. Compare the exact seconds/nanos wire pair.
    encode = getattr(value, 'timestamp_pb', None)
    wire = encode() if callable(encode) else value
    return wire if isinstance(wire, Timestamp) else None


def settle_in_transaction(
    transaction: Any,
    client: Any,
    snapshots: list,
    *,
    cutoff: datetime,
    apply: bool,
    discard_deletion_only: bool = False,
) -> list[str]:
    """Revalidate the original row and its keyed custody in one transaction.

    Native batch admission stamps record_lane_owner on the conversation before
    registering work. Sync assignment writes a sync revision on the same row.
    The separate enrichment claims are keyed by both notes and effects identity.
    A present marker or obligation is conservatively fenced regardless of age.
    """
    results = dict.fromkeys((snapshot.reference.path for snapshot in snapshots), 'changed')
    current = _read(client, transaction, [snapshot.reference for snapshot in snapshots], ROW_FIELDS)
    candidates = []
    job_refs = []
    for scanned in snapshots:
        ref = scanned.reference
        snapshot = current[ref.path]
        scanned_revision = _revision(scanned.update_time)
        if not snapshot.exists or scanned_revision is None or scanned_revision != _revision(snapshot.update_time):
            continue
        row = snapshot.to_dict() or {}
        disposition = classify(row, cutoff=cutoff, discard_deletion_only=discard_deletion_only)
        results[ref.path] = disposition
        if disposition not in CANDIDATES:
            continue
        job_id = row.get('finalization_job_id')
        job_ref = None
        if job_id is not None:
            if not isinstance(job_id, str) or not job_id or '/' in job_id:
                results[ref.path] = 'finalization_fenced'
                continue
            job_ref = client.collection(FINALIZATION_JOBS_COLLECTION).document(job_id)
            job_refs.append(job_ref)
        candidates.append((ref, row, disposition, job_ref))

    jobs = _read(
        client,
        transaction,
        job_refs,
        (
            'uid',
            'conversation_id',
            'finalization_revision',
            'status',
            'fanout_status',
            'finalization_engine',
            'finalization_owner_epoch',
        ),
    )
    custody_refs = []
    settled = []
    for ref, row, disposition, job_ref in candidates:
        user = ref.parent.parent
        uid, cid = user.id, ref.id
        job = jobs[job_ref.path].to_dict() if job_ref is not None else None
        if not _settled_job(uid, cid, row, job or {}):
            results[ref.path] = 'finalization_fenced'
            continue
        _, record_id = record_identity(uid, cid)
        custody = (
            client.collection(ACCOUNT_DELETION_COLLECTION).document(uid),
            client.collection('batch_pipeline_prod_jobs').document(record_id),
            client.collection(outbox.COLLECTION).document(outbox.key(uid, cid)),
            client.collection(outbox.COLLECTION).document(outbox.key(uid, cid + '\0effects')),
        )
        tombstone = user.collection(TOMBSTONES).document(cid)
        custody_refs.extend((*custody, tombstone))
        settled.append((ref, disposition, custody, tombstone))

    metadata = _read(client, transaction, custody_refs, ())
    for conversation_ref, disposition, custody, tombstone in settled:
        if any(metadata[item.path].exists for item in custody):
            results[conversation_ref.path] = 'custody_fenced'
        elif metadata[tombstone.path].exists != (disposition == 'deleted'):
            results[conversation_ref.path] = 'deletion_fenced'
        elif apply:
            transaction.update(conversation_ref, {'status': 'completed'})
    return list(results.values())
