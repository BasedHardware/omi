import copy
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import db
from database import users as users_db
from utils import encryption

memories_collection = 'memories'
users_collection = 'users'


# *********************************
# ******* ENCRYPTION HELPERS ******
# *********************************

def _encrypt_memory_data(memory_data: Dict[str, Any], uid: str) -> Dict[str, Any]:
    """
    Encrypts sensitive fields in a memory dictionary.
    Operates on a copy of the data to avoid side effects.
    """
    data = copy.deepcopy(memory_data)
    if 'content' in data and isinstance(data['content'], str):
        data['content'] = encryption.encrypt(data['content'], uid)
    return data


def _decrypt_memory_data(memory_data: Dict[str, Any], uid: str) -> Dict[str, Any]:
    """
    Decrypts sensitive fields in a memory dictionary.
    Operates on a copy of the data to avoid side effects.
    """
    data = copy.deepcopy(memory_data)
    if 'content' in data and isinstance(data['content'], str):
        try:
            data['content'] = encryption.decrypt(data['content'], uid)
        except Exception:
            pass  # Ignore decryption errors
    return data


def _prepare_data_for_write(data: Dict[str, Any], uid: str, level: str) -> Dict[str, Any]:
    """
    Prepares data for writing to Firestore by encrypting it if the protection level is 'enhanced'.
    For 'standard' and 'e2ee', data is returned as is.
    """
    if level == 'enhanced':
        return _encrypt_memory_data(data, uid)
    return data


def _prepare_memory_for_read(memory_data: Optional[Dict[str, Any]], uid: str) -> Optional[Dict[str, Any]]:
    """
    Prepares a memory document for reading by decrypting it based on its protection level.
    For 'standard' and 'e2ee', data is returned as is.
    """
    if not memory_data:
        return None

    level = memory_data.get('data_protection_level')
    if level == 'enhanced':
        return _decrypt_memory_data(memory_data, uid)

    return memory_data


# *****************************
# ********** CRUD *************
# *****************************

def get_memories(uid: str, limit: int = 100, offset: int = 0, categories: List[str] = []):
    print('get_memories db', uid, limit, offset, categories)
    memories_ref = db.collection(users_collection).document(uid).collection(memories_collection)
    if categories:
        memories_ref = memories_ref.where(filter=FieldFilter('category', 'in', categories))

    memories_ref = (
        memories_ref
        .order_by('scoring', direction=firestore.Query.DESCENDING)
        .order_by('created_at', direction=firestore.Query.DESCENDING)
        .limit(limit)
        .offset(offset)
    )

    # TODO: put user review to firestore query
    memories = [doc.to_dict() for doc in memories_ref.stream()]
    print("get_memories", len(memories))
    result = [memory for memory in memories if memory['user_review'] is not False]
    return [_prepare_memory_for_read(mem, uid) for mem in result]


def get_user_public_memories(uid: str, limit: int = 100, offset: int = 0):
    print('get_public_memories', limit, offset)

    memories_ref = db.collection(users_collection).document(uid).collection(memories_collection)
    memories_ref = (
        memories_ref.order_by('scoring', direction=firestore.Query.DESCENDING)
        .order_by('created_at', direction=firestore.Query.DESCENDING)
    )

    memories_ref = memories_ref.limit(limit).offset(offset)

    memories = [doc.to_dict() for doc in memories_ref.stream()]

    # Consider visibility as 'public' if it's missing
    public_memories = [memory for memory in memories if memory.get('visibility', 'public') == 'public']

    return [_prepare_memory_for_read(mem, uid) for mem in public_memories]


def get_non_filtered_memories(uid: str, limit: int = 100, offset: int = 0):
    print('get_non_filtered_memories', uid, limit, offset)
    memories_ref = db.collection(users_collection).document(uid).collection(memories_collection)
    memories_ref = (
        memories_ref.order_by('created_at', direction=firestore.Query.DESCENDING)
    )
    memories_ref = memories_ref.limit(limit).offset(offset)
    memories = [doc.to_dict() for doc in memories_ref.stream()]
    return [_prepare_memory_for_read(mem, uid) for mem in memories]


def create_memory(uid: str, data: dict):
    current_level = users_db.get_data_protection_level(uid)
    data['data_protection_level'] = current_level
    prepared_data = _prepare_data_for_write(data, uid, current_level)

    user_ref = db.collection(users_collection).document(uid)
    memories_ref = user_ref.collection(memories_collection)
    memory_ref = memories_ref.document(prepared_data['id'])
    memory_ref.set(prepared_data)


def save_memories(uid: str, data: List[dict]):
    current_level = users_db.get_data_protection_level(uid)
    batch = db.batch()
    user_ref = db.collection(users_collection).document(uid)
    memories_ref = user_ref.collection(memories_collection)
    for memory in data:
        memory['data_protection_level'] = current_level
        prepared_data = _prepare_data_for_write(memory, uid, current_level)
        memory_ref = memories_ref.document(prepared_data['id'])
        batch.set(memory_ref, prepared_data)
    batch.commit()


def delete_memories(uid: str):
    batch = db.batch()
    user_ref = db.collection(users_collection).document(uid)
    memories_ref = user_ref.collection(memories_collection)
    for doc in memories_ref.stream():
        batch.delete(doc.reference)
    batch.commit()


