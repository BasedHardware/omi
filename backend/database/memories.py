import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter, transactional

from database import memory_ledger
from ._client import db
from database import users as users_db
from models.memories import merge_evidence_sets
from utils import encryption
from .helpers import set_data_protection_level, prepare_for_write, prepare_for_read
import logging

logger = logging.getLogger(__name__)

memories_collection = 'memories'
users_collection = 'users'


def get_memory_ids(uid: str) -> List[str]:
    """Return all memory document IDs for a user without decrypting any fields (IDs-only projection).

    Used for bulk operations like account deletion (e.g. to purge derived Pinecone vectors)."""
    coll = db.collection(users_collection).document(uid).collection(memories_collection)
    return [doc.id for doc in coll.select([]).stream()]


# *********************************
# ******* ENCRYPTION HELPERS ******
# *********************************


def _encrypt_memory_data(memory_data: Dict[str, Any], uid: str) -> Dict[str, Any]:
    data = copy.deepcopy(memory_data)

    if 'content' in data and isinstance(data['content'], str):
        data['content'] = encryption.encrypt(data['content'], uid)
    if 'evidence' in data and isinstance(data['evidence'], list):
        data['evidence'] = encryption.encrypt(json.dumps(data['evidence'], default=str), uid)
    return data


def _decrypt_memory_data(memory_data: Dict[str, Any], uid: str) -> Dict[str, Any]:
    data = copy.deepcopy(memory_data)

    if 'content' in data and isinstance(data['content'], str):
        try:
            data['content'] = encryption.decrypt(data['content'], uid)
        except Exception:
            pass
    if 'evidence' in data and isinstance(data['evidence'], str):
        try:
            decrypted = encryption.decrypt(data['evidence'], uid)
            data['evidence'] = json.loads(decrypted)
        except Exception:
            pass
    return data


def _prepare_data_for_write(data: Dict[str, Any], uid: str, level: str) -> Dict[str, Any]:
    if level == 'enhanced':
        return _encrypt_memory_data(data, uid)
    return data


def _prepare_memory_for_read(memory_data: Optional[Dict[str, Any]], uid: str) -> Optional[Dict[str, Any]]:
    if not memory_data:
        return None

    level = memory_data.get('data_protection_level')
    if level == 'enhanced':
        return _decrypt_memory_data(memory_data, uid)

    return memory_data


# *****************************
# ********** CRUD *************
# *****************************


@prepare_for_read(decrypt_func=_prepare_memory_for_read)
def get_memories(
    uid: str,
    limit: int = 100,
    offset: int = 0,
    categories: List[str] = [],
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    include_invalidated: bool = False,
    sort: str = 'scoring_desc',
):
    logger.info(f'get_memories db {uid} {limit} {offset} {categories} {start_date} {end_date} {sort}')
    memories_ref = db.collection(users_collection).document(uid).collection(memories_collection)

    if categories:
        memories_ref = memories_ref.where(filter=FieldFilter('category', 'in', categories))

    if start_date:
        memories_ref = memories_ref.where(filter=FieldFilter('created_at', '>=', start_date))

    if end_date:
        memories_ref = memories_ref.where(filter=FieldFilter('created_at', '<=', end_date))

    # Keep the Firestore query on the existing indexed order. MCP-specific sort
    # modes are applied after batch collection to avoid requiring extra
    # composite indexes for category-filtered reads.
    memories_ref = memories_ref.order_by('scoring', direction=firestore.Query.DESCENDING).order_by(
        'created_at', direction=firestore.Query.DESCENDING
    )

    memories_ref = memories_ref.limit(limit).offset(offset)

    # TODO: put user review to firestore query
    memories = [doc.to_dict() for doc in memories_ref.stream()]
    logger.info(f"get_memories {len(memories)}")
    # Exclude user-rejected memories, and (by default) superseded/retracted ones.
    # invalid_at is filtered in Python: old docs lack the field (-> None -> active),
    # which a Firestore `== None` filter would wrongly drop.
    result = [
        memory
        for memory in memories
        if memory.get('user_review') is not False and (include_invalidated or memory.get('invalid_at') is None)
    ]
    return result


