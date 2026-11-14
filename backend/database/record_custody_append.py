"""Exact upload fences: acquire before storage, revise only after acceptance."""

import hashlib
import time
import uuid

from google.cloud import firestore

from config import record_seal_rules as lease
from database._client import get_firestore_client, run_transactional
from database import record_token_lease_metrics as metrics
from database.record_audio import RecordUploadCapacityExceeded
from database.batch_pipeline_record_lease_recovery import prepare_recovery
from database.batch_pipeline_privacy import assert_batch_write_allowed
from database.record_custody_receipts import expires_at


class RecordCustodyFenceLost(RuntimeError):
    """No successful ACK until this upload's own fence can be finalized."""


def resolve_target(uid, cid, recording_session_id=None, *, firestore_client=None):
    """Resolve the same user-scoped target before custody and record admission."""
    if not cid and recording_session_id:
        client = firestore_client if firestore_client is not None else get_firestore_client()
        session = (
            client.collection('users')
            .document(uid)
            .collection('recording_sessions')
            .document(recording_session_id)
            .get()
            .to_dict()
            or {}
        )
        cid = session.get('conversation_id')
    if cid is not None and not isinstance(cid, str):
        raise ValueError('invalid registered conversation identity')
    return cid


def _receipt(ref, session):
    # Both normal finish and lost-fence recovery terminate the same upload.
    return ref.collection('record_custody_recoveries').document(hashlib.sha256(session.encode()).hexdigest())


def begin(uid, cid, session, *, firestore_client=None):
    if not lease.token_lease_serving(uid):
        return False
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(cid)

    @firestore.transactional
    def commit(tx):
        owner = client.collection('users').document(uid).get(transaction=tx).to_dict() or {}
        # Sync opt-out keeps its no-custody path, but never bypasses erasure.
        # Actual custody enrolls the same conversation checks as finish/recovery.
        assert_batch_write_allowed(
            client, tx, uid, conversation_ids=() if owner.get('private_cloud_sync_enabled', True) is False else (cid,)
        )
        if owner.get('private_cloud_sync_enabled', True) is False:
            return False
        snapshot = ref.get(transaction=tx)
        if not snapshot.exists:
            raise RecordCustodyFenceLost('custody target no longer exists; retain local audio')
        row = snapshot.to_dict() or {}
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
        previous = _receipt(ref, session).get(transaction=tx).to_dict() or {}
        if previous.get('accepted'):
            # Keep finish's receipt replay path without reacquiring its fence.
            return True
        sessions = dict(row.get('record_upload_sessions') or {})
        if session in sessions:
            return True
        if len(sessions) >= 128:
            raise RecordUploadCapacityExceeded('record upload session budget exceeded')
        now = time.time()
        late = bool(row.get('record_audio_partial') or row.get('record_audio_closed')) or any(
            lease.token_lease_lapsed(token, now, row=row) for token in sessions.values()
        )
        # An uploader is not a GKE pusher pod. Its own lease remains the exit
        # even after rollback; it never acquires a pusher pod-gone proof.
        sessions[session] = {
            'pod': '',
            'process_started_at': now,
            'last_signal_at': now,
            'lease_expires_at': now + lease.custody_token_lease_seconds(),
            'signal_source': 'custody_append',
            'append_late': late,
        }
        tx.update(ref, {'record_upload_sessions': sessions})
        return True

    return run_transactional(client, commit, transient=True)