def get_memory(uid: str, memory_id: str):
    user_ref = db.collection(users_collection).document(uid)
    memories_ref = user_ref.collection(memories_collection)
    memory_ref = memories_ref.document(memory_id)
    memory_data = memory_ref.get().to_dict()
    return _prepare_memory_for_read(memory_data, uid)


def review_memory(uid: str, memory_id: str, value: bool):
    user_ref = db.collection(users_collection).document(uid)
    memories_ref = user_ref.collection(memories_collection)
    memory_ref = memories_ref.document(memory_id)
    memory_ref.update({'reviewed': True, 'user_review': value})


def change_memory_visibility(uid: str, memory_id: str, value: str):
    user_ref = db.collection(users_collection).document(uid)
    memories_ref = user_ref.collection(memories_collection)
    memory_ref = memories_ref.document(memory_id)
    memory_ref.update({'visibility': value})


def edit_memory(uid: str, memory_id: str, value: str):
    user_ref = db.collection(users_collection).document(uid)
    memories_ref = user_ref.collection(memories_collection)
    memory_ref = memories_ref.document(memory_id)

    doc_snapshot = memory_ref.get()
    if not doc_snapshot.exists:
        return

    doc_level = doc_snapshot.to_dict().get('data_protection_level', 'standard')
    content = value
    if doc_level == 'enhanced':
        content = encryption.encrypt(content, uid)

    memory_ref.update({'content': content, 'edited': True, 'updated_at': datetime.now(timezone.utc)})


def delete_memory(uid: str, memory_id: str):
    user_ref = db.collection(users_collection).document(uid)
    memories_ref = user_ref.collection(memories_collection)
    memory_ref = memories_ref.document(memory_id)
    memory_ref.delete()


def delete_all_memories(uid: str):
    user_ref = db.collection(users_collection).document(uid)
    memories_ref = user_ref.collection(memories_collection)
    batch = db.batch()
    for doc in memories_ref.stream():
        batch.delete(doc.reference)
    batch.commit()


def delete_memories_for_conversation(uid: str, memory_id: str):
    batch = db.batch()
    user_ref = db.collection(users_collection).document(uid)
    memories_ref = user_ref.collection(memories_collection)
    query = (
        memories_ref.where(filter=FieldFilter('memory_id', '==', memory_id))
    )

    removed_ids = []
    for doc in query.stream():
        batch.delete(doc.reference)
        removed_ids.append(doc.id)
    batch.commit()
    print('delete_memories_for_conversation', memory_id, len(removed_ids))


# **************************************
# ********* MIGRATION HELPERS **********
# **************************************

def get_memories_to_migrate(uid: str, target_level: str) -> List[dict]:
    """
    Finds all memories that are not at the target protection level by fetching all documents
    and filtering them in memory. This simplifies the code but may be less performant for
    users with a very large number of documents.
    """
    memories_ref = db.collection(users_collection).document(uid).collection(memories_collection)
    all_memories = memories_ref.select(['data_protection_level']).stream()

    to_migrate = []
    for doc in all_memories:
        doc_data = doc.to_dict()
        current_level = doc_data.get('data_protection_level', 'standard')
        if target_level != current_level:
            to_migrate.append({'id': doc.id, 'type': 'memory'})

    return to_migrate


def migrate_memory_level(uid: str, memory_id: str, target_level: str):
    """
    Migrates a single memory to the target protection level.
    """
    doc_ref = db.collection(users_collection).document(uid).collection(memories_collection).document(memory_id)
    doc_snapshot = doc_ref.get()
    if not doc_snapshot.exists:
        raise ValueError("Memory not found")

    memory_data = doc_snapshot.to_dict()
    current_level = memory_data.get('data_protection_level', 'standard')

    if current_level == target_level:
        return  # Nothing to do

    # Decrypt the data first (if needed) to get a clean slate.
    plain_data = _prepare_memory_for_read(memory_data, uid)

    # Now, encrypt if the target is 'enhanced'.
    migrated_data = _prepare_data_for_write(plain_data, uid, target_level)

    # Update the document with the migrated data and the new protection level.
    migrated_data['data_protection_level'] = target_level
    doc_ref.update(migrated_data)


def migrate_memories(prev_uid: str, new_uid: str, app_id: str = None):
    """
    Migrate memories from one user to another.
    If app_id is provided, only migrate memories related to that app.
    """
    print(f'Migrating memories from {prev_uid} to {new_uid}')

    # Get source memories
    prev_user_ref = db.collection(users_collection).document(prev_uid)
    prev_memories_ref = prev_user_ref.collection(memories_collection)

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
    new_user_ref = db.collection(users_collection).document(new_uid)
    new_memories_ref = new_user_ref.collection(memories_collection)

    # Add memories to batch
    for memory in memories_to_migrate:
        memory_ref = new_memories_ref.document(memory['id'])
        batch.set(memory_ref, memory)

    # Commit batch
    batch.commit()
    print(f'Migrated {len(memories_to_migrate)} memories from {prev_uid} to {new_uid}')
    return len(memories_to_migrate)