@prepare_for_read(decrypt_func=_prepare_memory_for_read)
def get_user_public_memories(uid: str, limit: int = 100, offset: int = 0):
    logger.info(f'get_public_memories {limit} {offset}')

    memories_ref = db.collection(users_collection).document(uid).collection(memories_collection)
    memories_ref = memories_ref.order_by('scoring', direction=firestore.Query.DESCENDING).order_by(
        'created_at', direction=firestore.Query.DESCENDING
    )

    memories_ref = memories_ref.limit(limit).offset(offset)

    memories = [doc.to_dict() for doc in memories_ref.stream()]

    # Consider visibility as 'public' if it's missing
    public_memories = [memory for memory in memories if memory.get('visibility', 'public') == 'public']

    return public_memories


@prepare_for_read(decrypt_func=_prepare_memory_for_read)
def get_non_filtered_memories(uid: str, limit: int = 100, offset: int = 0):
    logger.info(f'get_non_filtered_memories {uid} {limit} {offset}')
    memories_ref = db.collection(users_collection).document(uid).collection(memories_collection)
    memories_ref = memories_ref.order_by('created_at', direction=firestore.Query.DESCENDING)
    memories_ref = memories_ref.limit(limit).offset(offset)
    memories = [doc.to_dict() for doc in memories_ref.stream()]
    return memories


@set_data_protection_level(data_arg_name='data')
@prepare_for_write(data_arg_name='data', prepare_func=_prepare_data_for_write)
def create_memory(uid: str, data: dict):
    user_ref = db.collection(users_collection).document(uid)
    memories_ref = user_ref.collection(memories_collection)
    memory_ref = memories_ref.document(data['id'])

    def build_commit(transaction):
        snapshot = memory_ref.get(transaction=transaction)
        existing_data = snapshot.to_dict() if snapshot.exists else None
        merged_data = _merge_memory_for_write(uid, existing_data, data)

        def write_projection(write_transaction):
            write_transaction.set(memory_ref, merged_data)

        return {'mutations': [memory_ledger.add_fact(merged_data)], 'projection_writer': write_projection}

    return memory_ledger.append_commit_with_builder(uid, None, build_commit, use_current_head=True)


@set_data_protection_level(data_arg_name='data')
@prepare_for_write(data_arg_name='data', prepare_func=_prepare_data_for_write)
def save_memories(uid: str, data: List[dict]):
    if not data:
        return

    user_ref = db.collection(users_collection).document(uid)
    memories_ref = user_ref.collection(memories_collection)
    coalesced_data = _coalesce_memory_writes(uid, data)
    refs_and_data = [(memories_ref.document(memory['id']), memory) for memory in coalesced_data]

    def build_commit(transaction):
        snapshots = []
        for memory_ref, _ in refs_and_data:
            snapshots.append(memory_ref.get(transaction=transaction))

        merged_data = []
        for (memory_ref, memory), snapshot in zip(refs_and_data, snapshots):
            existing_data = snapshot.to_dict() if snapshot.exists else None
            merged_data.append((memory_ref, _merge_memory_for_write(uid, existing_data, memory)))

        def write_projection(write_transaction):
            for memory_ref, memory in merged_data:
                write_transaction.set(memory_ref, memory)

        return {
            'mutations': [memory_ledger.add_fact(memory) for _, memory in merged_data],
            'projection_writer': write_projection,
        }

    return memory_ledger.append_commit_with_builder(uid, None, build_commit, use_current_head=True)


@transactional
def _set_memory_transaction(transaction, uid: str, memory_ref, memory: dict):
    snapshot = memory_ref.get(transaction=transaction)
    existing_data = snapshot.to_dict() if snapshot.exists else None
    transaction.set(memory_ref, _merge_memory_for_write(uid, existing_data, memory))


