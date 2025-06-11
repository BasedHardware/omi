import asyncio
import json
import uuid
from datetime import datetime, timedelta
from typing import List, Tuple, Optional

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter
from google.cloud.firestore_v1.base_query import Or
from google.cloud.firestore_v1.async_client import AsyncClient

import utils.other.hume as hume
from database import users as users_db
from models.conversation import ConversationPhoto, PostProcessingStatus, PostProcessingModel, ConversationStatus
from models.transcript_segment import TranscriptSegment
from utils import encryption
from ._client import db

conversations_collection = 'conversations'


# *********************************
# ******* ENCRYPTION HELPERS ******
# *********************************

def _encrypt_conversation_data(conversation_data: dict, uid: str):
    """Encrypts sensitive fields in a conversation dictionary."""
    if 'transcript_segments' in conversation_data and isinstance(conversation_data['transcript_segments'], list):
        segments_json = json.dumps(conversation_data['transcript_segments'])
        conversation_data['transcript_segments'] = encryption.encrypt(segments_json, uid)

    if 'structured' in conversation_data and conversation_data.get('structured'):
        structured = conversation_data['structured']
        if 'title' in structured and structured.get('title'):
            structured['title'] = encryption.encrypt(structured['title'], uid)
        if 'summary' in structured and structured.get('summary'):
            structured['summary'] = encryption.encrypt(structured['summary'], uid)

    return conversation_data


def _decrypt_conversation_data(conversation_data: dict, uid: str):
    """Decrypts sensitive fields in a conversation dictionary."""
    if not conversation_data:
        return conversation_data

    if 'transcript_segments' in conversation_data and isinstance(conversation_data['transcript_segments'], str):
        decrypted_segments_json = encryption.decrypt(conversation_data['transcript_segments'], uid)
        try:
            conversation_data['transcript_segments'] = json.loads(decrypted_segments_json)
        except (json.JSONDecodeError, TypeError):
            # If decryption failed, it might return the original string, which is not valid JSON.
            # Keep it as is for debugging.
            pass

    if 'structured' in conversation_data and conversation_data.get('structured'):
        structured = conversation_data['structured']
        if 'title' in structured and structured.get('title'):
            structured['title'] = encryption.decrypt(structured['title'], uid)
        if 'summary' in structured and structured.get('summary'):
            structured['summary'] = encryption.decrypt(structured['summary'], uid)

    return conversation_data


# *****************************
# ********** CRUD *************
# *****************************

def upsert_conversation(uid: str, conversation_data: dict):
    current_level = users_db.get_data_protection_level(uid)
    conversation_data['data_protection_level'] = current_level

    if current_level == 'enhanced':
        conversation_data = _encrypt_conversation_data(conversation_data, uid)

    if 'audio_base64_url' in conversation_data:
        del conversation_data['audio_base64_url']
    if 'photos' in conversation_data:
        del conversation_data['photos']

    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_data['id'])
    conversation_ref.set(conversation_data)


def get_conversation(uid, conversation_id, expected_level: str = None):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_data = conversation_ref.get().to_dict()

    if not conversation_data:
        return None

    # Determine the encryption level to use for decryption.
    # If an expected_level is passed (during migration), use that.
    # Otherwise, use the document's own level, or the user's global level as a fallback.
    level_for_decryption = expected_level or conversation_data.get('data_protection_level') or users_db.get_data_protection_level(uid)

    if level_for_decryption == 'enhanced':
        conversation_data = _decrypt_conversation_data(conversation_data, uid)

    return conversation_data


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
        # Note: This query will not work on encrypted fields. 'category' is assumed to be unencrypted.
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

    # Decrypt each conversation based on its own protection level
    decrypted_conversations = []
    for conv in conversations:
        if conv.get('data_protection_level') == 'enhanced':
            decrypted_conversations.append(_decrypt_conversation_data(conv, uid))
        else:
            decrypted_conversations.append(conv)
    
    return decrypted_conversations


def update_conversation(uid: str, conversation_id: str, memory_data: dict):
    # When updating, we respect the document's own protection level.
    doc_ref = db.collection('users').document(uid).collection(conversations_collection).document(conversation_id)
    doc_snapshot = doc_ref.get()
    if not doc_snapshot.exists:
        return

    doc_level = doc_snapshot.to_dict().get('data_protection_level', 'standard')

    if doc_level == 'enhanced':
        memory_data = _encrypt_conversation_data(memory_data.copy(), uid)

    doc_ref.update(memory_data)


def update_conversation_title(uid: str, conversation_id: str, title: str):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    
    if users_db.get_data_protection_level(uid) == 'enhanced':
        title = encryption.encrypt(title, uid)
        
    conversation_ref.update({'structured.title': title})


def delete_conversation(uid, conversation_id):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.delete()


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

    decrypted_conversations = []
    for conv in conversations:
        if conv.get('data_protection_level') == 'enhanced':
            decrypted_conversations.append(_decrypt_conversation_data(conv, uid))
        else:
            decrypted_conversations.append(conv)

    return decrypted_conversations


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

    decrypted_conversations = []
    for conv in conversations:
        if conv.get('data_protection_level') == 'enhanced':
            decrypted_conversations.append(_decrypt_conversation_data(conv, uid))
        else:
            decrypted_conversations.append(conv)

    return decrypted_conversations


# **************************************
# ********* MIGRATION HELPERS **********
# **************************************

