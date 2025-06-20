import asyncio
import copy
import json
import uuid
import zlib
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict, Any

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter
from google.cloud.firestore_v1.async_client import AsyncClient

import utils.other.hume as hume
from database import users as users_db
from models.conversation import ConversationPhoto, PostProcessingStatus, PostProcessingModel, ConversationStatus
from models.transcript_segment import TranscriptSegment
from utils import encryption
from ._client import db
from .helpers import set_data_protection_level, prepare_for_write, prepare_for_read, with_photos

conversations_collection = 'conversations'


# *********************************
# ******* ENCRYPTION HELPERS ******
# *********************************

def _decrypt_conversation_data(conversation_data: Dict[str, Any], uid: str) -> Dict[str, Any]:
    data = copy.deepcopy(conversation_data)

    if 'transcript_segments' in data and isinstance(data['transcript_segments'], str):
        try:
            decrypted_payload = encryption.decrypt(data['transcript_segments'], uid)
            if data.get('transcript_segments_compressed'):
                # New format: encrypted(compressed(json))
                compressed_bytes = bytes.fromhex(decrypted_payload)
                decompressed_json = zlib.decompress(compressed_bytes).decode('utf-8')
                data['transcript_segments'] = json.loads(decompressed_json)
            else:
                # Old format: encrypted(json)
                data['transcript_segments'] = json.loads(decrypted_payload)
        except (json.JSONDecodeError, TypeError, zlib.error, ValueError):
            pass

    return data


def _prepare_conversation_for_write(data: Dict[str, Any], uid: str, level: str) -> Dict[str, Any]:
    data = copy.deepcopy(data)
    if 'transcript_segments' in data and isinstance(data['transcript_segments'], list):
        segments_json = json.dumps(data['transcript_segments'])
        compressed_segments_bytes = zlib.compress(segments_json.encode('utf-8'))
        data['transcript_segments_compressed'] = True

        if level == 'enhanced':
            encrypted_segments = encryption.encrypt(compressed_segments_bytes.hex(), uid)
            data['transcript_segments'] = encrypted_segments
        else:
            data['transcript_segments'] = compressed_segments_bytes
    return data


def _prepare_conversation_for_read(conversation_data: Optional[Dict[str, Any]], uid: str) -> Optional[Dict[str, Any]]:
    if not conversation_data:
        return None

    data = copy.deepcopy(conversation_data)
    level = data.get('data_protection_level')

    if level == 'enhanced':
        return _decrypt_conversation_data(data, uid)

    # Handle standard level with potential compression
    if data.get('transcript_segments_compressed'):
        if 'transcript_segments' in data and isinstance(data['transcript_segments'], bytes):
            try:
                decompressed_json = zlib.decompress(data['transcript_segments']).decode('utf-8')
                data['transcript_segments'] = json.loads(decompressed_json)
            except (json.JSONDecodeError, TypeError, zlib.error):
                pass

    return data


# *****************************
# ********** CRUD *************
# *****************************

@set_data_protection_level(data_arg_name='conversation_data')
@prepare_for_write(data_arg_name='conversation_data', prepare_func=_prepare_conversation_for_write)
def upsert_conversation(uid: str, conversation_data: dict):
    if 'audio_base64_url' in conversation_data:
        del conversation_data['audio_base64_url']
    if 'photos' in conversation_data:
        del conversation_data['photos']

    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_data['id'])
    conversation_ref.set(conversation_data)

@prepare_for_read(decrypt_func=_prepare_conversation_for_read)
@with_photos()
def get_conversation(uid, conversation_id):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_data = conversation_ref.get().to_dict()
    return conversation_data


