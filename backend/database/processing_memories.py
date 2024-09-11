from ._client import db
from google.cloud import firestore
from typing import List


def upsert_processing_memory(uid: str, processing_memory_data: dict):
    user_ref = db.collection('users').document(uid)
    processing_memory_ref = user_ref.collection('processing_memories').document(processing_memory_data['id'])
    processing_memory_ref.set(processing_memory_data)

def update_processing_memory(uid: str, processing_memory_id: str, memoy_data: dict):
    user_ref = db.collection('users').document(uid)
    processing_memory_ref = user_ref.collection('processing_memories').document(processing_memory_id)
    processing_memory_ref.update(memoy_data)


def delete_processing_memory(uid, processing_memory_id):
    user_ref = db.collection('users').document(uid)
    processing_memory_ref = user_ref.collection('processing_memories').document(processing_memory_id)
    processing_memory_ref.update({'deleted': True})

def get_processing_memories_by_id(uid, processing_memory_ids):
    user_ref = db.collection('users').document(uid)
    memories_ref = user_ref.collection('processing_memories')

    doc_refs = [memories_ref.document(str(processing_memory_id)) for processing_memory_id in processing_memory_ids]
    docs = db.get_all(doc_refs)

    memories = []
    for doc in docs:
        if doc.exists:
            memories.append(doc.to_dict())
    return memories

def update_processing_memory_segments(uid: str, id: str, segments: List[dict]):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('processing_memories').document(id)
    memory_ref.update({'transcript_segments': segments})


def get_last(uid: str):
    processing_memories_ref = (
        db.collection('users').document(uid).collection('processing_memories')
    )
    processing_memories_ref = processing_memories_ref.order_by('created_at', direction=firestore.Query.DESCENDING)
    processing_memories_ref = processing_memories_ref.limit(1)
    docs = [doc.to_dict() for doc in processing_memories_ref.stream()]
    if len(docs) > 0:
        return docs[0]
    return None
