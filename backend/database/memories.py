from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import db


def upsert_memory(uid: str, memory_data: dict):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('memories').document(memory_data['id'])
    memory_ref.set(memory_data)


def get_memory(uid, memory_id):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('memories').document(memory_id)
    return memory_ref.get().to_dict()


def get_memories(uid: str, limit: int = 100, offset: int = 0, include_discarded: bool = False):
    memories_ref = (
        db.collection('users').document(uid).collection('memories')
        .where(filter=FieldFilter('deleted', '==', False))
    )
    if not include_discarded:
        memories_ref = memories_ref.where(filter=FieldFilter('discarded', '==', False))
    memories_ref = memories_ref.order_by('created_at', direction=firestore.Query.DESCENDING)
    memories_ref = memories_ref.limit(limit).offset(offset)
    return [doc.to_dict() for doc in memories_ref.stream()]


def update_memory(uid: str, memory_id: str, memoy_data: dict):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('memories').document(memory_id)
    memory_ref.update(memoy_data)


def delete_memory(uid, memory_id):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('memories').document(memory_id)
    memory_ref.update({'deleted': True})


def filter_memories_by_date(uid, start_date, end_date):
    user_ref = db.collection('users').document(uid)
    query = (
        user_ref.collection('memories')
        .where(filter=FieldFilter('created_at', '>=', start_date))
        .where(filter=FieldFilter('created_at', '<=', end_date))
        .where(filter=FieldFilter('discarded', '==', False))
        .order_by('created_at', direction=firestore.Query.DESCENDING)
    )
    return [doc.to_dict() for doc in query.stream()]


def get_memories_batch_operation():
    batch = db.batch()
    return batch


def add_memory_to_batch(batch, uid, memory_data):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('memories').document(memory_data['id'])
    batch.set(memory_ref, memory_data)