@prepare_for_read(decrypt_func=_prepare_conversation_for_read)
@with_photos()
def get_conversations(uid: str, limit: int = 100, offset: int = 0, include_discarded: bool = False,
                      statuses: List[str] = [], start_date: Optional[datetime] = None,
                      end_date: Optional[datetime] = None, categories: Optional[List[str]] = None):
    conversations_ref = (
        db.collection('users').document(uid).collection(conversations_collection)
    )
    if not include_discarded:
        conversations_ref = conversations_ref.where(filter=FieldFilter('discarded', '==', False))
    if len(statuses) > 0:
        conversations_ref = conversations_ref.where(filter=FieldFilter('status', 'in', statuses))

    if categories:
        conversations_ref = conversations_ref.where(filter=FieldFilter('structured.category', 'in', categories))

    # Apply date range filters if provided
    if start_date:
        conversations_ref = conversations_ref.where(filter=FieldFilter('created_at', '>=', start_date))
    if end_date:
        conversations_ref = conversations_ref.where(filter=FieldFilter('created_at', '<=', end_date))

    # Sort
    conversations_ref = conversations_ref.order_by('created_at', direction=firestore.Query.DESCENDING)

    # Limits
    conversations_ref = conversations_ref.limit(limit).offset(offset)

    conversations = [doc.to_dict() for doc in conversations_ref.stream()]
    return conversations


def update_conversation(uid: str, conversation_id: str, update_data: dict):
    doc_ref = db.collection('users').document(uid).collection(conversations_collection).document(conversation_id)
    doc_snapshot = doc_ref.get()
    if not doc_snapshot.exists:
        return

    doc_level = doc_snapshot.to_dict().get('data_protection_level', 'standard')
    prepared_data = _prepare_conversation_for_write(update_data, uid, doc_level)
    doc_ref.update(prepared_data)


def update_conversation_title(uid: str, conversation_id: str, title: str):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)

    doc_snapshot = conversation_ref.get()
    if not doc_snapshot.exists:
        return

    conversation_ref.update({'structured.title': title})


def delete_conversation(uid, conversation_id):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.delete()


@prepare_for_read(decrypt_func=_prepare_conversation_for_read)
@with_photos()
def filter_conversations_by_date(uid, start_date, end_date):
    user_ref = db.collection('users').document(uid)
    query = (
        user_ref.collection(conversations_collection)
        .where(filter=FieldFilter('created_at', '>=', start_date))
        .where(filter=FieldFilter('created_at', '<=', end_date))
        .where(filter=FieldFilter('discarded', '==', False))
        .order_by('created_at', direction=firestore.Query.DESCENDING)
    )
    conversations = [doc.to_dict() for doc in query.stream()]
    return conversations


@prepare_for_read(decrypt_func=_prepare_conversation_for_read)
@with_photos()
def get_conversations_by_id(uid, conversation_ids):
    user_ref = db.collection('users').document(uid)
    conversations_ref = user_ref.collection(conversations_collection)

    doc_refs = [conversations_ref.document(str(conversation_id)) for conversation_id in conversation_ids]
    docs = db.get_all(doc_refs)

    conversations = []
    for doc in docs:
        if doc.exists:
            data = doc.to_dict()
            if data.get('discarded'):
                continue
            conversations.append(data)

    return conversations


# **************************************
# ********* MIGRATION HELPERS **********
# **************************************

def get_conversations_to_migrate(uid: str, target_level: str) -> List[dict]:
    """
    Finds all conversations that are not at the target protection level by fetching all documents
    and filtering them in memory. This simplifies the code but may be less performant for
    users with a very large number of documents.
    """
    conversations_ref = db.collection('users').document(uid).collection(conversations_collection)
    all_conversations = conversations_ref.select(['data_protection_level', 'visibility']).stream()

    to_migrate = []
    for doc in all_conversations:
        doc_data = doc.to_dict()
        if doc_data.get('visibility') in ['public', 'shared']:
            continue

        current_level = doc_data.get('data_protection_level', 'standard')
        if target_level != current_level:
            to_migrate.append({'id': doc.id, 'type': 'conversation'})

    return to_migrate


def migrate_conversation_level(uid: str, conversation_id: str, target_level: str):
    """
    Migrates a single conversation to the target protection level.
    """
    doc_ref = db.collection('users').document(uid).collection(conversations_collection).document(conversation_id)
    doc_snapshot = doc_ref.get()
    if not doc_snapshot.exists:
        raise ValueError("Conversation not found")

    conversation_data = doc_snapshot.to_dict()
    current_level = conversation_data.get('data_protection_level', 'standard')

    if current_level == target_level:
        return  # Nothing to do

    # Decrypt/decompress the data to get a clean slate.
    plain_data = _prepare_conversation_for_read(conversation_data, uid)

    # Re-prepare the segments for writing with the new level.
    update_payload = {'transcript_segments': plain_data.get('transcript_segments')}
    prepared_payload = _prepare_conversation_for_write(update_payload, uid, target_level)

    # Update the document with the migrated data and the new protection level.
    update_data = {
        'data_protection_level': target_level,
    }
    if 'transcript_segments' in prepared_payload:
        update_data['transcript_segments'] = prepared_payload['transcript_segments']
        update_data['transcript_segments_compressed'] = prepared_payload.get('transcript_segments_compressed', False)

    if not update_data.get('transcript_segments_compressed'):
        update_data['transcript_segments_compressed'] = firestore.DELETE_FIELD

    doc_ref.update(update_data)


