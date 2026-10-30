"""Person writes that are not identity edits: pinning, and creating one person per name."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database.people_generation import bump_people_generation
from ._client import get_firestore_client, run_transactional
from .firestore_transaction_retry import run_with_transaction_contention_retry
from .speaker_learning_fields import project_person_learning


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
        bump_people_generation(transaction, ref)
        return {**person, **update, 'id': person.get('id') or person_id}

    return run_transactional(client, apply)


def get_or_create_person_by_name(uid: str, data: Dict[str, Any], *, firestore_client: Any = None) -> Dict[str, Any]:
    """Create ``data`` as a new person unless an active person already has its exact name.

    The name check and the create commit in one transaction, so concurrent or retried
    requests for the same new name share one person instead of each creating their own.
    Returns the existing person, projected like a lookup, or ``data`` once it is created.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    people_ref = client.collection('users').document(uid).collection('people')
    same_name = people_ref.where(filter=FieldFilter('name', '==', data['name']))

    @firestore.transactional
    def apply(transaction: Any) -> Optional[Dict[str, Any]]:
        # Read every match: under a limit, dismissed namesakes could hide the active person.
        for snapshot in list(same_name.stream(transaction=transaction)):
            person = snapshot.to_dict() or {}
            if person.get('is_dismissed') is not True:
                return {**person, 'id': person.get('id') or snapshot.id}
        # The transaction's read of every same-name person guards the race; `set` (like the
        # action-item dedupe) also persists under the hermetic E2E Firestore fake.
        transaction.set(people_ref.document(data['id']), {**data, 'is_user_created': True})
        return None

    existing = run_with_transaction_contention_retry(client.transaction, apply, operation_name='person_get_or_create')
    if existing is None:
        return data
    return project_person_learning(uid, existing, firestore_client=client)
