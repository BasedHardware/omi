from datetime import datetime, timezone
from typing import List

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import db

memories_collection = 'memories'


def get_memories(uid: str, limit: int = 100, offset: int = 0):
    print('get_memories', uid, limit, offset)
    memories_ref = db.collection('users').document(uid).collection('facts')
    memories_ref = (
        memories_ref.order_by('scoring', direction=firestore.Query.DESCENDING)
        .order_by('created_at', direction=firestore.Query.DESCENDING)
        .where(filter=FieldFilter('deleted', '==', False))
    )
    memories_ref = memories_ref.limit(limit).offset(offset)
    # TODO: put user review to firestore query
    memories = [doc.to_dict() for doc in memories_ref.stream()]
    result = [memory for memory in memories if memory['user_review'] is not False]
    return result


def get_user_public_memories(uid: str, limit: int = 100, offset: int = 0):
    print('get_public_memories', limit, offset)

    memories_ref = db.collection('users').document(uid).collection('facts')
    memories_ref = (
        memories_ref.order_by('scoring', direction=firestore.Query.DESCENDING)
        .order_by('created_at', direction=firestore.Query.DESCENDING)
        .where(filter=FieldFilter('deleted', '==', False))
    )

    memories_ref = memories_ref.limit(limit).offset(offset)

    memories = [doc.to_dict() for doc in memories_ref.stream()]

    # Consider visibility as 'public' if it's missing
    public_memories = [memory for memory in memories if memory.get('visibility', 'public') == 'public']

    return public_memories


def get_non_filtered_memories(uid: str, limit: int = 100, offset: int = 0):
    print('get_non_filtered_memories', uid, limit, offset)
    memories_ref = db.collection('users').document(uid).collection('facts')
    memories_ref = (
        memories_ref.order_by('created_at', direction=firestore.Query.DESCENDING)
        .where(filter=FieldFilter('deleted', '==', False))
    )
    memories_ref = memories_ref.limit(limit).offset(offset)
    return [doc.to_dict() for doc in memories_ref.stream()]


def create_memory(uid: str, data: dict):
    user_ref = db.collection('users').document(uid)
    memories_ref = user_ref.collection('facts')
    memory_ref = memories_ref.document(data['id'])
    memory_ref.set(data)
    # TODO: remove after migration
    new_memories_ref = user_ref.collection(memories_collection)
    new_memory_ref = new_memories_ref.document(data['id'])
    new_memory_ref.set(data)
    ##############################


def save_memories(uid: str, data: List[dict]):
    batch = db.batch()
    user_ref = db.collection('users').document(uid)
    memories_ref = user_ref.collection('facts')
    for memory in data:
        memory_ref = memories_ref.document(memory['id'])
        batch.set(memory_ref, memory)
    batch.commit()
    # TODO: remove after migration
    new_memories_ref = user_ref.collection(memories_collection)
    for memory in data:
        memory_ref = new_memories_ref.document(memory['id'])
        batch.set(memory_ref, memory)
    batch.commit()
    ##############################


def delete_memories(uid: str):
    batch = db.batch()
    user_ref = db.collection('users').document(uid)
    memories_ref = user_ref.collection('facts')
    for doc in memories_ref.stream():
        batch.delete(doc.reference)
    batch.commit()
    # TODO: remove after migration
    new_memories_ref = user_ref.collection(memories_collection)
    for doc in new_memories_ref.stream():
        batch.delete(doc.reference)
    batch.commit()
    ##############################


def get_memory(uid: str, memory_id: str):
    user_ref = db.collection('users').document(uid)
    memories_ref = user_ref.collection('facts')
    memory_ref = memories_ref.document(memory_id)
    return memory_ref.get().to_dict()


def review_memory(uid: str, memory_id: str, value: bool):
    user_ref = db.collection('users').document(uid)
    memories_ref = user_ref.collection('facts')
    memory_ref = memories_ref.document(memory_id)
    memory_ref.update({'reviewed': True, 'user_review': value})
    # TODO: remove after migration
    new_memories_ref = user_ref.collection(memories_collection)
    new_memory_ref = new_memories_ref.document(memory_id)
    new_memory_ref.update({'reviewed': True, 'user_review': value})
    ##############################