def migrate_conversations_level_batch(uid: str, conversation_ids: List[str], target_level: str):
    """
    Migrates a batch of conversations to the target protection level.
    """
    batch = db.batch()
    conversations_ref = db.collection('users').document(uid).collection(conversations_collection)
    doc_refs = [conversations_ref.document(conv_id) for conv_id in conversation_ids]
    doc_snapshots = db.get_all(doc_refs)

    for doc_snapshot in doc_snapshots:
        if not doc_snapshot.exists:
            print(f"Conversation {doc_snapshot.id} not found, skipping.")
            continue

        conversation_data = doc_snapshot.to_dict()
        current_level = conversation_data.get('data_protection_level', 'standard')

        if current_level == target_level:
            continue

        # Decrypt/decompress the data to get a clean slate.
        plain_data = _prepare_conversation_for_read(conversation_data, uid)

        # Re-prepare the segments for writing with the new level.
        update_payload = {'transcript_segments': plain_data.get('transcript_segments')}
        prepared_payload = _prepare_conversation_for_write(update_payload, uid, target_level)

        # Update the document with the migrated data and the new protection level.
        update_data = {
            'data_protection_level': target_level,
        }
        if 'transcript_segments' in prepared_payload:
            update_data['transcript_segments'] = prepared_payload['transcript_segments']
            update_data['transcript_segments_compressed'] = prepared_payload.get('transcript_segments_compressed', False)

        if not update_data.get('transcript_segments_compressed'):
            update_data['transcript_segments_compressed'] = firestore.DELETE_FIELD

        batch.update(doc_snapshot.reference, update_data)

    batch.commit()


# **************************************
# ********** STATUS *************
# **************************************

@prepare_for_read(decrypt_func=_prepare_conversation_for_read)
@with_photos()
def get_in_progress_conversation(uid: str):
    user_ref = db.collection('users').document(uid)
    conversations_ref = (
        user_ref.collection(conversations_collection)
        .where(filter=FieldFilter('status', '==', 'in_progress'))
    )
    docs = [doc.to_dict() for doc in conversations_ref.stream()]
    conversation = docs[0] if docs else None
    return conversation


@prepare_for_read(decrypt_func=_prepare_conversation_for_read)
@with_photos()
def get_processing_conversations(uid: str):
    user_ref = db.collection('users').document(uid)
    conversations_ref = (
        user_ref.collection(conversations_collection)
        .where(filter=FieldFilter('status', '==', 'processing'))
    )
    conversations = [doc.to_dict() for doc in conversations_ref.stream()]
    return conversations


def update_conversation_status(uid: str, conversation_id: str, status: str):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.update({'status': status})


def set_conversation_as_discarded(uid: str, conversation_id: str):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.update({'discarded': True})


# *********************************
# ********** CALENDAR *************
# *********************************

def update_conversation_events(uid: str, conversation_id: str, events: List[dict]):
    update_conversation(uid, conversation_id, {'structured.events': events})


# *********************************
# ******** ACTION ITEMS ***********
# *********************************

def update_conversation_action_items(uid: str, conversation_id: str, action_items: List[dict]):
    update_conversation(uid, conversation_id, {'structured.action_items': action_items})


# ******************************
# ********** OTHER *************
# ******************************

def update_conversation_finished_at(uid: str, conversation_id: str, finished_at: datetime):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.update({'finished_at': finished_at})


def update_conversation_segments(uid: str, conversation_id: str, segments: List[dict]):
    doc_ref = db.collection('users').document(uid).collection(conversations_collection).document(conversation_id)
    doc_snapshot = doc_ref.get(field_paths=['data_protection_level'])
    if not doc_snapshot.exists:
        return

    doc_level = doc_snapshot.to_dict().get('data_protection_level', 'standard')
    update_payload = {'transcript_segments': segments}
    prepared_payload = _prepare_conversation_for_write(update_payload, uid, doc_level)
    doc_ref.update(prepared_payload)