@transactional
def _set_memories_transaction(transaction, uid: str, refs_and_data: List[tuple]):
    snapshots = []
    for memory_ref, _ in refs_and_data:
        snapshots.append(memory_ref.get(transaction=transaction))

    for (memory_ref, memory), snapshot in zip(refs_and_data, snapshots):
        existing_data = snapshot.to_dict() if snapshot.exists else None
        transaction.set(memory_ref, _merge_memory_for_write(uid, existing_data, memory))


def _merge_memory_for_write(uid: str, existing_data: Optional[dict], incoming_data: dict) -> dict:
    """Merge additive provenance when a deterministic memory id already exists."""
    if not existing_data:
        return incoming_data

    incoming_plain = _prepare_memory_for_read(incoming_data, uid) or incoming_data
    existing_plain = _prepare_memory_for_read(existing_data, uid) or existing_data
    existing_evidence = existing_plain.get('evidence') or []
    incoming_evidence = incoming_plain.get('evidence') or []
    if not incoming_evidence:
        return incoming_data

    merged_plain = {**existing_plain, **incoming_plain}
    merged_plain['created_at'] = existing_plain.get('created_at', incoming_plain.get('created_at'))
    merged_plain['evidence'] = merge_evidence_sets(existing_evidence, incoming_evidence)
    return _prepare_data_for_write(merged_plain, uid, merged_plain.get('data_protection_level', 'standard'))


def _coalesce_memory_writes(uid: str, memories: List[dict]) -> List[dict]:
    merged_by_id = {}
    order = []
    for memory in memories:
        memory_id = memory['id']
        if memory_id not in merged_by_id:
            merged_by_id[memory_id] = memory
            order.append(memory_id)
            continue
        merged_by_id[memory_id] = _merge_memory_for_write(uid, merged_by_id[memory_id], memory)
    return [merged_by_id[memory_id] for memory_id in order]


def _merge_evidence(existing: List[dict], incoming: List[dict]) -> List[dict]:
    return merge_evidence_sets(existing, incoming)


def delete_memories(uid: str):
    batch = db.batch()
    user_ref = db.collection(users_collection).document(uid)
    memories_ref = user_ref.collection(memories_collection)
    for doc in memories_ref.stream():
        batch.delete(doc.reference)
    batch.commit()


@prepare_for_read(decrypt_func=_prepare_memory_for_read)
def get_memory(uid: str, memory_id: str):
    user_ref = db.collection(users_collection).document(uid)
    memories_ref = user_ref.collection(memories_collection)
    memory_ref = memories_ref.document(memory_id)
    memory_data = memory_ref.get().to_dict()
    return memory_data


def get_memories_by_ids(uid: str, memory_ids: List[str]) -> List[dict]:
    """
    Batch fetch multiple memories by their IDs.
    Uses Firestore's get_all for efficient batch retrieval.
    """
    if not memory_ids:
        return []

    user_ref = db.collection(users_collection).document(uid)
    memories_ref = user_ref.collection(memories_collection)

    doc_refs = [memories_ref.document(memory_id) for memory_id in memory_ids]
    docs = db.get_all(doc_refs)

    memories = []
    for doc in docs:
        if doc.exists:
            memory_data = doc.to_dict()
            # Apply decryption if needed
            memory_data = _prepare_memory_for_read(memory_data, uid)
            if memory_data:
                memories.append(memory_data)

    return memories


def review_memory(uid: str, memory_id: str, value: bool):
    user_ref = db.collection(users_collection).document(uid)
    memories_ref = user_ref.collection(memories_collection)
    memory_ref = memories_ref.document(memory_id)
    memory_ref.update({'reviewed': True, 'user_review': value})


