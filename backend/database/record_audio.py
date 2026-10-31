"""Transactional record-audio closure and cross-session upload custody metadata."""

from typing import Literal

from google.cloud import firestore

from database._client import get_firestore_client, run_transactional


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

    @firestore.transactional
    def commit(tx):
        row = ref.get(transaction=tx).to_dict() or {}
        if row.get('deleted') or not row:
            return 'deleted'
        if row.get('record_lane_owner') not in {'batch_live_v1', 'batch_sync_v1'}:
            return 'not_batch_owner'
        if row.get('record_upload_failed'):
            return 'upload_failed'
        if row.get('record_upload_sessions'):
            return 'producer_pending'
        if not row.get('record_audio_closed'):
            tx.update(ref, {'record_audio_closed': True})
        return None

    return run_transactional(client, commit, transient=True)


def set_record_upload_pending(
    uid: str, conversation_id: str, session: str, pending: bool, *, producer=None, firestore_client=None
):
    """Track a session's buffered/in-flight audio before accepting its first frame.

    No expiry: a dead producer cannot prove that its tail reached storage.
    Clear only this producer's token after its successful drain.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)

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
            sessions.pop(session)
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
