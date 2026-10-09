"""Missing owner print repair on the authoritative customer data plane."""

from datetime import datetime, timezone
from google.cloud import firestore
from database._client import get_data_plane_firestore_client as get_firestore_client
from database.account_deletion_marker import account_deletion_document


def get_user_speaker_embedding_recovery_state(uid: str):
    """Existing owner publication timestamp and vector, observed before repair."""
    snapshot = get_firestore_client().collection('users').document(uid).get()
    if not snapshot.exists:
        return None
    data = snapshot.to_dict() or {}
    return data.get('speaker_embedding_updated_at'), data.get('speaker_embedding')


def recover_user_speaker_embedding(uid: str, embedding: list, *, expected_updated_at) -> bool:
    """Repair only an unchanged missing vector; enrollment/teaching/deletion win."""
    client = get_firestore_client()
    ref = client.collection('users').document(uid)
    marker = account_deletion_document(uid, firestore_client=client)

    @firestore.transactional
    def repair(transaction):
        snapshot = ref.get(transaction=transaction)
        deleting = marker.get(transaction=transaction)
        data = snapshot.to_dict() or {}
        if (
            not snapshot.exists
            or deleting.exists
            or data.get('speaker_embedding')
            or data.get('speaker_embedding_updated_at') != expected_updated_at
        ):
            return False
        transaction.update(
            ref, {'speaker_embedding': embedding, 'speaker_embedding_updated_at': datetime.now(timezone.utc)}
        )
        return True

    return repair(client.transaction())
