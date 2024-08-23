from typing import List

from google.cloud import firestore

from ._client import db


def get_facts(uid: str, limit: int = 100, offset: int = 0):
    facts_ref = (
        db.collection('users').document(uid).collection('facts')
    )
    facts_ref = facts_ref.order_by('created_at', direction=firestore.Query.DESCENDING)
    facts_ref = facts_ref.limit(limit).offset(offset)
    return [doc.to_dict() for doc in facts_ref.stream()]


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
