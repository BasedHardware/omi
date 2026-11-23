"""Non-expiring, all-file WAL custody under the existing native record owner.

This protocol never enrolls a provider job. Per-file pending work and its wake
are committed with the bundle, and survive admission rollback and phone loss.
"""

import hashlib
import json
import time
from uuid import uuid4

from google.cloud import firestore
from config.record_wal_duplicate import MERGE_TARGET_FIELD, RETAINED_DONORS_FIELD, SETTLED_FIELD

from database._client import run_transactional, get_data_plane_firestore_client
from database.batch_pipeline_privacy import (
    assert_batch_write_allowed,
    BatchPrivacyBlocked,
    privacy_owner_key,
    read_batch_owner_snapshot,
)
from database.firestore_read_origin import read_origin
from database.batch_pipeline_store import FirestoreTransaction
from database import record_wal_capacity as capacity

SCHEMA = 'record_wal_handoff_v1'
VERSION = 1
JOB_PREFIX = 'bp_wh_'
BUNDLE_KIND = 'record_wal_bundle'
FILE_KIND = 'record_wal_file'
PENDING_REASON = 'source_alignment_pending'
FENCE_SECONDS = 600


class HandoffConflict(RuntimeError):
    """Unresolved ownership or lost exact-request fence; keep the phone copy."""


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def bundle_id(uid, cid, files):
    return JOB_PREFIX + identity([SCHEMA, uid, cid, files])


def file_identity(uid, cid, generation, entry):
    return identity([SCHEMA, uid, cid, generation, entry])


def intake_collection(client, namespace):
    # Existing admission receipt storage; only tagged WAL files own this index.
    return _ref(client, namespace, '_wal_schema').parent


def _ref(client, namespace, key):
    return FirestoreTransaction.intake_reference(client, namespace, key)


def _file_ref(client, namespace, file_id):
    return _ref(client, namespace, 'wal_file_' + file_id)


def check_owner_authority(
    client,
    tx,
    uid,
    cid,
    source,
    device,
    expected_generation=None,
    *,
    sampling_read_budget=None,
    allow_retained_merge=False,
):
    snapshots = {}
    check = assert_batch_write_allowed
    options = {}
    if sampling_read_budget is not None:
        check = read_batch_owner_snapshot
        options['read_budget'] = sampling_read_budget
    generation = check(
        client,
        tx,
        uid,
        conversation_ids=(cid,),
        expected_generation=expected_generation,
        snapshots=snapshots,
        **options,
    )
    row = snapshots.get('conversations', {}).get(cid) or {}
    user = snapshots.get('user') or {}
    target_id = row.get(MERGE_TARGET_FIELD)
    successor = snapshots.get('conversations', {}).get(target_id) or {}
    retained = (
        allow_retained_merge
        and row.get(SETTLED_FIELD) is True
        and row.get('deleted') is True
        and bool(target_id)
        and target_id == row.get('sync_merged_into')
        and successor.get('private_cloud_sync_enabled') is True
        and not successor.get('uses_custom_stt')
        and not successor.get('deleted')
        and not successor.get('sync_merged_into')
        and cid in (successor.get(RETAINED_DONORS_FIELD) or [])
    )
    if (
        not row
        or (row.get('deleted') or row.get('sync_merged_into'))
        and not retained
        or row.get('record_lane_owner') != 'batch_live_v1'
        or row.get('source') != source
        or row.get('client_device_id') != device
        or row.get('uses_custom_stt')
        or not row.get('private_cloud_sync_enabled')
        or not user.get('private_cloud_sync_enabled', True)
    ):
        raise HandoffConflict('native owner context changed')
    return generation, user.get('data_protection_level', 'enhanced'), row


def has_receipts(uid, cid, *, firestore_client=None):
    client = firestore_client if firestore_client is not None else get_data_plane_firestore_client()
    row = client.collection('users').document(uid).collection('conversations').document(cid).get().to_dict() or {}
    return bool(row.get('record_wal_handoff_present'))


