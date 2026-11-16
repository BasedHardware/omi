"""Durable quiet obligations and a paid-once permit shared with on-open notes.

The permit lives on the existing summary lease, separate from full-processing
attempts. A failed/cancelled paid call is not automatically bought again; final
processing retains its own budget. Dispatch and lease contention can retry.
"""

from datetime import datetime, timedelta, timezone

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database import conversations_v3 as store, conversations_v3_leases as leases
from database.account_deletion_marker import account_deletion_document
from database.account_deletion_policy import account_deletion_marker_blocks_access
from utils.conversations.v3 import Conflict, policy, summary_input
from utils.conversations.v3.outline import SILENCE

QUIET = timedelta(seconds=30)


def source_patch(uid, snapshot, *, now, decoded=None):
    row = snapshot.to_dict() or {}
    if row.get('v3_manual_end') or row.get('data_protection_level') == 'private' or row.get('is_locked'):
        return {'v3_quiet_pending': False}
    if not row.get('transcript_segments'):
        return {}
    decoded = decoded if decoded is not None else store.decode_row(uid, snapshot)
    if not decoded or decoded.get('_v3_unreadable') or not decoded.get('transcript_segments'):
        return {}
    generation = summary_input.fingerprint(decoded)
    if generation == row.get('v3_quiet_generation'):
        return {}
    return {
        'v3_quiet_generation': generation,
        'v3_quiet_due': max(now, row.get('finished_at') or now) + QUIET,
        'v3_quiet_pending': True,
    }


def obligation(uid, rid, generation=None, *, firestore_client=None):
    client = firestore_client or store.get_firestore_client()
    row = store.user_conversations(client, uid).document(rid).get().to_dict() or {}
    if (
        not row.get('v3_quiet_pending')
        or not row.get('recording')
        or row.get('deleted')
        or row.get('is_locked')
        or row.get('data_protection_level') == 'private'
        or generation
        and generation != row.get('v3_quiet_generation')
    ):
        return None
    return row


def settle(uid, rid, generation, *, firestore_client=None):
    client = firestore_client or store.get_firestore_client()
    ref = store.user_conversations(client, uid).document(rid)

    @firestore.transactional
    def finish(tx):
        row = ref.get(transaction=tx).to_dict() or {}
        if row.get('v3_quiet_pending') and row.get('v3_quiet_generation') == generation:
            tx.update(ref, {'v3_quiet_pending': False})

    finish(client.transaction())


def sources_current(tx, client, uid, row, *, quiet=False):
    """Read source/tail fences before the first write, including newly arrived recordings."""
    coll = store.user_conversations(client, uid)
    ids = row.get('v3_recording_ids') or []
    if not ids or len(ids) > store.LIMIT:
        return None
    snapshots = {rid: coll.document(rid).get(transaction=tx) for rid in ids}
    # A new recording can arrive before the canonical builder projects it. The
    # query participates in this transaction, so that phantom also fences commit.
    query = coll.where(filter=FieldFilter('v3_pending', '==', True))
    if not quiet and row.get('status') != 'in_progress':
        if not row.get('started_at') or not row.get('finished_at'):
            return None
        # A later live capture cannot extend an already closed window. Keep
        # nearby pending sources fenced, using the existing pending/start index.
        query = query.where(filter=FieldFilter('started_at', '>=', row['started_at'] - SILENCE)).where(
            filter=FieldFilter('started_at', '<', row['finished_at'] + SILENCE)
        )
    pending = list(query.limit(store.LIMIT + 1).stream(transaction=tx))
    if len(pending) > store.LIMIT:
        return None
    snapshots.update({snap.id: snap for snap in pending})
    expected = row.get('v3_source_hashes') or {}
    revisions = {}
    for rid, snap in snapshots.items():
        source = snap.to_dict() or {}
        if (
            not snap.exists
            or source.get('deleted')
            or source.get('is_locked')
            or source.get('data_protection_level') == 'private'
        ):
            return None
        if policy.transcription_pending(source) or policy.transcription_failed(source):
            return None
        if quiet and source.get('v3_quiet_due') and datetime.now(timezone.utc) < source['v3_quiet_due']:
            return None
        decoded = store.decode_row(uid, snap)
        if not decoded or summary_input.fingerprint(decoded) != expected.get(rid):
            return None
        revisions[rid] = snap.update_time
    return revisions


def reserve(uid, cid, token, revision, *, quiet=False, firestore_client=None):
    client = firestore_client or store.get_firestore_client()
    ref = store.user_conversations(client, uid).document(cid)
    held = leases.lease_ref(client, uid, 'summary-' + cid)

    @firestore.transactional
    def begin(tx):
        snapshot = ref.get(transaction=tx)
        row = store.decode_row(uid, snapshot)
        deletion = account_deletion_document(uid, firestore_client=client).get(transaction=tx)
        lease = held.get(transaction=tx).to_dict() or {}
        now = datetime.now(timezone.utc)
        if account_deletion_marker_blocks_access(
            marker_exists=deletion.exists, raw_status=(deletion.to_dict() or {}).get('status')
        ):
            raise Conflict('account_deletion')
        if lease.get('token') != token or not lease.get('until') or lease['until'] <= now:
            raise Conflict('lease_lost')
        if (
            not row
            or snapshot.update_time != revision
            or row.get('deleted')
            or row.get('is_locked')
            or row.get('recording')
            or row.get('data_protection_level') == 'private'
            or not summary_input.eligible(row)
            or summary_input.exact(row)
        ):
            return None
        if quiet and (
            not row.get('v3_derived')
            or row.get('status') != 'in_progress'
            or not row.get('finished_at')
            or now < row['finished_at'] + QUIET
        ):
            return None
        sources = sources_current(tx, client, uid, row, quiet=quiet) if row.get('v3_derived') else {}
        if sources is None:
            return None
        key = summary_input.fingerprint(row)
        # Do not evict spent permits: even a correction back to old text cannot
        # buy it again. Refuse further speculation if the bounded ledger is full.
        spent = list(lease.get('snapshot_inputs') or [])
        if key in spent or len(spent) >= store.LIMIT:
            return None
        tx.update(held, {'snapshot_inputs': [*spent, key]})
        return {'row': row, 'revision': snapshot.update_time, 'sources': sources, 'input_hash': key}

    return begin(client.transaction())