def finish(uid, cid, session, *, accepted, late_observed: bool = False, firestore_client=None):
    # A mode rollback must still clear this request's exact fence. Callers only
    # invoke finish for a token acquired by begin; off requests do no IO.
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(cid)
    receipt = _receipt(ref, session)
    # Stable across retries of this call, distinct from a later finish replay.
    attempt = uuid.uuid4().hex

    @firestore.transactional
    def commit(tx):
        # A response lost after commit must not masquerade as a cleared fence.
        # Read before every potential write, including continuation creation.
        recorded = receipt.get(transaction=tx).to_dict() or {}
        if recorded.get('accepted'):
            return bool(recorded.get('late')), recorded.get('finish_attempt') == attempt
        assert_batch_write_allowed(client, tx, uid, conversation_ids=(cid,))
        row = ref.get(transaction=tx).to_dict() or {}
        sessions = dict(row.get('record_upload_sessions') or {})
        token = sessions.get(session)
        if not isinstance(token, dict) or token.get('signal_source') != 'custody_append':
            if accepted:
                raise RecordCustodyFenceLost('retain WAL and retry custody with a fresh fence')
            return False, False
        sessions.pop(session)
        patch: dict[str, object] = {'record_upload_sessions': sessions}
        recovery = None
        late = bool(
            late_observed
            or token.get('append_late')
            or row.get('record_audio_closed')
            or row.get('record_audio_partial')
        ) or any(lease.token_lease_lapsed(value, time.time(), row=row) for value in (token, *sessions.values()))
        eligible = not row.get('deleted') and row.get('record_lane_owner') in {None, 'batch_live_v1', 'batch_sync_v1'}
        if accepted and eligible:
            revision = int(row.get('record_upload_revision') or 0) + 1
            patch['record_upload_revision'] = revision
            # Begin already acquired serve custody. A rollback cannot cancel
            # recovery of bytes accepted under that durable obligation.
            recovered, recovery = prepare_recovery(client, tx, uid, cid, row, revision, time.time())
            patch.update(recovered)
            late |= bool(recovery)
        if recovery:
            tx.set(*recovery)
        tx.update(ref, patch)
        tx.set(
            receipt,
            {
                'upload_revision': patch.get('record_upload_revision', row.get('record_upload_revision', 0)),
                'recorded_at': time.time(),
                'expires_at': expires_at(time.time()),
                'accepted': accepted and eligible,
                'late': accepted and late and eligible,
                'finish_attempt': attempt,
            },
        )
        return accepted and late and eligible, True

    late, own_attempt = run_transactional(client, commit, transient=True)
    if late and own_attempt:
        metrics.LATE_APPEND.inc()
    return late


def recover_committed(uid, cid, session, *, firestore_client=None):
    """Finalize accepted bytes after a lost fence; persist an exact-request receipt.

    Only the request that acquired serve custody calls this after durable storage
    and an accepted response. The receipt makes retries of this recovery no-ops.
    It contains metadata only; original audio and work remain immutable.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(cid)
    receipt = _receipt(ref, session)
    attempt = uuid.uuid4().hex

    @firestore.transactional
    def commit(tx):
        previous = receipt.get(transaction=tx)
        if previous.exists:
            recorded = previous.to_dict() or {}
            own_attempt = recorded.get('finish_attempt') == attempt
            return own_attempt, own_attempt and bool(recorded.get('late'))
        assert_batch_write_allowed(client, tx, uid, conversation_ids=(cid,))
        row = ref.get(transaction=tx).to_dict() or {}
        if (
            not row
            or row.get('deleted')
            or row.get('record_lane_owner') not in {None, 'batch_live_v1', 'batch_sync_v1'}
        ):
            raise RecordCustodyFenceLost('accepted custody cannot revise a missing or ineligible conversation')
        sessions = dict(row.get('record_upload_sessions') or {})
        token = sessions.get(session)
        if isinstance(token, dict) and token.get('signal_source') == 'custody_append':
            sessions.pop(session)
        now = time.time()
        revision = int(row.get('record_upload_revision') or 0) + 1
        recovered, recovery = prepare_recovery(client, tx, uid, cid, row, revision, now)
        patch = {'record_upload_sessions': sessions, 'record_upload_revision': revision, **recovered}
        if recovery:
            tx.set(*recovery)
        tx.update(ref, patch)
        tx.set(
            receipt,
            {
                'upload_revision': revision,
                'recorded_at': now,
                'expires_at': expires_at(now),
                'accepted': True,
                'late': True,
                'finish_attempt': attempt,
            },
        )
        return True, True

    recovered, count_late = run_transactional(client, commit, transient=True)
    if count_late:
        metrics.LATE_APPEND.inc()
    return recovered
