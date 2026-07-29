import copy
from typing import Any, Dict, List, Optional

from google.cloud import firestore

from database._client import get_firestore_client

_FINALIZATION_IDENTITY_FIELDS = ('finalization_incarnation_id', 'finalization_job_id', 'finalization_revision')


def get_conversation_audio_source(
    uid: str,
    conversation_id: str,
    *,
    firestore_client: Any = None,
) -> Optional[Dict[str, Any]]:
    """Read only the playback stamp and row identity needed for source-fenced invalidation."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    conversation_ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)
    snapshot = conversation_ref.get(field_paths=['conversation_audio', *_FINALIZATION_IDENTITY_FIELDS])
    if not getattr(snapshot, 'exists', False):
        return None
    return snapshot.to_dict() or {}


def commit_conversation_audio_if_source_current(
    uid: str,
    conversation_id: str,
    conversation_audio: Dict[str, Any],
    *,
    expected_audio_files: List[Dict[str, Any]],
    expected_finalization_identity: tuple[str | None, str | None, int | None] | None,
    firestore_client: Any = None,
) -> bool:
    """Stamp an artifact only while both its row identity and audio source remain current."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    conversation_ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)
    transaction = client.transaction()

    @firestore.transactional
    def _commit(transaction) -> bool:
        snapshot = conversation_ref.get(transaction=transaction)
        if not getattr(snapshot, 'exists', False):
            return False
        current = snapshot.to_dict() or {}
        if (
            expected_finalization_identity is not None
            and tuple(current.get(field) for field in _FINALIZATION_IDENTITY_FIELDS) != expected_finalization_identity
        ):
            return False
        if current.get('audio_files') != expected_audio_files:
            return False
        transaction.update(conversation_ref, {'conversation_audio': copy.deepcopy(conversation_audio)})
        return True

    return _commit(transaction)
