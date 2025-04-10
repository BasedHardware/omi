# DEPRECATED: This file has been deprecated long ago
#
# This file is deprecated and should be removed. The code is not used anymore and is not referenced in any other file.
# The only files that references this file are routers/processing_memories.py and utils/processing_conversations.py, which are also deprecated.

from datetime import datetime
from typing import List

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import db


def upsert_processing_conversation(uid: str, processing_conversation_data: dict):
    user_ref = db.collection('users').document(uid)
    processing_conversation_ref = user_ref.collection('processing_memories').document(processing_conversation_data['id'])
    processing_conversation_ref.set(processing_conversation_data)


def update_processing_conversation(uid: str, processing_conversation_id: str, memoy_data: dict):
    user_ref = db.collection('users').document(uid)
    processing_conversation_ref = user_ref.collection('processing_memories').document(processing_conversation_id)
    processing_conversation_ref.update(memoy_data)


def delete_processing_conversation(uid, processing_conversation_id):
    user_ref = db.collection('users').document(uid)
    processing_conversation_ref = user_ref.collection('processing_memories').document(processing_conversation_id)
    processing_conversation_ref.update({'deleted': True})


def get_processing_conversations_by_id(uid, processing_conversation_ids):
    user_ref = db.collection('users').document(uid)
    conversations_ref = user_ref.collection('processing_memories')

    doc_refs = [conversations_ref.document(str(processing_conversation_id)) for processing_conversation_id in processing_conversation_ids]
    docs = db.get_all(doc_refs)

    conversations = []
    for doc in docs:
        if doc.exists:
            conversations.append(doc.to_dict())
    return conversations


def get_processing_conversation_by_id(uid, processing_conversation_id):
    conversation_ref = db.collection('users').document(uid).collection('processing_memories').document(processing_conversation_id)
    return conversation_ref.get().to_dict()


def get_processing_conversations(uid: str, statuses: [str] = [], filter_ids: [str] = [], limit: int = 5):
    processing_conversations_ref = (
        db.collection('users').document(uid).collection('processing_memories')
    )
    if len(statuses) > 0:
        processing_conversations_ref = processing_conversations_ref.where(filter=FieldFilter('status', 'in', statuses))
    if len(filter_ids) > 0:
        processing_conversations_ref = processing_conversations_ref.where(filter=FieldFilter('id', 'in', filter_ids))
    processing_conversations_ref = processing_conversations_ref.order_by('created_at', direction=firestore.Query.DESCENDING)
    processing_conversations_ref = processing_conversations_ref.limit(limit)
    return [doc.to_dict() for doc in processing_conversations_ref.stream()]


def update_processing_conversation_segments(uid: str, id: str, segments: List[dict], capturing_to: datetime):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection('processing_memories').document(id)
    conversation_ref.update({
        'transcript_segments': segments,
        'capturing_to': capturing_to,
    })


def update_processing_conversation_status(uid: str, id: str, status: str):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection('processing_memories').document(id)
    conversation_ref.update({
        'status': status,
    })


def update_audio_url(uid: str, id: str, audio_url: str):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection('processing_memories').document(id)
    conversation_ref.update({
        'audio_url': audio_url,
    })


def get_last(uid: str):
    processing_conversations_ref = (
        db.collection('users').document(uid).collection('processing_memories')
    )
    processing_conversations_ref = processing_conversations_ref.order_by('created_at', direction=firestore.Query.DESCENDING)
    processing_conversations_ref = processing_conversations_ref.limit(1)
    docs = [doc.to_dict() for doc in processing_conversations_ref.stream()]
    if len(docs) > 0:
        return docs[0]
    return None
