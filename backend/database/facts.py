from datetime import datetime, timezone
from typing import List

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import db


def get_facts(uid: str, limit: int = 100, offset: int = 0):
    print('get_facts', uid, limit, offset)
    facts_ref = db.collection('users').document(uid).collection('facts')
    facts_ref = (
        facts_ref.order_by('scoring', direction=firestore.Query.DESCENDING)
        .order_by('created_at', direction=firestore.Query.DESCENDING)
        .where(filter=FieldFilter('deleted', '==', False))
    )
    facts_ref = facts_ref.limit(limit).offset(offset)
    # TODO: put user review to firestore query
    facts = [doc.to_dict() for doc in facts_ref.stream()]
    result = [fact for fact in facts if fact['user_review'] is not False]
    return result


def get_user_public_facts(uid: str, limit: int = 100, offset: int = 0):
    print('get_public_facts', limit, offset)

    facts_ref = db.collection('users').document(uid).collection('facts')
    facts_ref = (
        facts_ref.order_by('scoring', direction=firestore.Query.DESCENDING)
        .order_by('created_at', direction=firestore.Query.DESCENDING)
        .where(filter=FieldFilter('deleted', '==', False))
    )

    facts_ref = facts_ref.limit(limit).offset(offset)

    facts = [doc.to_dict() for doc in facts_ref.stream()]

    # Consider visibility as 'public' if it's missing
    public_facts = [fact for fact in facts if fact.get('visibility', 'public') == 'public']

    return public_facts


def get_non_filtered_facts(uid: str, limit: int = 100, offset: int = 0):
    print('get_non_filtered_facts', uid, limit, offset)
    facts_ref = db.collection('users').document(uid).collection('facts')
    facts_ref = (
        facts_ref.order_by('created_at', direction=firestore.Query.DESCENDING)
        .where(filter=FieldFilter('deleted', '==', False))
    )
    facts_ref = facts_ref.limit(limit).offset(offset)
    return [doc.to_dict() for doc in facts_ref.stream()]


def create_fact(uid: str, data: dict):
    user_ref = db.collection('users').document(uid)
    facts_ref = user_ref.collection('facts')
    fact_ref = facts_ref.document(data['id'])
    fact_ref.set(data)


def save_facts(uid: str, data: List[dict]):
    batch = db.batch()
    user_ref = db.collection('users').document(uid)
    facts_ref = user_ref.collection('facts')
    for fact in data:
        fact_ref = facts_ref.document(fact['id'])
        batch.set(fact_ref, fact)
    batch.commit()


def delete_facts(uid: str):
    batch = db.batch()
    user_ref = db.collection('users').document(uid)
    facts_ref = user_ref.collection('facts')
    for doc in facts_ref.stream():
        batch.delete(doc.reference)
    batch.commit()


def get_fact(uid: str, fact_id: str):
    user_ref = db.collection('users').document(uid)
    facts_ref = user_ref.collection('facts')
    fact_ref = facts_ref.document(fact_id)
    return fact_ref.get().to_dict()


def review_fact(uid: str, fact_id: str, value: bool):
    user_ref = db.collection('users').document(uid)
    facts_ref = user_ref.collection('facts')
    fact_ref = facts_ref.document(fact_id)
    fact_ref.update({'reviewed': True, 'user_review': value})


def change_fact_visibility(uid: str, fact_id: str, value: str):
    user_ref = db.collection('users').document(uid)
    facts_ref = user_ref.collection('facts')
    fact_ref = facts_ref.document(fact_id)
    fact_ref.update({'visibility': value})


def edit_fact(uid: str, fact_id: str, value: str):
    user_ref = db.collection('users').document(uid)
    facts_ref = user_ref.collection('facts')
    fact_ref = facts_ref.document(fact_id)
    fact_ref.update({'content': value, 'edited': True, 'updated_at': datetime.now(timezone.utc)})


def delete_fact(uid: str, fact_id: str):
    user_ref = db.collection('users').document(uid)
    facts_ref = user_ref.collection('facts')
    fact_ref = facts_ref.document(fact_id)
    fact_ref.update({'deleted': True})


def delete_all_facts(uid: str):
    user_ref = db.collection('users').document(uid)
    facts_ref = user_ref.collection('facts')
    query = facts_ref.where(filter=FieldFilter('deleted', '==', False))
    batch = db.batch()
    for doc in query.stream():
        batch.update(doc.reference, {'deleted': True})
    batch.commit()


def delete_facts_for_memory(uid: str, memory_id: str):
    batch = db.batch()
    user_ref = db.collection('users').document(uid)
    facts_ref = user_ref.collection('facts')
    query = (
        facts_ref.where(filter=FieldFilter('memory_id', '==', memory_id))
        .where(filter=FieldFilter('deleted', '==', False))
    )

    removed_ids = []
    for doc in query.stream():
        batch.update(doc.reference, {'deleted': True})
        removed_ids.append(doc.id)
    batch.commit()
    print('delete_facts_for_memory', memory_id, len(removed_ids))


def migrate_facts(prev_uid: str, new_uid: str, app_id: str = None):
    """
    Migrate facts from one user to another.
    If app_id is provided, only migrate facts related to that app.
    """
    print(f'Migrating facts from {prev_uid} to {new_uid}')

    # Get source facts
    prev_user_ref = db.collection('users').document(prev_uid)
    prev_facts_ref = prev_user_ref.collection('facts')

    # Apply app_id filter if provided
    if app_id:
        query = prev_facts_ref.where(filter=FieldFilter('app_id', '==', app_id))
    else:
        query = prev_facts_ref

    # Get facts to migrate
    facts_to_migrate = [doc.to_dict() for doc in query.stream()]

    if not facts_to_migrate:
        print(f'No facts to migrate for user {prev_uid}')
        return 0

    # Create batch for destination user
    batch = db.batch()
    new_user_ref = db.collection('users').document(new_uid)
    new_facts_ref = new_user_ref.collection('facts')

    # Add facts to batch
    for fact in facts_to_migrate:
        fact_ref = new_facts_ref.document(fact['id'])
        batch.set(fact_ref, fact)

    # Commit batch
    batch.commit()
    print(f'Migrated {len(facts_to_migrate)} facts from {prev_uid} to {new_uid}')
    return len(facts_to_migrate)
