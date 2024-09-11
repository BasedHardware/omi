from datetime import datetime, timezone
from typing import List

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import db


def get_facts(uid: str, limit: int = 100, offset: int = 0):
    # TODO: how to query more
    facts_ref = db.collection('users').document(uid).collection('facts')
    facts_ref = (
        facts_ref.order_by('created_at', direction=firestore.Query.DESCENDING)
        .where(filter=FieldFilter('deleted', '==', False))
        # .where(filter=FieldFilter('user_review', '!=', False))
    )
    facts_ref = facts_ref.limit(limit).offset(offset)
    facts = [doc.to_dict() for doc in facts_ref.stream()]
    print('get_facts', len(facts))
    result = [fact for fact in facts if fact['user_review'] is not False]
    print('get_facts', len(result))
    return result


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