# ***********************************
# ********** VISIBILITY *************
# ***********************************

def set_conversation_visibility(uid: str, conversation_id: str, visibility: str):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.update({'visibility': visibility})


@prepare_for_read(decrypt_func=_prepare_conversation_for_read)
async def _get_public_conversation(db_client: AsyncClient, uid: str, conversation_id: str):
    conversation_ref = db_client.collection('users').document(uid).collection('conversations').document(conversation_id)
    conversation_doc = await conversation_ref.get()
    if conversation_doc.exists:
        conversation_data = conversation_doc.to_dict()
        if conversation_data.get('visibility') in ['public']:
            photos_ref = conversation_ref.collection('photos')
            photos_docs = await photos_ref.stream()
            conversation_data['photos'] = [doc.to_dict() for doc in photos_docs]
            return conversation_data
    return None


async def _get_public_conversations(data: List[Tuple[str, str]]):
    db_client = AsyncClient()
    tasks = [_get_public_conversation(db_client, uid, conversation_id) for uid, conversation_id in data]
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
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.update({
        'postprocessing.status': status,
        'postprocessing.model': model,
        'postprocessing.fail_reason': fail_reason
    })


def store_model_segments_result(uid: str, conversation_id: str, model_name: str, segments: List[TranscriptSegment]):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
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
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
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
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
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

def add_conversation_photo(uid: str, conversation_id: str, photo_data: dict) -> str:
    """
    Adds a single photo to a conversation's 'photos' sub-collection and returns the new photo's ID.
    """
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    photos_ref = conversation_ref.collection('photos')

    photo_id = str(uuid.uuid4())
    photo_data['id'] = photo_id

    photo_doc_ref = photos_ref.document(photo_id)
    photo_doc_ref.set(photo_data)

    return photo_id


def update_conversation_photo(uid: str, conversation_id: str, photo_id: str, updates: dict):
    """
    Updates a specific photo document in a conversation's 'photos' sub-collection.
    """
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    photo_ref = conversation_ref.collection('photos').document(photo_id)
    photo_ref.update(updates)


def store_conversation_photos(uid: str, conversation_id: str, photos: List[ConversationPhoto]):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    photos_ref = conversation_ref.collection('photos')
    batch = db.batch()
    for photo in photos:
        photo_id = photo.id or str(uuid.uuid4())
        photo_ref = photos_ref.document(photo_id)
        data = photo.dict()
        data['id'] = photo_id
        batch.set(photo_ref, data)
    batch.commit()


def get_conversation_photos(uid: str, conversation_id: str):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    photos_ref = conversation_ref.collection('photos')
    return [doc.to_dict() for doc in photos_ref.stream()]


# ********************************
# ********** SYNCING *************
# ********************************

@prepare_for_read(decrypt_func=_prepare_conversation_for_read)
@with_photos()
def get_closest_conversation_to_timestamps(
        uid: str, start_timestamp: int, end_timestamp: int
) -> Optional[dict]:
    print('get_closest_conversation_to_timestamps', start_timestamp, end_timestamp)
    start_threshold = datetime.utcfromtimestamp(start_timestamp) - timedelta(minutes=2)
    end_threshold = datetime.utcfromtimestamp(end_timestamp) + timedelta(minutes=2)
    print('get_closest_conversation_to_timestamps', start_threshold, end_threshold)

    query = (
        db.collection('users').document(uid).collection(conversations_collection)
        .where(filter=FieldFilter('finished_at', '>=', start_threshold))
        .where(filter=FieldFilter('started_at', '<=', end_threshold))
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


@prepare_for_read(decrypt_func=_prepare_conversation_for_read)
@with_photos()
def get_last_completed_conversation(uid: str) -> Optional[dict]:
    query = (
        db.collection('users').document(uid).collection(conversations_collection)
        .where(filter=FieldFilter('status', '==', ConversationStatus.completed))
        .order_by('created_at', direction=firestore.Query.DESCENDING)
        .limit(1)
    )
    conversations = [doc.to_dict() for doc in query.stream()]
    conversation = conversations[0] if conversations else None
    return conversation