def get_conversations_to_migrate(uid: str, target_level: str) -> List[dict]:
    """
    Finds all conversations that are not at the target protection level using efficient queries.
    """
    conversations_ref = db.collection('users').document(uid).collection(conversations_collection)
    
    if target_level == 'enhanced':
        # Find documents where level is 'standard' OR null (missing)
        # Using two separate queries because Firestore OR is limited.
        # This is still more efficient than fetching all documents.
        query_standard = conversations_ref.where(filter=FieldFilter('data_protection_level', '==', 'standard'))
        query_null = conversations_ref.where(filter=FieldFilter('data_protection_level', '==', None))
        
        standard_docs = [{'id': doc.id, 'type': 'conversation'} for doc in query_standard.stream()]
        null_docs = [{'id': doc.id, 'type': 'conversation'} for doc in query_null.stream()]
        return standard_docs + null_docs

    elif target_level == 'standard':
        # Find documents that are 'enhanced'
        query = conversations_ref.where(filter=FieldFilter('data_protection_level', '==', 'enhanced'))
        return [{'id': doc.id, 'type': 'conversation'} for doc in query.stream()]
    
    return []


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

    # Decrypt the data first, regardless of target, to get a clean slate.
    if current_level == 'enhanced':
        conversation_data = _decrypt_conversation_data(conversation_data, uid)

    # Now, encrypt if the target is 'enhanced'.
    if target_level == 'enhanced':
        migrated_data = _encrypt_conversation_data(conversation_data.copy(), uid)
    else: # target is 'standard'
        migrated_data = conversation_data.copy()

    # Update the document with the migrated data and the new protection level.
    migrated_data['data_protection_level'] = target_level
    doc_ref.update(migrated_data)


# **************************************
# ********** STATUS *************
# **************************************

def get_in_progress_conversation(uid: str):
    user_ref = db.collection('users').document(uid)
    conversations_ref = (
        user_ref.collection(conversations_collection)
        .where(filter=FieldFilter('status', '==', 'in_progress'))
    )
    docs = [doc.to_dict() for doc in conversations_ref.stream()]
    conversation = docs[0] if docs else None

    if conversation and conversation.get('data_protection_level') == 'enhanced':
        return _decrypt_conversation_data(conversation, uid)

    return conversation


def get_processing_conversations(uid: str):
    user_ref = db.collection('users').document(uid)
    conversations_ref = (
        user_ref.collection(conversations_collection)
        .where(filter=FieldFilter('status', '==', 'processing'))
    )
    conversations = [doc.to_dict() for doc in conversations_ref.stream()]

    decrypted_conversations = []
    for conv in conversations:
        if conv.get('data_protection_level') == 'enhanced':
            decrypted_conversations.append(_decrypt_conversation_data(conv, uid))
        else:
            decrypted_conversations.append(conv)

    return decrypted_conversations


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
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.update({'structured.events': events})


# *********************************
# ******** ACTION ITEMS ***********
# *********************************

def update_conversation_action_items(uid: str, conversation_id: str, action_items: List[dict]):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.update({'structured.action_items': action_items})


# ******************************
# ********** OTHER *************
# ******************************

def update_conversation_finished_at(uid: str, conversation_id: str, finished_at: datetime):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.update({'finished_at': finished_at})


def update_conversation_segments(uid: str, conversation_id: str, segments: List[dict]):
    doc_ref = db.collection('users').document(uid).collection(conversations_collection).document(conversation_id)
    doc_level = doc_ref.get().to_dict().get('data_protection_level', 'standard')

    if doc_level == 'enhanced':
        segments_json = json.dumps(segments)
        encrypted_segments = encryption.encrypt(segments_json, uid)
        update_data = {'transcript_segments': encrypted_segments}
    else:
        update_data = {'transcript_segments': segments}

    doc_ref.update(update_data)


# ***********************************
# ********** VISIBILITY *************
# ***********************************

def set_conversation_visibility(uid: str, conversation_id: str, visibility: str):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.update({'visibility': visibility})


async def _get_public_conversation(db: AsyncClient, uid: str, conversation_id: str):
    conversation_ref = db.collection('users').document(uid).collection('conversations').document(conversation_id)
    conversation_doc = await conversation_ref.get()
    if conversation_doc.exists:
        conversation_data = conversation_doc.to_dict()
        if conversation_data.get('visibility') in ['public']:
            # Decrypt if necessary before returning
            if conversation_data.get('data_protection_level') == 'enhanced':
                return _decrypt_conversation_data(conversation_data, uid)
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

def store_conversation_photos(uid: str, conversation_id: str, photos: List[ConversationPhoto]):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
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
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
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
    
    if closest_conversation and closest_conversation.get('data_protection_level') == 'enhanced':
        return _decrypt_conversation_data(closest_conversation, uid)

    return closest_conversation


def get_last_completed_conversation(uid: str) -> Optional[dict]:
    query = (
        db.collection('users').document(uid).collection(conversations_collection)
        .where(filter=FieldFilter('status', '==', ConversationStatus.completed))
        .order_by('created_at', direction=firestore.Query.DESCENDING)
        .limit(1)
    )
    conversations = [doc.to_dict() for doc in query.stream()]
    conversation = conversations[0] if conversations else None

    if conversation and conversation.get('data_protection_level') == 'enhanced':
        return _decrypt_conversation_data(conversation, uid)
        
    return conversation
