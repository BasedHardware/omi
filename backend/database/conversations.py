import asyncio
import json
import uuid
from datetime import datetime, timedelta
from typing import List, Tuple, Optional

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter
from google.cloud.firestore_v1.async_client import AsyncClient

import utils.other.hume as hume
from models.conversation import ConversationPhoto, PostProcessingStatus, PostProcessingModel, ConversationStatus
from models.transcript_segment import TranscriptSegment
from ._client import db


def _convert_memory_data_to_conversation_data(data: dict) -> dict:
    """Convert memory data format to conversation data format."""
    if 'processing_memory_id' in data:
        data['processing_conversation_id'] = data.pop('processing_memory_id')
    if 'plugins_results' in data:
        plugins_results = data.pop('plugins_results')
        data['apps_results'] = [
            {'content': result['content'], 'app_id': result['plugin_id']}
            for result in plugins_results
        ]
    return data


def _get_conversation_ref_and_data(user_ref: firestore.DocumentReference, conversation_id: str) -> Tuple[
    firestore.DocumentReference, dict]:
    """Get conversation reference and handle memory_id conversion if needed."""
    memory_ref = user_ref.collection('memories').document(conversation_id)
    conversation_ref = user_ref.collection('conversations').document(conversation_id)

    memory_data = memory_ref.get().to_dict()

    if memory_data and (('processing_memory_id' in memory_data) or ('plugins_results' in memory_data)):
        data = _convert_memory_data_to_conversation_data(memory_data)
        return conversation_ref, data

    return conversation_ref, None


# *****************************
# ********** CRUD *************
# *****************************

def upsert_conversation(uid: str, conversation_data: dict):
    if 'audio_base64_url' in conversation_data:
        del conversation_data['audio_base64_url']
    if 'photos' in conversation_data:
        del conversation_data['photos']

    user_ref = db.collection('users').document(uid)
    # TODO: memories collection is deprecated, remove this after migration
    conversation_ref = user_ref.collection('memories').document(conversation_data['id'])
    conversation_ref.set(conversation_data)
    ########################################################
    new_conversation_ref = user_ref.collection('conversations').document(conversation_data['id'])
    new_conversation_ref.set(_convert_memory_data_to_conversation_data(conversation_data))


def get_conversation(uid, conversation_id):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection('memories').document(conversation_id)
    return conversation_ref.get().to_dict()


def get_conversations(uid: str, limit: int = 100, offset: int = 0, include_discarded: bool = False,
                      statuses: List[str] = [], start_date: Optional[datetime] = None,
                      end_date: Optional[datetime] = None):
    conversations_ref = (
        db.collection('users').document(uid).collection('memories')
        .where(filter=FieldFilter('deleted', '==', False))
    )
    if not include_discarded:
        conversations_ref = conversations_ref.where(filter=FieldFilter('discarded', '==', False))
    if len(statuses) > 0:
        conversations_ref = conversations_ref.where(filter=FieldFilter('status', 'in', statuses))

    # Apply date range filters if provided
    if start_date:
        conversations_ref = conversations_ref.where(filter=FieldFilter('created_at', '>=', start_date))
    if end_date:
        conversations_ref = conversations_ref.where(filter=FieldFilter('created_at', '<=', end_date))

    # Sort
    conversations_ref = conversations_ref.order_by('created_at', direction=firestore.Query.DESCENDING)

    # Limits
    conversations_ref = conversations_ref.limit(limit).offset(offset)
    return [doc.to_dict() for doc in conversations_ref.stream()]


def update_conversation(uid: str, conversation_id: str, memory_data: dict):
    user_ref = db.collection('users').document(uid)
    # TODO: memories collection is deprecated, remove this after migration
    conversation_ref = user_ref.collection('memories').document(conversation_id)
    conversation_ref.update(memory_data)
    ########################################################
    new_conversation_ref, converted_data = _get_conversation_ref_and_data(user_ref, conversation_id)
    if converted_data:
        new_conversation_ref.update(converted_data)
    new_conversation_ref.update(_convert_memory_data_to_conversation_data(memory_data))


