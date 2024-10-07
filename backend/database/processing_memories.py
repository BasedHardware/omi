from datetime import datetime
from typing import List

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import db


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


def get_processing_memory_by_id(uid, processing_memory_id):
    memory_ref = db.collection('users').document(uid).collection('processing_memories').document(processing_memory_id)
    return memory_ref.get().to_dict()


def get_processing_memories(uid: str, statuses: [str] = [], filter_ids: [str] = [], limit: int = 5):
    processing_memories_ref = (
        db.collection('users').document(uid).collection('processing_memories')
    )
    if len(statuses) > 0:
        processing_memories_ref = processing_memories_ref.where(filter=FieldFilter('status', 'in', statuses))
    if len(filter_ids) > 0:
        processing_memories_ref = processing_memories_ref.where(filter=FieldFilter('id', 'in', filter_ids))
    processing_memories_ref = processing_memories_ref.order_by('created_at', direction=firestore.Query.DESCENDING)
    processing_memories_ref = processing_memories_ref.limit(limit)
    return [doc.to_dict() for doc in processing_memories_ref.stream()]


def update_processing_memory_segments(uid: str, id: str, segments: List[dict], capturing_to: datetime):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('processing_memories').document(id)
    memory_ref.update({
        'transcript_segments': segments,
        'capturing_to': capturing_to,
    })


def update_processing_memory_status(uid: str, id: str, status: str):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('processing_memories').document(id)
    memory_ref.update({
        'status': status,
    })


def update_audio_url(uid: str, id: str, audio_url: str):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('processing_memories').document(id)
    memory_ref.update({
        'audio_url': audio_url,
    })


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
