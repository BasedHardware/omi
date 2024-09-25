import asyncio
import json
import uuid
from datetime import datetime
from typing import List, Tuple

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter
from google.cloud.firestore_v1.async_client import AsyncClient

import utils.other.hume as hume
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
    # TODO: check utc comparison or not?
    user_ref = db.collection('users').document(uid)
    query = (
        user_ref.collection('memories')
        .where(filter=FieldFilter('created_at', '>=', start_date))
        .where(filter=FieldFilter('created_at', '<=', end_date))
        .where(filter=FieldFilter('deleted', '==', False))
        .where(filter=FieldFilter('discarded', '==', False))
        .order_by('created_at', direction=firestore.Query.DESCENDING)
    )
    return [doc.to_dict() for doc in query.stream()]


# data = [
#     datetime(2024, 8, 18, 0, 0, ),  # tzinfo=TzInfo(UTC)
#     datetime(2024, 8, 24, 23, 59, 59, )  # tzinfo=TzInfo(UTC)
# ]
# result = filter_memories_by_date('viUv7GtdoHXbK1UBCDlPuTDuPgJ2', data[0], data[1])
# print(len(result))


def get_memories_by_id(uid, memory_ids):
    user_ref = db.collection('users').document(uid)
    memories_ref = user_ref.collection('memories')

    doc_refs = [memories_ref.document(str(memory_id)) for memory_id in memory_ids]
    docs = db.get_all(doc_refs)

    memories = []
    for doc in docs:
        if doc.exists:
            data = doc.to_dict()
            if data.get('deleted') or data.get('discarded'):
                continue
            memories.append(data)
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


def get_memory_transcripts_by_model(uid: str, memory_id: str):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('memories').document(memory_id)
    deepgram_ref = memory_ref.collection('deepgram_streaming')
    soniox_ref = memory_ref.collection('soniox_streaming')
    speechmatics_ref = memory_ref.collection('speechmatics_streaming')
    whisperx_ref = memory_ref.collection('fal_whisperx')

    return {
        'deepgram': list(sorted([doc.to_dict() for doc in deepgram_ref.stream()], key=lambda x: x['start'])),
        'soniox': list(sorted([doc.to_dict() for doc in soniox_ref.stream()], key=lambda x: x['start'])),
        'speechmatics': list(sorted([doc.to_dict() for doc in speechmatics_ref.stream()], key=lambda x: x['start'])),
        'whisperx': list(sorted([doc.to_dict() for doc in whisperx_ref.stream()], key=lambda x: x['start'])),
    }


def update_memory_events(uid: str, memory_id: str, events: List[dict]):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('memories').document(memory_id)
    memory_ref.update({'structured.events': events})

def update_memory_finished_at(uid: str, memory_id: str, finished_at: datetime):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('memories').document(memory_id)
    memory_ref.update({'finished_at': finished_at})


# VISBILITY

def set_memory_visibility(uid: str, memory_id: str, visibility: str):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('memories').document(memory_id)
    memory_ref.update({'visibility': visibility})


# claude outputs


async def _get_public_memory(db: AsyncClient, uid: str, memory_id: str):
    memory_ref = db.collection('users').document(uid).collection('memories').document(memory_id)
    memory_doc = await memory_ref.get()
    if memory_doc.exists:
        memory_data = memory_doc.to_dict()
        if memory_data.get('visibility') in ['public'] and not memory_data.get('deleted'):
            return memory_data
    return None


async def _get_public_memories(data: List[Tuple[str, str]]):
    db = AsyncClient()
    tasks = [_get_public_memory(db, uid, memory_id) for uid, memory_id in data]
    memories = await asyncio.gather(*tasks)
    return [memory for memory in memories if memory is not None]


def run_get_public_memories(data: List[Tuple[str, str]]):
    return asyncio.run(_get_public_memories(data))


# POST PROCESSING

def set_postprocessing_status(
        uid: str, memory_id: str, status: PostProcessingStatus, fail_reason: str = None,
        model: PostProcessingModel = PostProcessingModel.fal_whisperx
):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('memories').document(memory_id)
    memory_ref.update({
        'postprocessing.status': status,
        'postprocessing.model': model,
        'postprocessing.fail_reason': fail_reason
    })


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


def update_memory_segments(uid: str, memory_id: str, segments: List[dict]):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('memories').document(memory_id)
    memory_ref.update({'transcript_segments': segments})
    # TODO: update also fal_whisperx? nah..?


def store_model_emotion_predictions_result(
        uid: str, memory_id: str, model_name: str,
        predictions: List[hume.HumeJobModelPredictionResponseModel]
):
    now = datetime.now()
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('memories').document(memory_id)
    predictions_ref = memory_ref.collection(model_name)
    batch = db.batch()
    count = 0
    for prediction in predictions:
        prediction_id = str(uuid.uuid4())
        prediction_ref = predictions_ref.document(prediction_id)
        batch.set(prediction_ref, {
            "created_at": now,
            "start": prediction.time[0],
            "end": prediction.time[1],
            "emotions": json.dumps(hume.HumePredictionEmotionResponseModel.to_multi_dict(prediction.emotions)),
        })
        count = count + 1
        if count >= 100:
            batch.commit()
            batch = db.batch()
            count = 0
    batch.commit()
