"""Content-free user deletion intent, independent of hard-delete/processing rollback."""

from datetime import datetime, timezone

from google.api_core.exceptions import AlreadyExists

from database._client import db

COLLECTION = 'deleted_conversations'


def is_deleted(uid: str, conversation_id: str) -> bool:
    return db.collection('users').document(uid).collection(COLLECTION).document(conversation_id).get().exists


def record_deletion(uid: str, conversation_id: str) -> None:
    user = db.collection('users').document(uid)
    row = user.collection('conversations').document(conversation_id).get().to_dict() or {}
    # Store identity only, never transcript, structured data, or calendar identity.
    external = row.get('external_data') or {}
    try:
        user.collection(COLLECTION).document(conversation_id).create(
            {
                'conversation_id': conversation_id,
                'deleted_at': datetime.now(timezone.utc),
                'client_session_id': external.get('from_segments_client_session_id'),
                'created_at': row.get('created_at'),
            }
        )
    except AlreadyExists:
        # A retried delete after hard cleanup must preserve the original binding.
        pass
