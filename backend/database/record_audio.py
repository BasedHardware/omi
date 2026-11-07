"""Transactional record-audio closure and cross-session upload custody metadata."""

from typing import Any, Literal
import time

from google.cloud import firestore

from config import record_seal_rules
from database._client import get_firestore_client, run_transactional
from config import pipeline_attention as pipeline_policy
from utils.batch_pipeline import record_attention
from utils.conversations import pipeline_attention


class RecordUploadCapacityExceeded(ValueError):
    """The persisted producer map cannot accept another token."""


RecordSealRefusal = Literal['producer_pending', 'upload_failed', 'not_batch_owner', 'deleted']


def seal_record_audio(uid: str, conversation_id: str, *, firestore_client=None) -> RecordSealRefusal | None:
    """Resolve the persisted owner at closure, across websocket sessions.

    Upload failures are sticky across reconnects. Only the separate full-proof
    repair path may clear one; a later clean session cannot certify lost audio.
    Return None on success, otherwise a closed, content-free refusal reason.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)
    committed_row = {}
    observed = pipeline_attention.attention(uid) if pipeline_attention.admitted(uid) else None

    @firestore.transactional
    def commit(tx):
        committed_row.clear()
        row = ref.get(transaction=tx).to_dict() or {}
        was_closed = row.get('record_audio_closed') is True
        if row.get('deleted') or not row:
            return 'deleted'
        if row.get('record_lane_owner') not in {'batch_live_v1', 'batch_sync_v1'}:
            return 'not_batch_owner'
        if row.get('record_upload_failed'):
            return 'upload_failed'
        if row.get('record_upload_sessions'):
            if record_seal_rules.refused_stamp_enabled() and row.get('record_seal_refused_at') is None:
                tx.update(ref, {'record_seal_refused_at': time.time()})
            return 'producer_pending'
        if row.get('record_audio_partial'):
            # A clean late producer certifies its drain, never an earlier
            # missing tail. Repair refreshes the separate partial barrier.
            return None
        if not row.get('record_audio_closed') or row.get('record_seal_refused_at') is not None:
            patch: dict[str, Any] = {'record_audio_closed': True}
            if row.get('record_seal_refused_at') is not None:
                patch['record_seal_refused_at'] = None
            if observed is not None:
                patch[pipeline_policy.FIELD] = {
                    **(row.get(pipeline_policy.FIELD) or {}),
                    'attention': (row.get(pipeline_policy.FIELD) or {}).get('attention', observed),
                    'sealed_at': pipeline_policy.seconds((row.get(pipeline_policy.FIELD) or {}).get('sealed_at'))
                    or time.time(),
                }
            tx.update(ref, patch)
            row.update(patch)
        committed_row.update(row, record_audio_closed=True)
        committed_row['_new_seal'] = not was_closed
        return None

    result = run_transactional(client, commit, transient=True)
    if result is None and committed_row.get('_new_seal') and observed is not None:
        captured = pipeline_policy.capture_end(committed_row)
        closed = pipeline_policy.seconds(committed_row.get('finished_at'))
        pipeline_attention.metrics.stage(
            'recorded_span_to_seal', time.time() - captured if captured else None, observed
        )
        pipeline_attention.metrics.stage('finished_to_seal', time.time() - closed if closed else None, observed)
        finished = pipeline_policy.seconds((committed_row.get(pipeline_policy.FIELD) or {}).get('producer_finished_at'))
        pipeline_attention.metrics.stage(
            'producer_finish_to_seal', time.time() - finished if finished else None, observed
        )
    if result is None and pipeline_policy.record_fast_enabled() and committed_row:
        record_attention.sealed(uid, conversation_id, committed_row)
    return result


def set_record_upload_pending(
    uid: str, conversation_id: str, session: str, pending: bool, *, producer=None, firestore_client=None
):
    """Track a session's buffered/in-flight audio before accepting its first frame.

    No expiry: a dead producer cannot prove that its tail reached storage.
    Clear only this producer's token after its successful drain.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)
    instrument = pipeline_attention.admitted(uid)

    @firestore.transactional
    def commit(tx):
        row = ref.get(transaction=tx).to_dict()
        if row is None:
            return False
        if pending and row.get('record_lane_owner') not in {None, 'batch_live_v1', 'batch_sync_v1'}:
            return False  # Immutable legacy owners cannot later enter batch custody.
        sessions = dict(row.get('record_upload_sessions') or {})
        if pending:
            if session in sessions:
                return True
            if len(sessions) >= 128:
                raise RecordUploadCapacityExceeded('record upload session budget exceeded')
            sessions[session] = producer or True
            tx.update(
                ref,
                {
                    'record_upload_sessions': sessions,
                    'record_audio_closed': False,
                    'record_upload_revision': int(row.get('record_upload_revision') or 0) + 1,
                },
            )
        elif session in sessions:
            if isinstance(sessions[session], dict) and 'abandoned_at' in sessions[session]:
                return False  # Only repair's retained-tail proof may release this fence.
            sessions.pop(session)
            update = {'record_upload_sessions': sessions}
            if not sessions and instrument:
                update[pipeline_policy.FIELD] = {
                    **(row.get(pipeline_policy.FIELD) or {}),
                    'producer_finished_at': time.time(),
                }
            tx.update(ref, update)
        return True

    return run_transactional(client, commit, transient=True)


def abandon_record_upload_session(uid: str, conversation_id: str, session: str, *, firestore_client=None) -> bool:
    """Attest that one producer stopped, never that its tail was projected.

    The caller must first stop its tasks and settle all in-flight executor work.
    Preserve the token for repair's archive/tail proof; never recreate a row or
    affect a reconnect's different token. Retries preserve the first attestation.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)

    @firestore.transactional
    def commit(tx):
        row = ref.get(transaction=tx).to_dict()
        if not row or row.get('deleted'):
            return False
        sessions = dict(row.get('record_upload_sessions') or {})
        producer = sessions.get(session)
        if not isinstance(producer, dict):
            return False  # Absent/legacy tokens cannot acquire an invented identity.
        if 'abandoned_at' not in producer:
            sessions[session] = {**producer, 'abandoned_at': time.time()}
            tx.update(ref, {'record_upload_sessions': sessions})
        return True

    return run_transactional(client, commit, transient=True)


def mark_record_upload_failed(uid: str, conversation_id: str, *, firestore_client=None) -> bool:
    """Persist a terminal upload/drop refusal before the session forgets it."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)

    @firestore.transactional
    def commit(tx):
        row = ref.get(transaction=tx).to_dict()
        if row is None:
            return False  # Never recreate a deleted conversation.
        if row.get('record_lane_owner') not in {None, 'batch_live_v1', 'batch_sync_v1'}:
            return False  # Immutable legacy owners never enter this protocol.
        # Always write, including repeated failures: a repair plan must observe
        # a new failure even while the sticky flag was already true.
        tx.update(
            ref,
            {
                'record_upload_failed': True,
                'record_audio_closed': False,
                'record_upload_revision': int(row.get('record_upload_revision') or 0) + 1,
            },
        )
        return True

    return run_transactional(client, commit, transient=True)
