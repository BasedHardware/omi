import uuid
from typing import List

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from models.memory import MemoryPhoto, PostProcessingStatus, PostProcessingModel
from models.transcript_segment import TranscriptSegment
from ._client import db


def upsert_memory(uid: str, memory_data: dict):
    if 'audio_base64_url' in memory_data:
        del memory_data['audio_base64_url']
    if 'photos' in memory_data:
        del memory_data['photos']

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


def get_memories_by_id(uid, memory_ids):
    user_ref = db.collection('users').document(uid)
    memories_ref = user_ref.collection('memories')

    doc_refs = [memories_ref.document(str(memory_id)) for memory_id in memory_ids]
    docs = db.get_all(doc_refs)

    memories = []
    for doc in docs:
        if doc.exists:
            memories.append(doc.to_dict())
    return memories


# Open Glass

def store_memory_photos(uid: str, memory_id: str, photos: List[MemoryPhoto]):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('memories').document(memory_id)
    photos_ref = memory_ref.collection('photos')
    batch = db.batch()
    for photo in photos:
        photo_id = str(uuid.uuid4())
        photo_ref = photos_ref.document(str(uuid.uuid4()))
        data = photo.dict()
        data['id'] = photo_id
        batch.set(photo_ref, data)
    batch.commit()


def get_memory_photos(uid: str, memory_id: str):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('memories').document(memory_id)
    photos_ref = memory_ref.collection('photos')
    return [doc.to_dict() for doc in photos_ref.stream()]


# POST PROCESSING

def set_postprocessing_status(
        uid: str, memory_id: str, status: PostProcessingStatus,
        model: PostProcessingModel = PostProcessingModel.fal_whisperx
):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('memories').document(memory_id)
    memory_ref.update({'postprocessing.status': status, 'postprocessing.model': model})


def store_model_segments_result(uid: str, memory_id: str, model_name: str, segments: List[TranscriptSegment]):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('memories').document(memory_id)
    segments_ref = memory_ref.collection(model_name)
    batch = db.batch()
    for i, segment in enumerate(segments):
        segment_id = str(uuid.uuid4())
        segment_ref = segments_ref.document(segment_id)
        batch.set(segment_ref, segment.dict())
        if i >= 400:
            batch.commit()
            batch = db.batch()
    batch.commit()