def begin(client, namespace, uid, cid, files, source, device):
    """A scoped fence independent of RECORD_TOKEN_LEASE_MODE (including off)."""
    job_id = bundle_id(uid, cid, files)
    ref = _ref(client, namespace, job_id)
    token = uuid4().hex

    @firestore.transactional
    def acquire(tx):
        generation, protection, row = check_owner_authority(client, tx, uid, cid, source, device)
        previous = ref.get(transaction=tx).to_dict() or {}
        if previous and (previous.get('schema') != SCHEMA or previous.get('version') != VERSION):
            raise HandoffConflict('unsupported custody receipt schema')
        if previous and previous.get('privacy_generation') != generation:
            raise BatchPrivacyBlocked('privacy_generation_changed')
        if previous.get('state') == 'accepted':
            return previous
        file_rows = []
        new_files = []
        for entry in files:
            file_id = file_identity(uid, cid, generation, entry)
            prior = _file_ref(client, namespace, file_id).get(transaction=tx).to_dict() or {}
            file_rows.append({'file_id': file_id, **entry, 'receipt': prior.get('receipt')})
            if not prior:
                new_files.append((file_id, entry))
        fence = {
            'schema': SCHEMA,
            'version': VERSION,
            'job_id': job_id,
            'kind': BUNDLE_KIND,
            'owner_id': uid,
            'owner_key': privacy_owner_key(uid),
            'conversation_id': cid,
            'source': source,
            'client_device_id': device,
            'privacy_generation': generation,
            'data_protection_level': protection,
            'base_upload_revision': int(row.get('record_upload_revision') or 0),
            'state': 'preparing',
            'fence_token': token,
            'fence_until': time.time() + FENCE_SECONDS,
            'files': file_rows,
        }
        # A fresh request may supersede an interrupted one. Only its exact token
        # may commit; concurrent writers share create-only media, never paid work.
        capacity.reserve(client, tx, uid, [entry for _, entry in new_files])
        for file_id, entry in new_files:
            tx.set(
                _file_ref(client, namespace, file_id),
                {
                    'schema': SCHEMA,
                    'version': VERSION,
                    'kind': capacity.RESERVATION_KIND,
                    'owner_id': uid,
                    'owner_key': privacy_owner_key(uid),
                    'conversation_id': cid,
                    'privacy_generation': generation,
                    'file_id': file_id,
                    'quota_bytes': entry['size'] + capacity.ENCRYPTION_OVERHEAD,
                    'wal_pending_since': time.time(),
                },
            )
        tx.set(ref, fence)
        return fence

    return run_transactional(client, acquire, transient=True)


def commit(client, namespace, fence, receipts):
    """CAS owner/privacy/fence; commit every original, work, wake and revision."""
    uid, cid, job_id = fence['owner_id'], fence['conversation_id'], fence['job_id']
    ref = _ref(client, namespace, job_id)

    @firestore.transactional
    def finish(tx):
        _, protection, row = check_owner_authority(
            client, tx, uid, cid, fence['source'], fence['client_device_id'], fence['privacy_generation']
        )
        if protection != fence['data_protection_level']:
            raise BatchPrivacyBlocked('data_protection_changed')
        if int(row.get('record_upload_revision') or 0) < fence['base_upload_revision']:
            raise HandoffConflict('record upload revision regressed')
        current = ref.get(transaction=tx).to_dict() or {}
        if current.get('state') == 'accepted':
            return current
        if current.get('fence_token') != fence['fence_token'] or current.get('fence_until', 0) < time.time():
            raise HandoffConflict('exact request fence lost')
        if len(receipts) != len(fence['files']) or not receipts:
            raise HandoffConflict('all-file receipt required')
        entries = []
        for entry, receipt in zip(fence['files'], receipts):
            if (
                not receipt.get('generation')
                or not receipt.get('crc32c')
                or receipt.get('size') != entry['size']
                or receipt.get('sha256') != entry['sha256']
                or receipt.get('file_id') != entry['file_id']
                or receipt.get('name') != entry['name']
                or not receipt.get('stored_size')
            ):
                raise HandoffConflict('unverified original file')
            file_ref = _file_ref(client, namespace, entry['file_id'])
            prior = file_ref.get(transaction=tx).to_dict() or {}
            if prior.get('receipt') and prior['receipt'] != receipt:
                raise HandoffConflict('immutable file receipt conflict')
            entries.append((entry, receipt, file_ref, prior))
        now = time.time()
        revision = int(row.get('record_upload_revision') or 0) + 1
        common = {
            'schema': SCHEMA,
            'version': VERSION,
            'owner_id': uid,
            'owner_key': privacy_owner_key(uid),
            'conversation_id': cid,
            'privacy_generation': fence['privacy_generation'],
        }
        # All reads above, all writes below (including on retries).
        for entry, receipt, file_ref, prior in entries:
            if prior.get('receipt'):
                continue  # A rebundled file keeps its one obligation and wake.
            file_id = entry['file_id']
            work = {
                **common,
                'file_id': file_id,
                'state': 'pending',
                'reason': PENDING_REASON,
                'created_at': now,
                'pending_since': now,
                'upload_revision': revision,
            }
            tx.set(
                file_ref,
                {
                    **common,
                    'kind': FILE_KIND,
                    'file_id': file_id,
                    'receipt': receipt,
                    'uri': receipt['uri'],
                    'obligation': work,
                    'outbox': work,
                    'wal_pending_since': prior.get('wal_pending_since', now),
                    **({'quota_bytes': prior['quota_bytes']} if 'quota_bytes' in prior else {}),
                },
            )
        accepted = {
            **fence,
            'state': 'accepted',
            'accepted_at': now,
            'upload_revision': revision,
            'files': [{**entry, 'receipt': receipt} for entry, receipt, _, _ in entries],
        }
        accepted.pop('fence_token', None)
        accepted.pop('fence_until', None)
        tx.set(ref, accepted)
        conversation = client.collection('users').document(uid).collection('conversations').document(cid)
        tx.update(conversation, {'record_upload_revision': revision, 'record_wal_handoff_present': True})
        return accepted

    return run_transactional(client, finish, transient=True)


