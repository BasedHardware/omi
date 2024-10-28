import asyncio
import json
import uuid
from datetime import datetime, timedelta
from typing import List, Tuple, Optional

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter
from google.cloud.firestore_v1.async_client import AsyncClient

import utils.other.hume as hume
from models.memory import MemoryPhoto, PostProcessingStatus, PostProcessingModel
from models.transcript_segment import TranscriptSegment
from ._client import db


# *****************************
# ********** CRUD *************
# *****************************

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


def get_memories(uid: str, limit: int = 100, offset: int = 0, include_discarded: bool = False,
                 statuses: List[str] = []):
    memories_ref = (
        db.collection('users').document(uid).collection('memories')
        .where(filter=FieldFilter('deleted', '==', False))
    )
    if not include_discarded:
        memories_ref = memories_ref.where(filter=FieldFilter('discarded', '==', False))
    if len(statuses) > 0:
        memories_ref = memories_ref.where(filter=FieldFilter('status', 'in', statuses))
    memories_ref = memories_ref.order_by('created_at', direction=firestore.Query.DESCENDING)
    memories_ref = memories_ref.limit(limit).offset(offset)
    return [doc.to_dict() for doc in memories_ref.stream()]


def update_memory(uid: str, memory_id: str, memoy_data: dict):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('memories').document(memory_id)
    memory_ref.update(memoy_data)


def update_memory_title(uid: str, memory_id: str, title: str):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('memories').document(memory_id)
    memory_ref.update({'structured.title': title})


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
        .where(filter=FieldFilter('deleted', '==', False))
        .where(filter=FieldFilter('discarded', '==', False))
        .order_by('created_at', direction=firestore.Query.DESCENDING)
    )
    return [doc.to_dict() for doc in query.stream()]


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


# **************************************
# ********** STATUS *************
# **************************************

def get_in_progress_memory(uid: str):
    user_ref = db.collection('users').document(uid)
    memories_ref = (
        user_ref.collection('memories')
        .where(filter=FieldFilter('status', '==', 'in_progress'))
    )
    docs = [doc.to_dict() for doc in memories_ref.stream()]
    return docs[0] if docs else None


def get_processing_memories(uid: str):
    user_ref = db.collection('users').document(uid)
    memories_ref = (
        user_ref.collection('memories')
        .where(filter=FieldFilter('status', '==', 'processing'))
    )
    return [doc.to_dict() for doc in memories_ref.stream()]


def update_memory_status(uid: str, memory_id: str, status: str):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('memories').document(memory_id)
    memory_ref.update({'status': status})


def set_memory_as_discarded(uid: str, memory_id: str):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('memories').document(memory_id)
    memory_ref.update({'discarded': True})


# *********************************
# ********** CALENDAR *************
# *********************************

def update_memory_events(uid: str, memory_id: str, events: List[dict]):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('memories').document(memory_id)
    memory_ref.update({'structured.events': events})


# *********************************
# ******** ACTION ITEMS ***********
# *********************************

def update_memory_action_items(uid: str, memory_id: str, action_items: List[dict]):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('memories').document(memory_id)
    memory_ref.update({'structured.action_items': action_items})


# ******************************
# ********** OTHER *************
# ******************************

def update_memory_finished_at(uid: str, memory_id: str, finished_at: datetime):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('memories').document(memory_id)
    memory_ref.update({'finished_at': finished_at})


def update_memory_segments(uid: str, memory_id: str, segments: List[dict]):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('memories').document(memory_id)
    memory_ref.update({'transcript_segments': segments})


# ***********************************
# ********** VISIBILITY *************
# ***********************************

def set_memory_visibility(uid: str, memory_id: str, visibility: str):
    user_ref = db.collection('users').document(uid)
    memory_ref = user_ref.collection('memories').document(memory_id)
    memory_ref.update({'visibility': visibility})


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


# ****************************************
# ********** POSTPROCESSING **************
# ****************************************

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


# ***********************************
# ********** OPENGLASS **************
# ***********************************

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


# ********************************
# ********** SYNCING *************
# ********************************

def get_closest_memory_to_timestamps(
        uid: str, start_timestamp: int, end_timestamp: int
) -> Optional[dict]:
    print('get_closest_memory_to_timestamps', start_timestamp, end_timestamp)
    start_threshold = datetime.utcfromtimestamp(start_timestamp) - timedelta(minutes=2)
    end_threshold = datetime.utcfromtimestamp(end_timestamp) + timedelta(minutes=2)
    print('get_closest_memory_to_timestamps', start_threshold, end_threshold)

    query = (
        db.collection('users').document(uid).collection('memories')
        .where(filter=FieldFilter('finished_at', '>=', start_threshold))
        .where(filter=FieldFilter('started_at', '<=', end_threshold))
        .where(filter=FieldFilter('deleted', '==', False))
        .order_by('created_at', direction=firestore.Query.DESCENDING)
    )

    memories = [doc.to_dict() for doc in query.stream()]
    print('get_closest_memory_to_timestamps len(memories)', len(memories))
    if not memories:
        return None

    print('get_closest_memory_to_timestamps found:')
    for memory in memories:
        print('-', memory['id'], memory['started_at'], memory['finished_at'])

    # get the memory that has the closest start timestamp or end timestamp
    closest_memory = None
    min_diff = float('inf')
    for memory in memories:
        memory_start_timestamp = memory['started_at'].timestamp()
        memory_end_timestamp = memory['finished_at'].timestamp()
        diff1 = abs(memory_start_timestamp - start_timestamp)
        diff2 = abs(memory_end_timestamp - end_timestamp)
        if diff1 < min_diff or diff2 < min_diff:
            min_diff = min(diff1, diff2)
            closest_memory = memory

    print('get_closest_memory_to_timestamps closest_memory:', closest_memory['id'])
    return closest_memory

# get_closest_memory_to_timestamps('yOnlnL4a3CYHe6Zlfotrngz9T3w2', 1728236993, 1728237005)