def update_conversation_title(uid: str, conversation_id: str, title: str):
    user_ref = db.collection('users').document(uid)
    # TODO: memories collection is deprecated, remove this after migration
    conversation_ref = user_ref.collection('memories').document(conversation_id)
    conversation_ref.update({'structured.title': title})
    ########################################################
    new_conversation_ref, converted_data = _get_conversation_ref_and_data(user_ref, conversation_id)
    if converted_data:
        new_conversation_ref.update(converted_data)
    new_conversation_ref.update({'structured.title': title})


def delete_conversation(uid, conversation_id):
    user_ref = db.collection('users').document(uid)
    # TODO: memories collection is deprecated, remove this after migration
    conversation_ref = user_ref.collection('memories').document(conversation_id)
    conversation_ref.update({'deleted': True})
    ########################################################
    new_conversation_ref, converted_data = _get_conversation_ref_and_data(user_ref, conversation_id)
    if converted_data:
        new_conversation_ref.update(converted_data)
    new_conversation_ref.update({'deleted': True})


def filter_conversations_by_date(uid, start_date, end_date):
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


def get_conversations_by_id(uid, conversation_ids):
    user_ref = db.collection('users').document(uid)
    conversations_ref = user_ref.collection('memories')

    doc_refs = [conversations_ref.document(str(conversation_id)) for conversation_id in conversation_ids]
    docs = db.get_all(doc_refs)

    conversations = []
    for doc in docs:
        if doc.exists:
            data = doc.to_dict()
            if data.get('deleted') or data.get('discarded'):
                continue
            conversations.append(data)
    return conversations


# **************************************
# ********** STATUS *************
# **************************************

def get_in_progress_conversation(uid: str):
    user_ref = db.collection('users').document(uid)
    conversations_ref = (
        user_ref.collection('memories')
        .where(filter=FieldFilter('status', '==', 'in_progress'))
    )
    docs = [doc.to_dict() for doc in conversations_ref.stream()]
    return docs[0] if docs else None


def get_processing_conversations(uid: str):
    user_ref = db.collection('users').document(uid)
    conversations_ref = (
        user_ref.collection('memories')
        .where(filter=FieldFilter('status', '==', 'processing'))
    )
    return [doc.to_dict() for doc in conversations_ref.stream()]


def update_conversation_status(uid: str, conversation_id: str, status: str):
    user_ref = db.collection('users').document(uid)
    # TODO: memories collection is deprecated, remove this after migration
    conversation_ref = user_ref.collection('memories').document(conversation_id)
    conversation_ref.update({'status': status})
    ########################################################
    new_conversation_ref, converted_data = _get_conversation_ref_and_data(user_ref, conversation_id)
    if converted_data:
        new_conversation_ref.update(converted_data)
    new_conversation_ref.update({'status': status})


def set_conversation_as_discarded(uid: str, conversation_id: str):
    user_ref = db.collection('users').document(uid)
    # TODO: memories collection is deprecated, remove this after migration
    conversation_ref = user_ref.collection('memories').document(conversation_id)
    conversation_ref.update({'discarded': True})
    ########################################################
    new_conversation_ref, converted_data = _get_conversation_ref_and_data(user_ref, conversation_id)
    if converted_data:
        new_conversation_ref.update(converted_data)
    new_conversation_ref.update({'discarded': True})


# *********************************
# ********** CALENDAR *************
# *********************************

def update_conversation_events(uid: str, conversation_id: str, events: List[dict]):
    user_ref = db.collection('users').document(uid)
    # TODO: memories collection is deprecated, remove this after migration
    conversation_ref = user_ref.collection('memories').document(conversation_id)
    conversation_ref.update({'structured.events': events})
    ########################################################
    new_conversation_ref, converted_data = _get_conversation_ref_and_data(user_ref, conversation_id)
    if converted_data:
        new_conversation_ref.update(converted_data)
    new_conversation_ref.update({'structured.events': events})


# *********************************
# ******** ACTION ITEMS ***********
# *********************************

