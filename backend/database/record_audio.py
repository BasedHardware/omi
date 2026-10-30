"""Transactional record-audio closure and cross-session upload custody metadata."""

from google.cloud import firestore

from database._client import get_firestore_client, run_transactional


def seal_record_audio(uid: str, conversation_id: str, *, firestore_client=None) -> bool:
    """Resolve the persisted owner at closure, across websocket sessions.

    Upload failures are sticky across reconnects. A later clean session must
    never certify audio lost by an earlier session, even after a prior seal.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)

    @firestore.transactional
    def commit(tx):
        row = ref.get(transaction=tx).to_dict() or {}
        if (
            row.get('record_lane_owner') not in {'batch_live_v1', 'batch_sync_v1'}
            or row.get('record_upload_failed')
            or row.get('record_upload_sessions')
            or row.get('deleted')
        ):
            return False
        if not row.get('record_audio_closed'):
            tx.update(ref, {'record_audio_closed': True})
        return True

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
        if pending and row.get('record_lane_owner') not in {'batch_live_v1', 'batch_sync_v1'}:
            return False  # Legacy/unowned producers add no metadata writes.
        sessions = dict(row.get('record_upload_sessions') or {})
        if pending:
            if session in sessions:
                return True
            if len(sessions) >= 128:
                raise ValueError('record upload session budget exceeded')
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
        if not row.get('record_upload_failed') or row.get('record_audio_closed'):
            tx.update(ref, {'record_upload_failed': True, 'record_audio_closed': False})
        return True

    return run_transactional(client, commit, transient=True)
