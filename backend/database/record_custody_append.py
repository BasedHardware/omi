"""Exact upload fences: acquire before storage, revise only after acceptance."""

import time

from google.cloud import firestore

from config import record_seal_rules as lease
from database._client import get_firestore_client, run_transactional
from database import record_token_lease_metrics as metrics
from database.record_audio import RecordUploadCapacityExceeded


class RecordCustodyFenceLost(RuntimeError):
    """No successful ACK until this upload's own fence can be finalized."""


def begin(uid, cid, session, *, firestore_client=None):
    if not lease.token_lease_serving(uid):
        return False
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(cid)

    @firestore.transactional
    def commit(tx):
        row = ref.get(transaction=tx).to_dict() or {}
        if (
            not row
            or row.get('deleted')
            or row.get('record_lane_owner')
            not in {
                None,
                'batch_live_v1',
                'batch_sync_v1',
            }
        ):
            return False
        sessions = dict(row.get('record_upload_sessions') or {})
        if session in sessions:
            return True
        if len(sessions) >= 128:
            raise RecordUploadCapacityExceeded('record upload session budget exceeded')
        now = time.time()
        late = bool(row.get('record_audio_partial') or row.get('record_audio_closed')) or any(
            lease.token_lease_lapsed(token, now, row=row) for token in sessions.values()
        )
        # An uploader is not a GKE pusher pod. Empty pod deliberately has no
        # pod-gone proof after rollback; serve uses its own observed lease.
        sessions[session] = {
            'pod': '',
            'process_started_at': now,
            'last_signal_at': now,
            'lease_expires_at': now + lease.token_lease_seconds(),
            'signal_source': 'custody_append',
            'append_late': late,
        }
        tx.update(ref, {'record_upload_sessions': sessions})
        return True

    return run_transactional(client, commit, transient=True)


def finish(uid, cid, session, *, accepted, firestore_client=None):
    # A mode rollback must still clear this request's exact fence. Callers only
    # invoke finish for a token acquired by begin; off requests do no IO.
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(cid)

    @firestore.transactional
    def commit(tx):
        row = ref.get(transaction=tx).to_dict() or {}
        sessions = dict(row.get('record_upload_sessions') or {})
        token = sessions.get(session)
        if not isinstance(token, dict) or token.get('signal_source') != 'custody_append':
            if accepted:
                raise RecordCustodyFenceLost('retain WAL and retry custody with a fresh fence')
            return False
        sessions.pop(session)
        patch = {'record_upload_sessions': sessions}
        recovery = None
        late = bool(token.get('append_late'))
        eligible = not row.get('deleted') and row.get('record_lane_owner') in {None, 'batch_live_v1', 'batch_sync_v1'}
        if accepted and eligible:
            revision = int(row.get('record_upload_revision') or 0) + 1
            patch['record_upload_revision'] = revision
            if (
                late
                and lease.token_lease_serving(uid)
                and (row.get('record_audio_closed') or row.get('record_audio_partial'))
            ):
                from database.batch_pipeline_record_lease_recovery import prepare_recovery

                recovered, recovery = prepare_recovery(client, tx, uid, cid, row, revision, time.time())
                patch.update(recovered)
        if recovery:
            tx.set(*recovery)
        tx.update(ref, patch)
        return accepted and late and eligible

    late = run_transactional(client, commit, transient=True)
    if late:
        metrics.LATE_APPEND.inc()
    return late


def late_snapshot(uid, cid, *, firestore_client=None):
    """Shadow observes the pre-append state; only accepted storage counts it."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    row = client.collection('users').document(uid).collection('conversations').document(cid).get().to_dict() or {}
    if not row or row.get('deleted') or row.get('record_lane_owner') not in {'batch_live_v1', 'batch_sync_v1'}:
        return False
    return bool(row.get('record_audio_closed') or row.get('record_audio_partial')) or any(
        lease.token_lease_lapsed(token, time.time(), row=row)
        for token in (row.get('record_upload_sessions') or {}).values()
    )