def update_conversation_action_items(uid: str, conversation_id: str, action_items: List[dict]):
    user_ref = db.collection('users').document(uid)
    # TODO: memories collection is deprecated, remove this after migration
    conversation_ref = user_ref.collection('memories').document(conversation_id)
    conversation_ref.update({'structured.action_items': action_items})
    ########################################################
    new_conversation_ref, converted_data = _get_conversation_ref_and_data(user_ref, conversation_id)
    if converted_data:
        new_conversation_ref.update(converted_data)
    new_conversation_ref.update({'structured.action_items': action_items})


# ******************************
# ********** OTHER *************
# ******************************

def update_conversation_finished_at(uid: str, conversation_id: str, finished_at: datetime):
    user_ref = db.collection('users').document(uid)
    # TODO: memories collection is deprecated, remove this after migration
    conversation_ref = user_ref.collection('memories').document(conversation_id)
    conversation_ref.update({'finished_at': finished_at})
    ########################################################
    new_conversation_ref, converted_data = _get_conversation_ref_and_data(user_ref, conversation_id)
    if converted_data:
        new_conversation_ref.update(converted_data)
    new_conversation_ref.update({'finished_at': finished_at})


def update_conversation_segments(uid: str, conversation_id: str, segments: List[dict]):
    user_ref = db.collection('users').document(uid)
    # TODO: memories collection is deprecated, remove this after migration
    conversation_ref = user_ref.collection('memories').document(conversation_id)
    conversation_ref.update({'transcript_segments': segments})
    ########################################################
    new_conversation_ref, converted_data = _get_conversation_ref_and_data(user_ref, conversation_id)
    if converted_data:
        new_conversation_ref.update(converted_data)
    new_conversation_ref.update({'transcript_segments': segments})


# ***********************************
# ********** VISIBILITY *************
# ***********************************

def set_conversation_visibility(uid: str, conversation_id: str, visibility: str):
    user_ref = db.collection('users').document(uid)
    # TODO: memories collection is deprecated, remove this after migration
    conversation_ref = user_ref.collection('memories').document(conversation_id)
    conversation_ref.update({'visibility': visibility})
    ########################################################
    new_conversation_ref, converted_data = _get_conversation_ref_and_data(user_ref, conversation_id)
    if converted_data:
        new_conversation_ref.update(converted_data)
    new_conversation_ref.update({'visibility': visibility})


async def _get_public_conversation(db: AsyncClient, uid: str, conversation_id: str):
    conversation_ref = db.collection('users').document(uid).collection('memories').document(conversation_id)
    conversation_doc = await conversation_ref.get()
    if conversation_doc.exists:
        conversation_data = conversation_doc.to_dict()
        if conversation_data.get('visibility') in ['public'] and not conversation_data.get('deleted'):
            return conversation_data
    return None


async def _get_public_conversations(data: List[Tuple[str, str]]):
    db = AsyncClient()
    tasks = [_get_public_conversation(db, uid, conversation_id) for uid, conversation_id in data]
    conversations = await asyncio.gather(*tasks)
    return [conversation for conversation in conversations if conversation is not None]


def run_get_public_conversations(data: List[Tuple[str, str]]):
    return asyncio.run(_get_public_conversations(data))


# ****************************************
# ********** POSTPROCESSING **************
# ****************************************

def set_postprocessing_status(
        uid: str, conversation_id: str, status: PostProcessingStatus, fail_reason: str = None,
        model: PostProcessingModel = PostProcessingModel.fal_whisperx
):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection('memories').document(conversation_id)
    conversation_ref.update({
        'postprocessing.status': status,
        'postprocessing.model': model,
        'postprocessing.fail_reason': fail_reason
    })


def store_model_segments_result(uid: str, conversation_id: str, model_name: str, segments: List[TranscriptSegment]):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection('memories').document(conversation_id)
    segments_ref = conversation_ref.collection(model_name)
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
        uid: str, conversation_id: str, model_name: str,
        predictions: List[hume.HumeJobModelPredictionResponseModel]
):
    now = datetime.now()
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection('memories').document(conversation_id)
    predictions_ref = conversation_ref.collection(model_name)
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


