"""Signature and single-attempt transaction for the SCA-2283 historical repair."""

from datetime import datetime, timezone
import os
import re

from google.api_core.exceptions import GoogleAPICallError

from database import conversation_batch_purge_jobs as jobs
from database.batch_pipeline_privacy import privacy_owner_key
from database.batch_pipeline_purge import row_references
from database.batch_pipeline_reads import ReadOnlySnapshot
from utils.batch_pipeline.retention import BATCH_OBJECT_BUCKET_ENV, batch_object_address, delete_batch_object

START = datetime(2026, 10, 15, tzinfo=timezone.utc)
CUTOFF = datetime(2026, 11, 19, 4, 30, tzinfo=timezone.utc)
RPC = {'timeout': 5, 'retry': None}


def signature(snapshot, now):
    data = snapshot.to_dict() or {}
    deadline = data.get('write_pending_until')
    if (
        data.get('erasure_requested') is not True
        or not isinstance(deadline, datetime)
        or not deadline.tzinfo
        or data.get('cleanup_after') != deadline
        or deadline > now
        or 'expires_at' in data
        or not snapshot.create_time
        or not START <= snapshot.create_time < CUTOFF
    ):
        return 'signature', None
    uid = data.get('owner_id')
    identities = data.get('conversation_ids', [])
    if not isinstance(identities, list):
        return 'ambiguous', None
    ids = [*identities]
    for field in ('conversation_id', 'source_conversation_id'):
        if field in data:
            ids.append(data[field])
    if (
        not isinstance(uid, str)
        or not uid
        or '/' in uid
        or not ids
        or any(not isinstance(cid, str) or not cid or '/' in cid for cid in ids)
        or len(set(ids)) != 1
    ):
        return 'ambiguous', None
    try:
        if data.get('owner_key') != privacy_owner_key(uid):
            return 'ambiguous', None
        uris = row_references(data)
        if len(uris) > 1:
            return 'ambiguous', None
        allowed = {value for name in BATCH_OBJECT_BUCKET_ENV if (value := os.getenv(name, '').strip())}
        for uri in uris:
            bucket, path, generation = batch_object_address(uid, uri, allowed)
            if generation is None and (
                bucket != os.getenv('BUCKET_BATCH_PIPELINE')
                or not re.fullmatch(r'batch-pipeline/[^/]+/owners/[^/]+/[^/]+/[^/]+/[0-9a-f]{32}\.enc', path)
            ):
                return 'ambiguous', None
            if generation is not None and generation <= 0:
                return 'ambiguous', None
    except (AttributeError, TypeError, ValueError):
        return 'ambiguous', None
    return 'eligible', (uid, ids[0])


def proof(client, receipt, identity, *, transaction=None):
    uid, cid = identity
    tombstone_ref = client.collection('users').document(uid).collection('deleted_conversations').document(cid)
    tombstone = tombstone_ref.get(transaction=transaction, **RPC)
    pending = [
        ref.get(transaction=transaction, field_paths=[], **RPC).exists
        for ref in (jobs.job_ref(client, uid, cid), jobs.erasure_job_ref(client, uid, cid))
    ]
    deleted_at = (tombstone.to_dict() or {}).get('deleted_at')
    deadline = receipt.to_dict()['write_pending_until']
    valid = (
        isinstance(deleted_at, datetime)
        and bool(deleted_at.tzinfo)
        and receipt.create_time < deleted_at < receipt.update_time
        and deleted_at < deadline
        and not any(pending)
    )
    return valid, tombstone.update_time


def erase(client, receipt, tombstone_version, storage_client):
    """Return false on stale proof. Storage/commit errors propagate to stop the run."""
    api = client._firestore_api
    database = client._database_string
    metadata = client._rpc_metadata
    transaction = ReadOnlySnapshot(client, max_attempts=1)
    response = api.begin_transaction(request={'database': database}, metadata=metadata, **RPC)
    transaction.bind_snapshot(response.transaction)
    committed = False
    try:
        current = receipt.reference.get(transaction=transaction, **RPC)
        if current.update_time != receipt.update_time:
            return False
        _, identity = signature(current, datetime.now(timezone.utc))
        if identity is None:
            return False
        valid, version = proof(client, current, identity, transaction=transaction)
        if not valid or version != tombstone_version:
            return False
        for uri in sorted(row_references(current.to_dict())):
            delete_batch_object(identity[0], uri, storage_client=storage_client, timeout=5, resolve_generation=True)
        api.commit(
            request={
                'database': database,
                'transaction': transaction.id,
                'writes': [{'delete': current.reference._document_path}],
            },
            metadata=metadata,
            **RPC,
        )
        committed = True
        return True
    finally:
        if not committed:
            try:
                api.rollback(request={'database': database, 'transaction': transaction.id}, metadata=metadata, **RPC)
            except GoogleAPICallError:
                pass
        transaction.clear_snapshot()
