from datetime import datetime
from typing import List, Optional
import uuid

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import get_firestore


def upsert_processing_memory(uid: str, processing_memory_data: dict):
    user_ref = get_firestore().collection('users').document(uid)
    processing_memory_ref = user_ref.collection('processing_memories').document(processing_memory_data['id'])
    processing_memory_ref.set(processing_memory_data)

def update_processing_memory(memory_id: str, memory_data: dict):
    """Update processing memory document"""
    db = get_firestore()
    memories = db.collection_group('processing_memories').where(
        filter=FieldFilter('id', '==', memory_id)
    ).limit(1).stream()
    docs = list(memories)
    if docs:
        docs[0].reference.update(memory_data)


def delete_processing_memory(memory_id: str):
    """Delete processing memory document"""
    db = get_firestore()
    memories = db.collection_group('processing_memories').where(
        filter=FieldFilter('id', '==', memory_id)
    ).limit(1).stream()
    docs = list(memories)
    if docs:
        docs[0].reference.update({'deleted': True})


def create_processing_memory(memory_data: dict) -> str:
    """Create a new processing memory document"""
    if 'id' not in memory_data:
        memory_data['id'] = str(uuid.uuid4())
        
    db = get_firestore()
    user_ref = db.collection('users').document(memory_data['user_id'])
    doc_ref = user_ref.collection('processing_memories').document(memory_data['id'])
    doc_ref.set(memory_data)
    return memory_data['id']


def get_processing_memory(memory_id: str) -> Optional[dict]:
    """Get processing memory by ID"""
    db = get_firestore()
    memories = db.collection_group('processing_memories').where(
        filter=FieldFilter('id', '==', memory_id)
    ).limit(1).stream()
    docs = list(memories)
    if not docs:
        return None
    return docs[0].to_dict()


def get_processing_memories_by_state(user_id: str, state: str) -> List[dict]:
    """Get processing memories by state"""
    db = get_firestore()
    memories_ref = (
        db.collection('users').document(user_id)
        .collection('processing_memories')
        .where(filter=FieldFilter('state', '==', state))
    )
    return [doc.to_dict() for doc in memories_ref.stream()]


def get_processing_memories_by_id(uid: str, processing_memory_ids: List[str]) -> List[dict]:
    """Get processing memories by IDs"""
    user_ref = get_firestore().collection('users').document(uid)
    memories_ref = user_ref.collection('processing_memories')

    doc_refs = [memories_ref.document(str(memory_id)) for memory_id in processing_memory_ids]
    docs = get_firestore().get_all(doc_refs)

    memories = []
    for doc in docs:
        if doc.exists:
            memories.append(doc.to_dict())
    return memories


def get_processing_memory_by_id(uid: str, processing_memory_id: str) -> Optional[dict]:
    """Get processing memory by ID"""
    memory_ref = get_firestore().collection('users').document(uid).collection('processing_memories').document(processing_memory_id)
    return memory_ref.get().to_dict()


def get_processing_memories(uid: str, statuses: List[str] = None, filter_ids: List[str] = None, limit: int = 5) -> List[dict]:
    """Get processing memories with filters"""
    statuses = statuses or []
    filter_ids = filter_ids or []
    
    processing_memories_ref = (
        get_firestore().collection('users').document(uid).collection('processing_memories')
    )
    
    if statuses:
        processing_memories_ref = processing_memories_ref.where(filter=FieldFilter('status', 'in', statuses))
    if filter_ids:
        processing_memories_ref = processing_memories_ref.where(filter=FieldFilter('id', 'in', filter_ids))
        
    processing_memories_ref = processing_memories_ref.order_by('created_at', direction=firestore.Query.DESCENDING)
    processing_memories_ref = processing_memories_ref.limit(limit)
    
    return [doc.to_dict() for doc in processing_memories_ref.stream()]


def update_processing_memory_segments(uid: str, id: str, segments: List[dict], capturing_to: datetime):
    """Update processing memory segments"""
    user_ref = get_firestore().collection('users').document(uid)
    memory_ref = user_ref.collection('processing_memories').document(id)
    memory_ref.update({
        'transcript_segments': segments,
        'capturing_to': capturing_to,
    })


def update_processing_memory_status(uid: str, id: str, status: str):
    """Update processing memory status"""
    user_ref = get_firestore().collection('users').document(uid)
    memory_ref = user_ref.collection('processing_memories').document(id)
    memory_ref.update({
        'status': status,
    })


def update_audio_url(uid: str, id: str, audio_url: str):
    """Update processing memory audio URL"""
    user_ref = get_firestore().collection('users').document(uid)
    memory_ref = user_ref.collection('processing_memories').document(id)
    memory_ref.update({
        'audio_url': audio_url,
    })


def get_last(uid: str) -> Optional[dict]:
    """Get last processing memory"""
    processing_memories_ref = (
        get_firestore().collection('users').document(uid).collection('processing_memories')
        .order_by('created_at', direction=firestore.Query.DESCENDING)
        .limit(1)
    )
    docs = [doc.to_dict() for doc in processing_memories_ref.stream()]
    return docs[0] if docs else None


__all__ = [
    'create_processing_memory',
    'get_processing_memory',
    'update_processing_memory',
    'delete_processing_memory',
    'get_processing_memories_by_state',
    'get_processing_memories_by_id',
    'get_processing_memory_by_id',
    'get_processing_memories',
    'update_processing_memory_segments',
    'update_processing_memory_status',
    'update_audio_url',
    'get_last'
]