def get_conversation_transcripts_by_model(uid: str, conversation_id: str):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection('memories').document(conversation_id)
    deepgram_ref = conversation_ref.collection('deepgram_streaming')
    soniox_ref = conversation_ref.collection('soniox_streaming')
    speechmatics_ref = conversation_ref.collection('speechmatics_streaming')
    whisperx_ref = conversation_ref.collection('fal_whisperx')

    return {
        'deepgram': list(sorted([doc.to_dict() for doc in deepgram_ref.stream()], key=lambda x: x['start'])),
        'soniox': list(sorted([doc.to_dict() for doc in soniox_ref.stream()], key=lambda x: x['start'])),
        'speechmatics': list(sorted([doc.to_dict() for doc in speechmatics_ref.stream()], key=lambda x: x['start'])),
        'whisperx': list(sorted([doc.to_dict() for doc in whisperx_ref.stream()], key=lambda x: x['start'])),
    }


# ***********************************
# ********** OPENGLASS **************
# ***********************************

def store_conversation_photos(uid: str, conversation_id: str, photos: List[ConversationPhoto]):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection('memories').document(conversation_id)
    photos_ref = conversation_ref.collection('photos')
    batch = db.batch()
    for photo in photos:
        photo_id = str(uuid.uuid4())
        photo_ref = photos_ref.document(str(uuid.uuid4()))
        data = photo.dict()
        data['id'] = photo_id
        batch.set(photo_ref, data)
    batch.commit()


def get_conversation_photos(uid: str, conversation_id: str):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection('memories').document(conversation_id)
    photos_ref = conversation_ref.collection('photos')
    return [doc.to_dict() for doc in photos_ref.stream()]


# ********************************
# ********** SYNCING *************
# ********************************

def get_closest_conversation_to_timestamps(
        uid: str, start_timestamp: int, end_timestamp: int
) -> Optional[dict]:
    print('get_closest_conversation_to_timestamps', start_timestamp, end_timestamp)
    start_threshold = datetime.utcfromtimestamp(start_timestamp) - timedelta(minutes=2)
    end_threshold = datetime.utcfromtimestamp(end_timestamp) + timedelta(minutes=2)
    print('get_closest_conversation_to_timestamps', start_threshold, end_threshold)

    query = (
        db.collection('users').document(uid).collection('memories')
        .where(filter=FieldFilter('finished_at', '>=', start_threshold))
        .where(filter=FieldFilter('started_at', '<=', end_threshold))
        .where(filter=FieldFilter('deleted', '==', False))
        .order_by('created_at', direction=firestore.Query.DESCENDING)
    )

    conversations = [doc.to_dict() for doc in query.stream()]
    print('get_closest_conversation_to_timestamps len(conversations)', len(conversations))
    if not conversations:
        return None

    print('get_closest_conversation_to_timestamps found:')
    for conversation in conversations:
        print('-', conversation['id'], conversation['started_at'], conversation['finished_at'])

    # get the conversation that has the closest start timestamp or end timestamp
    closest_conversation = None
    min_diff = float('inf')
    for conversation in conversations:
        conversation_start_timestamp = conversation['started_at'].timestamp()
        conversation_end_timestamp = conversation['finished_at'].timestamp()
        diff1 = abs(conversation_start_timestamp - start_timestamp)
        diff2 = abs(conversation_end_timestamp - end_timestamp)
        if diff1 < min_diff or diff2 < min_diff:
            min_diff = min(diff1, diff2)
            closest_conversation = conversation

    print('get_closest_conversation_to_timestamps closest_conversation:', closest_conversation['id'])
    return closest_conversation


def get_last_completed_conversation(uid: str) -> Optional[dict]:
    query = (
        db.collection('users').document(uid).collection('memories')
        .where(filter=FieldFilter('deleted', '==', False))
        .where(filter=FieldFilter('status', '==', ConversationStatus.completed))
        .order_by('created_at', direction=firestore.Query.DESCENDING)
        .limit(1)
    )
    conversations = [doc.to_dict() for doc in query.stream()]
    return conversations[0] if conversations else None