def set_memory_kg_extracted(uid: str, memory_id: str):
    user_ref = db.collection(users_collection).document(uid)
    memories_ref = user_ref.collection(memories_collection)
    memory_ref = memories_ref.document(memory_id)
    memory_ref.update({'kg_extracted': True})


def change_memory_visibility(uid: str, memory_id: str, value: str):
    user_ref = db.collection(users_collection).document(uid)
    memories_ref = user_ref.collection(memories_collection)
    memory_ref = memories_ref.document(memory_id)
    memory_ref.update({'visibility': value})


def update_memory_fields(uid: str, memory_id: str, data: dict):
    """Updates specified fields for a memory and sets the updated_at timestamp."""
    if not data:
        return

    user_ref = db.collection(users_collection).document(uid)
    memories_ref = user_ref.collection(memories_collection)
    memory_ref = memories_ref.document(memory_id)

    update_payload = data.copy()
    update_payload['updated_at'] = datetime.now(timezone.utc)
    memory_ref.update(update_payload)


def add_evidence(uid: str, memory_id: str, evidence: dict):
    """Append one provenance Evidence row to a memory if it is not already present."""
    user_ref = db.collection(users_collection).document(uid)
    memories_ref = user_ref.collection(memories_collection)
    memory_ref = memories_ref.document(memory_id)

    doc_snapshot = memory_ref.get()
    if not doc_snapshot.exists:
        return

    memory_data = _prepare_memory_for_read(doc_snapshot.to_dict(), uid) or {}
    existing = memory_data.get('evidence') or []
    evidence_id = evidence.get('evidence_id')
    if evidence_id and any(item.get('evidence_id') == evidence_id for item in existing if isinstance(item, dict)):
        return

    updated_evidence = existing + [evidence]
    update_payload = {'evidence': updated_evidence, 'updated_at': datetime.now(timezone.utc)}
    doc_level = memory_data.get('data_protection_level', 'standard')
    if doc_level == 'enhanced':
        update_payload = _encrypt_memory_data(update_payload, uid)
    memory_ref.update(update_payload)


def recompute_evidence(uid: str, memory_id: str):
    """Placeholder hook for later veracity/tombstone recomputation tickets."""
    memory = get_memory(uid, memory_id)
    return (memory or {}).get('evidence', [])


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

    update_time = datetime.now(timezone.utc)
    value_for_commit = content if doc_level == 'enhanced' else value
    content_change = {'to': value_for_commit}
    if doc_level == 'enhanced':
        content_change['to_sha256'] = hashlib.sha256(value.encode('utf-8')).hexdigest()

    def write_projection(transaction):
        snapshot = memory_ref.get(transaction=transaction)
        if not snapshot.exists:
            return
        transaction.update(memory_ref, {'content': content, 'edited': True, 'updated_at': update_time})

    return memory_ledger.append_commit(
        uid,
        None,
        [memory_ledger.refine_fact(memory_id, {'content': content_change, 'edited': {'to': True}})],
        commit_time=update_time,
        projection_writer=write_projection,
        use_current_head=True,
    )


def invalidate_memory(
    uid: str, memory_id: str, superseded_by: Optional[str] = None, invalid_at: Optional[datetime] = None
):
    """Soft-invalidate a memory that has been superseded or retracted.

    Unlike delete_memory this keeps the document (history) but stamps invalid_at so
    every retrieval path excludes it — the "constantly updated brain" stops surfacing
    a fact the moment it stops being true. Callers should also drop the Pinecone vector
    so the memory disappears from semantic search too.
    """
    if invalid_at is None:
        invalid_at = datetime.now(timezone.utc)
    user_ref = db.collection(users_collection).document(uid)
    memories_ref = user_ref.collection(memories_collection)
    memory_ref = memories_ref.document(memory_id)
    update_payload = {'invalid_at': invalid_at, 'updated_at': datetime.now(timezone.utc)}
    if superseded_by is not None:
        update_payload['superseded_by'] = superseded_by

    if superseded_by is not None:
        ledger_mutation = memory_ledger.supersede_fact(
            memory_id,
            by=superseded_by,
            kind='contradict',
            valid_interval={'valid_to': invalid_at},
        )
    else:
        ledger_mutation = memory_ledger.retract_fact(memory_id, reason='invalidated')

    def write_projection(transaction):
        transaction.update(memory_ref, update_payload)

    return memory_ledger.append_commit(
        uid,
        None,
        [ledger_mutation],
        commit_time=invalid_at,
        projection_writer=write_projection,
        use_current_head=True,
    )


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