def change_memory_visibility(uid: str, memory_id: str, value: str):
    user_ref = db.collection('users').document(uid)
    memories_ref = user_ref.collection('facts')
    memory_ref = memories_ref.document(memory_id)
    memory_ref.update({'visibility': value})
    # TODO: remove after migration
    new_memories_ref = user_ref.collection(memories_collection)
    new_memory_ref = new_memories_ref.document(memory_id)
    new_memory_ref.update({'visibility': value})
    ##############################


def edit_memory(uid: str, memory_id: str, value: str):
    user_ref = db.collection('users').document(uid)
    memories_ref = user_ref.collection('facts')
    memory_ref = memories_ref.document(memory_id)
    memory_ref.update({'content': value, 'edited': True, 'updated_at': datetime.now(timezone.utc)})
    # TODO: remove after migration
    new_memories_ref = user_ref.collection(memories_collection)
    new_memory_ref = new_memories_ref.document(memory_id)
    new_memory_ref.update({'content': value, 'edited': True, 'updated_at': datetime.now(timezone.utc)})
    ##############################


def delete_memory(uid: str, memory_id: str):
    user_ref = db.collection('users').document(uid)
    memories_ref = user_ref.collection('facts')
    memory_ref = memories_ref.document(memory_id)
    memory_ref.update({'deleted': True})
    # TODO: remove after migration
    new_memories_ref = user_ref.collection(memories_collection)
    new_memory_ref = new_memories_ref.document(memory_id)
    new_memory_ref.update({'deleted': True})
    ##############################


def delete_all_memories(uid: str):
    user_ref = db.collection('users').document(uid)
    memories_ref = user_ref.collection('facts')
    query = memories_ref.where(filter=FieldFilter('deleted', '==', False))
    batch = db.batch()
    for doc in query.stream():
        batch.update(doc.reference, {'deleted': True})
    batch.commit()
    # TODO: remove after migration
    new_memories_ref = user_ref.collection(memories_collection)
    query = new_memories_ref.where(filter=FieldFilter('deleted', '==', False))
    batch = db.batch()
    for doc in query.stream():
        batch.update(doc.reference, {'deleted': True})
    batch.commit()
    ##############################


def delete_memories_for_conversation(uid: str, memory_id: str):
    batch = db.batch()
    user_ref = db.collection('users').document(uid)
    memories_ref = user_ref.collection('facts')
    query = (
        memories_ref.where(filter=FieldFilter('memory_id', '==', memory_id))
        .where(filter=FieldFilter('deleted', '==', False))
    )

    removed_ids = []
    for doc in query.stream():
        batch.update(doc.reference, {'deleted': True})
        removed_ids.append(doc.id)
    batch.commit()
    print('delete_memories_for_conversation', memory_id, len(removed_ids))


def migrate_memories(prev_uid: str, new_uid: str, app_id: str = None):
    """
    Migrate memories from one user to another.
    If app_id is provided, only migrate memories related to that app.
    """
    print(f'Migrating memories from {prev_uid} to {new_uid}')

    # Get source memories
    prev_user_ref = db.collection('users').document(prev_uid)
    prev_memories_ref = prev_user_ref.collection('facts')

    # Apply app_id filter if provided
    if app_id:
        query = prev_memories_ref.where(filter=FieldFilter('app_id', '==', app_id))
    else:
        query = prev_memories_ref

    # Get memories to migrate
    memories_to_migrate = [doc.to_dict() for doc in query.stream()]

    if not memories_to_migrate:
        print(f'No memories to migrate for user {prev_uid}')
        return 0

    # Create batch for destination user
    batch = db.batch()
    new_user_ref = db.collection('users').document(new_uid)
    new_memories_ref = new_user_ref.collection('facts')

    # Add memories to batch
    for memory in memories_to_migrate:
        memory_ref = new_memories_ref.document(memory['id'])
        batch.set(memory_ref, memory)

    # Commit batch
    batch.commit()
    print(f'Migrated {len(memories_to_migrate)} memories from {prev_uid} to {new_uid}')
    return len(memories_to_migrate)