def check_fence(client, namespace, fence):
    @firestore.transactional
    def check(tx):
        _, protection, _ = check_owner_authority(
            client,
            tx,
            fence['owner_id'],
            fence['conversation_id'],
            fence['source'],
            fence['client_device_id'],
            fence['privacy_generation'],
        )
        if protection != fence['data_protection_level']:
            raise BatchPrivacyBlocked('data_protection_changed')
        current = _ref(client, namespace, fence['job_id']).get(transaction=tx).to_dict() or {}
        if current.get('fence_token') != fence['fence_token'] or current.get('fence_until', 0) < time.time():
            raise HandoffConflict('exact request fence lost')

    return run_transactional(client, check)


def status(receipt):
    # Phase 1 deliberately has no completion path. An old native job's result
    # cannot discharge these original files; phase 2 must settle every file.
    return {
        'job_id': receipt['job_id'],
        'status': 'processing',
        'total_files': len(receipt['files']),
        'total_segments': 0,
        'processed_segments': 0,
        'successful_segments': 0,
        'failed_segments': 0,
        'poll_after_ms': 300000,
        'lane': 'backfill',
        'reason_code': PENDING_REASON,
    }


def read_status(client, namespace, uid, job_id):
    @firestore.transactional
    def read(tx):
        receipt = _ref(client, namespace, job_id).get(transaction=tx).to_dict() or {}
        if receipt.get('owner_id') != uid or receipt.get('state') != 'accepted':
            return None
        if receipt.get('schema') != SCHEMA or receipt.get('version') != VERSION:
            raise HandoffConflict('unsupported custody receipt schema')
        assert_batch_write_allowed(
            client,
            tx,
            uid,
            conversation_ids=(receipt['conversation_id'],),
            expected_generation=receipt['privacy_generation'],
        )
        return status(receipt)

    return run_transactional(client, read)


@read_origin('job:record_wal_handoff:pending_sample')
def pending_sample(client, namespace):
    """Indexed work discovery, independent of phones, producer switch and TTL."""
    query = intake_collection(client, namespace)
    # Single-field indexes only. pending_since exists exactly while unsettled.
    oldest = list(query.order_by('wal_pending_since').limit(1).stream(timeout=10, retry=None))
    count = query.where('wal_pending_since', '>=', 0).limit(10001).count().get(timeout=10, retry=None)[0][0].value
    return int(count), (oldest[0].to_dict()['wal_pending_since'] if oldest else None)