def get_memory_ids_for_conversation(uid: str, conversation_id: str) -> List[str]:
    """Get all memory IDs associated with a conversation."""
    user_ref = db.collection(users_collection).document(uid)
    memories_ref = user_ref.collection(memories_collection)
    query = memories_ref.where(filter=FieldFilter('memory_id', '==', conversation_id))

    memory_ids = [doc.id for doc in query.stream()]
    return memory_ids


def delete_memories_for_conversation(uid: str, memory_id: str):
    batch = db.batch()
    user_ref = db.collection(users_collection).document(uid)
    memories_ref = user_ref.collection(memories_collection)
    query = memories_ref.where(filter=FieldFilter('memory_id', '==', memory_id))

    removed_ids = []
    for doc in query.stream():
        batch.delete(doc.reference)
        removed_ids.append(doc.id)
    batch.commit()
    logger.info(f'delete_memories_for_conversation {memory_id} {len(removed_ids)}')


def unlock_all_memories(uid: str):
    """
    Finds all memories for a user with is_locked: True and updates them to is_locked = False.
    """
    memories_ref = db.collection(users_collection).document(uid).collection(memories_collection)
    locked_memories_query = memories_ref.where(filter=FieldFilter('is_locked', '==', True))

    batch = db.batch()
    docs = locked_memories_query.stream()
    count = 0
    for doc in docs:
        batch.update(doc.reference, {'is_locked': False})
        count += 1
        if count >= 499:  # Firestore batch limit is 500
            batch.commit()
            batch = db.batch()
            count = 0
    if count > 0:
        batch.commit()
    logger.info(f"Unlocked all memories for user {uid}")


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


def migrate_memories_level_batch(uid: str, memory_ids: List[str], target_level: str):
    """
    Migrates a batch of memories to the target protection level.
    """
    batch = db.batch()
    memories_ref = db.collection(users_collection).document(uid).collection(memories_collection)
    doc_refs = [memories_ref.document(mem_id) for mem_id in memory_ids]
    doc_snapshots = db.get_all(doc_refs)

    for doc_snapshot in doc_snapshots:
        if not doc_snapshot.exists:
            logger.warning(f"Memory {doc_snapshot.id} not found, skipping.")
            continue

        memory_data = doc_snapshot.to_dict()
        current_level = memory_data.get('data_protection_level', 'standard')

        if current_level == target_level:
            continue

        # Decrypt the data first (if needed) to get a clean slate.
        plain_data = _prepare_memory_for_read(memory_data, uid)

        plain_content = plain_data.get('content')
        migrated_content = plain_content
        if target_level == 'enhanced':
            if isinstance(plain_content, str):
                migrated_content = encryption.encrypt(plain_content, uid)

        # Update the document with the migrated data and the new protection level.
        update_data = {'data_protection_level': target_level, 'content': migrated_content}
        batch.update(doc_snapshot.reference, update_data)

    batch.commit()


def migrate_memories(prev_uid: str, new_uid: str, app_id: str = None):
    """
    Migrate memories from one user to another.
    If app_id is provided, only migrate memories related to that app.
    """
    logger.info(f'Migrating memories from {prev_uid} to {new_uid}')

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
        logger.info(f'No memories to migrate for user {prev_uid}')
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
    logger.info(f'Migrated {len(memories_to_migrate)} memories from {prev_uid} to {new_uid}')
    return len(memories_to_migrate)
