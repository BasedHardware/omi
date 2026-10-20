"""Person-level preferences that are not identity edits (pinning)."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from google.cloud import firestore

from ._client import get_firestore_client, run_transactional


def set_person_pinned(
    uid: str, person_id: str, pinned: bool, *, now: Optional[datetime] = None, firestore_client: Any = None
) -> Optional[Dict[str, Any]]:
    """Pin or unpin a person. Returns the updated document, or None when the person does not exist."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('people').document(person_id)
    now = now or datetime.now(timezone.utc)

    @firestore.transactional
    def apply(transaction: Any) -> Optional[Dict[str, Any]]:
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            return None
        person = snapshot.to_dict() or {}
        if bool(person.get('pinned')) == pinned:
            return {**person, 'id': person.get('id') or person_id}
        update = {'pinned': pinned, 'pinned_at': now if pinned else None, 'updated_at': now}
        transaction.update(ref, update)
        return {**person, **update, 'id': person.get('id') or person_id}

    return run_transactional(client, apply)
