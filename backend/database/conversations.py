import copy
import json
import uuid
import zlib
from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Optional, Dict, Any

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

import utils.other.hume as hume
from database import users as users_db
from models.conversation import (
    ConversationPhoto,
    PostProcessingStatus,
    PostProcessingModel,
    ConversationStatus,
    AudioFile,
)
from models.transcript_segment import TranscriptSegment
from utils import encryption
from ._client import db
from .helpers import set_data_protection_level, prepare_for_write, prepare_for_read, with_photos
from utils.other.storage import list_audio_chunks

conversations_collection = 'conversations'


def _ensure_timezone_aware(dt: datetime) -> datetime:
    """
    Ensure a datetime object is timezone-aware.
    If naive, assume UTC timezone.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# *********************************
# ******* ENCRYPTION HELPERS ******
# *********************************


def _decrypt_conversation_data(conversation_data: Dict[str, Any], uid: str) -> Dict[str, Any]:
    data = copy.deepcopy(conversation_data)

    if 'transcript_segments' not in data:
        return data

    if isinstance(data['transcript_segments'], str):
        try:
            decrypted_payload = encryption.decrypt(data['transcript_segments'], uid)
            if data.get('transcript_segments_compressed'):
                compressed_bytes = bytes.fromhex(decrypted_payload)
                decompressed_json = zlib.decompress(compressed_bytes).decode('utf-8')
                data['transcript_segments'] = json.loads(decompressed_json)
            # backward compatibility, will be removed soon
            else:
                data['transcript_segments'] = json.loads(decrypted_payload)
        except (json.JSONDecodeError, TypeError, zlib.error, ValueError) as e:
            print(e, uid)
            data['transcript_segments'] = []
    # backward compatibility, will be removed soon
    elif isinstance(data['transcript_segments'], bytes):
        try:
            compressed_bytes = data['transcript_segments']
            if data.get('transcript_segments_compressed'):
                decompressed_json = zlib.decompress(compressed_bytes).decode('utf-8')
                data['transcript_segments'] = json.loads(decompressed_json)
        except (json.JSONDecodeError, TypeError, zlib.error, ValueError) as e:
            print(e, uid)
            data['transcript_segments'] = []

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
            except (json.JSONDecodeError, TypeError, zlib.error) as e:
                print(e)
                pass

    return data


def _prepare_photo_for_write(data: Dict[str, Any], uid: str, level: str) -> Dict[str, Any]:
    data = copy.deepcopy(data)
    data['data_protection_level'] = level
    if level == 'enhanced' and 'base64' in data and isinstance(data['base64'], str):
        data['base64'] = encryption.encrypt(data['base64'], uid)
    return data


def _prepare_photo_for_read(photo_data: Optional[Dict[str, Any]], uid: str) -> Optional[Dict[str, Any]]:
    if not photo_data:
        return None
    data = copy.deepcopy(photo_data)
    level = data.get('data_protection_level')
    if level == 'enhanced' and 'base64' in data and isinstance(data['base64'], str):
        try:
            data['base64'] = encryption.decrypt(data['base64'], uid)
        except Exception:
            # If decryption fails, it might be already decrypted or not encrypted.
            # We can log this, but for now, we'll just pass.
            pass
    return data


def _normalize_apps_results(apps_results: Any) -> list:
    """
    Normalize apps_results to ensure it's a valid list with required fields.
    """
    if isinstance(apps_results, dict):
        apps_results = [apps_results[k] for k in sorted(apps_results.keys(), key=int)]

    if not isinstance(apps_results, list):
        return []

    normalized = []
    for item in apps_results:
        if not isinstance(item, dict):
            continue
        if not item.get('app_id'):
            continue
        normalized.append(item)

    return normalized


@prepare_for_read(decrypt_func=_prepare_photo_for_read)
def get_conversation_photos(uid: str, conversation_id: str):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    photos_ref = conversation_ref.collection('photos')
    photos = [doc.to_dict() for doc in photos_ref.stream()]
    return photos


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
@with_photos(get_conversation_photos)
def get_conversation(uid, conversation_id):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_data = conversation_ref.get().to_dict()
    
    # Normalize apps_results and filter out invalid entries
    if conversation_data:
        conversation_data['apps_results'] = _normalize_apps_results(
            conversation_data.get('apps_results')
        )
    
    return conversation_data


@prepare_for_read(decrypt_func=_prepare_conversation_for_read)
@with_photos(get_conversation_photos)
def get_conversations(
    uid: str,
    limit: int = 100,
    offset: int = 0,
    include_discarded: bool = False,
    statuses: List[str] = [],
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    categories: Optional[List[str]] = None,
    folder_id: Optional[str] = None,
    starred: Optional[bool] = None,
):
    conversations_ref = db.collection('users').document(uid).collection(conversations_collection)
    if not include_discarded:
        conversations_ref = conversations_ref.where(filter=FieldFilter('discarded', '==', False))
    if len(statuses) > 0:
        conversations_ref = conversations_ref.where(filter=FieldFilter('status', 'in', statuses))

    if categories:
        conversations_ref = conversations_ref.where(filter=FieldFilter('structured.category', 'in', categories))

    if folder_id:
        conversations_ref = conversations_ref.where(filter=FieldFilter('folder_id', '==', folder_id))

    if starred is not None:
        conversations_ref = conversations_ref.where(filter=FieldFilter('starred', '==', starred))

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
    
    # Normalize apps_results and filter out invalid entries
    for conversation in conversations:
        conversation['apps_results'] = _normalize_apps_results(
            conversation.get('apps_results')
        )
    
    return conversations


@prepare_for_read(decrypt_func=_prepare_conversation_for_read)
def get_conversations_without_photos(
    uid: str,
    limit: int = 100,
    offset: int = 0,
    include_discarded: bool = False,
    statuses: List[str] = [],
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    categories: Optional[List[str]] = None,
):
    """
    Same as get_conversations but without loading photos.
    Much faster for bulk operations like Wrapped where photos aren't needed.
    """
    conversations_ref = db.collection('users').document(uid).collection(conversations_collection)
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


def create_audio_files_from_chunks(
    uid: str,
    conversation_id: str,
) -> List[AudioFile]:
    """
    Create audio file records by merging chunks from a conversation.
    Chunks are merged unless there's a gap > 30 seconds between segments.

    Args:
        uid: User ID
        conversation_id: Conversation ID

    Returns:
        List of AudioFile objects
    """
    # Get all chunks for this conversation
    chunks = list_audio_chunks(uid, conversation_id)
    if not chunks:
        return []

    # Group chunks based on 30-second gap rule
    audio_files = []
    current_group = []

    for i, chunk in enumerate(chunks):
        if not current_group:
            current_group.append(chunk)
        else:
            # Check if there's a gap > 30 seconds between chunks
            prev_chunk = current_group[-1]
            time_gap = chunk['timestamp'] - prev_chunk['timestamp']
            if time_gap > 30:
                # Gap detected, finalize current group
                audio_file = _finalize_audio_file_group(uid, conversation_id, current_group, audio_files)
                if audio_file:
                    audio_files.append(audio_file)
                current_group = [chunk]
            else:
                current_group.append(chunk)

    # Finalize last group
    if current_group:
        audio_file = _finalize_audio_file_group(uid, conversation_id, current_group, audio_files)
        if audio_file:
            audio_files.append(audio_file)

    return audio_files


def _finalize_audio_file_group(
    uid: str, conversation_id: str, chunk_group: List[dict], existing_files: List[AudioFile]
) -> Optional[AudioFile]:
    """
    Create an AudioFile record that references chunks (no merging).

    Args:
        uid: User ID
        conversation_id: Conversation ID
        chunk_group: List of chunk dicts to reference
        existing_files: List of existing audio files

    Returns:
        AudioFile object or None if failed
    """
    if not chunk_group:
        return None

    # Generate file ID
    file_id = str(uuid.uuid4())

    # Extract timestamps
    timestamps = [chunk['timestamp'] for chunk in chunk_group]

    # Calculate started_at and duration from timestamps
    started_at = datetime.fromtimestamp(chunk_group[0]['timestamp'], tz=timezone.utc)
    last_chunk_start = datetime.fromtimestamp(chunk_group[-1]['timestamp'], tz=timezone.utc)
    # Add 5 seconds for the last chunk's duration
    duration = (last_chunk_start - started_at).total_seconds() + 5.0

    return AudioFile(
        id=file_id,
        uid=uid,
        conversation_id=conversation_id,
        chunk_timestamps=timestamps,
        provider='gcp',
        started_at=started_at,
        duration=duration,
    )


def update_conversation_title(uid: str, conversation_id: str, title: str):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)

    doc_snapshot = conversation_ref.get()
    if not doc_snapshot.exists:
        return

    conversation_ref.update({'structured.title': title})


def update_conversation_overview(uid: str, conversation_id: str, overview: str):
    update_data = {'structured.overview': overview}
    update_conversation(uid, conversation_id, update_data)


def update_conversation_segment_text(uid: str, conversation_id: str, segment_id: str, text: str):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)

    @firestore.transactional
    def update_in_transaction(transaction):
        doc_snapshot = conversation_ref.get(transaction=transaction)
        if not doc_snapshot.exists:
            return

        conversation_data = doc_snapshot.to_dict()
        level = conversation_data.get('data_protection_level', 'standard')

        decrypted_data = _prepare_conversation_for_read(conversation_data, uid)
        if not decrypted_data:
            return

        transcript_segments = decrypted_data.get('transcript_segments', [])

        # Find and update the segment
        updated = False
        for segment in transcript_segments:
            if isinstance(segment, dict) and segment.get('id') == segment_id:
                segment['text'] = text
                updated = True
                break

        if not updated:
            return

        prepared_data = _prepare_conversation_for_write(
            {'transcript_segments': transcript_segments},
            uid,
            level,
        )

        update_dict = {'transcript_segments': prepared_data['transcript_segments']}

        if 'transcript_segments_compressed' in prepared_data:
            update_dict['transcript_segments_compressed'] = prepared_data['transcript_segments_compressed']

        transaction.update(conversation_ref, update_dict)

    transaction = db.transaction()
    update_in_transaction(transaction)


def delete_conversation_photos(uid: str, conversation_id: str) -> int:
    """
    Delete all photos in a conversation's photos subcollection.

    IMPORTANT: Firestore does NOT cascade delete subcollections when you delete
    a parent document. This function must be called before deleting a conversation.

    Args:
        uid: User ID
        conversation_id: Conversation ID

    Returns:
        Number of photos deleted
    """
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    photos_ref = conversation_ref.collection('photos')

    # Get all photo documents
    photos = photos_ref.stream()
    deleted_count = 0

    # Delete in batches of 500 (Firestore batch limit)
    batch = db.batch()
    batch_count = 0

    for photo_doc in photos:
        batch.delete(photo_doc.reference)
        batch_count += 1
        deleted_count += 1

        if batch_count >= 500:
            batch.commit()
            batch = db.batch()
            batch_count = 0

    # Commit remaining
    if batch_count > 0:
        batch.commit()

    return deleted_count


def delete_conversation(uid, conversation_id):
    """
    Delete a conversation and its photos subcollection.

    Args:
        uid: User ID
        conversation_id: Conversation ID
    """
    # Delete photos subcollection first
    delete_conversation_photos(uid, conversation_id)

    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.delete()


def update_conversation_merged_data(uid: str, conversation_id: str, merged_data: dict):
    """
    Update a conversation with merged data from multiple conversations.

    This function handles the bulk update of all merged fields and respects
    the conversation's data protection level.

    Args:
        uid: User ID
        conversation_id: Primary conversation ID to update
        merged_data: Dictionary containing all merged fields
    """
    doc_ref = db.collection('users').document(uid).collection(conversations_collection).document(conversation_id)
    doc_snapshot = doc_ref.get()
    if not doc_snapshot.exists:
        return

    doc_level = doc_snapshot.to_dict().get('data_protection_level', 'standard')
    prepared_data = _prepare_conversation_for_write(merged_data, uid, doc_level)
    doc_ref.update(prepared_data)


def delete_conversations_by_source(uid: str, source: str, batch_size: int = 450) -> int:
    """
    Delete all conversations with a specific source.

    Args:
        uid: User ID
        source: Source type (e.g., 'limitless')
        batch_size: Number of documents to delete per batch

    Returns:
        Number of deleted conversations
    """
    user_ref = db.collection('users').document(uid)
    conversations_ref = user_ref.collection(conversations_collection)

    total_deleted = 0

    while True:
        # Query for conversations with matching source
        query = conversations_ref.where(filter=FieldFilter('source', '==', source)).limit(batch_size)
        docs = list(query.stream())

        if not docs:
            break

        batch = db.batch()
        for doc in docs:
            batch.delete(doc.reference)
            total_deleted += 1
        batch.commit()

        if len(docs) < batch_size:
            break

    return total_deleted


@prepare_for_read(decrypt_func=_prepare_conversation_for_read)
@with_photos(get_conversation_photos)
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
@with_photos(get_conversation_photos)
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


def migrate_conversations_level_batch(uid: str, conversation_ids: List[str], target_level: str):
    """
    Migrates a batch of conversations to the target protection level, committing in batches of 450.
    """
    batch = db.batch()
    batch_count = 0
    conversations_ref = db.collection('users').document(uid).collection(conversations_collection)
    doc_refs = [conversations_ref.document(conv_id) for conv_id in conversation_ids]
    doc_snapshots = db.get_all(
        doc_refs, field_paths=['data_protection_level', 'transcript_segments', 'transcript_segments_compressed']
    )

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
            update_data['transcript_segments_compressed'] = prepared_payload.get(
                'transcript_segments_compressed', False
            )

        if not update_data.get('transcript_segments_compressed'):
            update_data['transcript_segments_compressed'] = firestore.DELETE_FIELD

        batch.update(doc_snapshot.reference, update_data)
        batch_count += 1
        if batch_count >= 100:
            batch.commit()
            batch = db.batch()
            batch_count = 0

        # Now migrate photos for this conversation in the same batch
        photos_ref = doc_snapshot.reference.collection('photos')
        photos_stream = photos_ref.select(['data_protection_level', 'base64']).stream()
        for photo_doc in photos_stream:
            photo_data = photo_doc.to_dict()
            current_photo_level = photo_data.get('data_protection_level', 'standard')
            if current_photo_level == target_level:
                continue

            # Decrypt first to get a clean state
            plain_photo_data = _prepare_photo_for_read(photo_data, uid)

            # Prepare the specific fields for update
            photo_update_payload = {'data_protection_level': target_level}
            if target_level == 'enhanced':
                photo_update_payload['base64'] = encryption.encrypt(plain_photo_data['base64'], uid)
            else:  # Moving from enhanced to standard
                photo_update_payload['base64'] = plain_photo_data['base64']

            # Add photo update to the batch
            batch.update(photo_doc.reference, photo_update_payload)
            batch_count += 1
            if batch_count >= 100:
                batch.commit()
                batch = db.batch()
                batch_count = 0

    if batch_count > 0:
        batch.commit()


# **************************************
# ********** STATUS *************
# **************************************


@prepare_for_read(decrypt_func=_prepare_conversation_for_read)
@with_photos(get_conversation_photos)
def get_in_progress_conversation(uid: str):
    user_ref = db.collection('users').document(uid)
    conversations_ref = (
        user_ref.collection(conversations_collection)
        .where(filter=FieldFilter('status', '==', 'in_progress'))
        .order_by('created_at', direction=firestore.Query.DESCENDING)
        .limit(1)
    )
    docs = [doc.to_dict() for doc in conversations_ref.stream()]
    conversation = docs[0] if docs else None
    return conversation


@prepare_for_read(decrypt_func=_prepare_conversation_for_read)
@with_photos(get_conversation_photos)
def get_in_progress_conversations(uid: str):
    """Get all in-progress conversations for a user, ordered by created_at descending."""
    user_ref = db.collection('users').document(uid)
    conversations_ref = (
        user_ref.collection(conversations_collection)
        .where(filter=FieldFilter('status', '==', 'in_progress'))
        .order_by('created_at', direction=firestore.Query.DESCENDING)
    )
    conversations = [doc.to_dict() for doc in conversations_ref.stream()]
    return conversations


@prepare_for_read(decrypt_func=_prepare_conversation_for_read)
@with_photos(get_conversation_photos)
def get_processing_conversations(uid: str):
    user_ref = db.collection('users').document(uid)
    conversations_ref = user_ref.collection(conversations_collection).where(
        filter=FieldFilter('status', '==', 'processing')
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


def get_action_items(
    uid: str,
    limit: int = 100,
    offset: int = 0,
    include_completed: bool = True,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
):
    """Fetch action items directly from conversations collection"""
    conversations_ref = db.collection('users').document(uid).collection(conversations_collection)

    # Only get completed conversations with action items
    conversations_ref = conversations_ref.where(filter=FieldFilter('status', '==', 'completed'))

    # Apply date range filters if provided
    if start_date:
        conversations_ref = conversations_ref.where(filter=FieldFilter('created_at', '>=', start_date))
    if end_date:
        conversations_ref = conversations_ref.where(filter=FieldFilter('created_at', '<=', end_date))

    # Sort by created_at descending
    conversations_ref = conversations_ref.order_by('created_at', direction=firestore.Query.DESCENDING)

    # Get all conversations with action items
    conversations = []
    for doc in conversations_ref.stream():
        conversation_data = doc.to_dict()

        # Check if conversation has action items
        structured = conversation_data.get('structured', {})
        raw_action_items = structured.get('action_items', [])

        if raw_action_items:
            # Decrypt conversation data for proper reading
            decrypted_data = _prepare_conversation_for_read(conversation_data, uid)
            conversations.append(decrypted_data)

    # Extract and flatten action items with metadata
    action_items = []
    for conversation in conversations:
        conversation_id = conversation['id']
        conversation_title = conversation.get('structured', {}).get('title', 'Untitled')
        conversation_created_at = _ensure_timezone_aware(conversation['created_at'])

        raw_items = conversation.get('structured', {}).get('action_items', [])

        for idx, item in enumerate(raw_items):
            # Skip deleted items
            if isinstance(item, dict) and item.get('deleted', False):
                continue

            # Skip completed items if not requested
            is_completed = False
            if isinstance(item, dict):
                is_completed = item.get('completed', False)

            if not include_completed and is_completed:
                continue

            # Handle backwards compatibility for dates
            created_at = None
            completed_at = None

            if isinstance(item, dict):
                created_at = item.get('created_at')
                completed_at = item.get('completed_at')

            # Ensure timezone awareness for action item dates
            if created_at is not None:
                created_at = _ensure_timezone_aware(created_at)
            if completed_at is not None:
                completed_at = _ensure_timezone_aware(completed_at)

            # Fallback to conversation created_at if dates are missing
            if created_at is None:
                created_at = conversation_created_at

            # If item is completed but no completed_at date, use conversation created_at
            if is_completed and completed_at is None:
                completed_at = conversation_created_at

            action_item_data = {
                'id': f"{conversation_id}_{idx}",
                'conversation_id': conversation_id,
                'conversation_title': conversation_title,
                'conversation_created_at': conversation_created_at,
                'index': idx,
                'description': item.get('description', item) if isinstance(item, dict) else item,
                'completed': is_completed,
                'deleted': item.get('deleted', False) if isinstance(item, dict) else False,
                'created_at': created_at,
                'completed_at': completed_at,
            }
            action_items.append(action_item_data)

    # Sort by newest first
    action_items.sort(key=lambda x: -x['conversation_created_at'].timestamp())

    # Apply pagination
    start_idx = offset
    end_idx = offset + limit

    return action_items[start_idx:end_idx]


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


def set_conversation_starred(uid: str, conversation_id: str, starred: bool):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.update({'starred': starred})


def unlock_all_conversations(uid: str):
    """
    Finds all conversations for a user with is_locked: True and updates them to is_locked = False.
    """
    conversations_ref = db.collection('users').document(uid).collection(conversations_collection)
    locked_conversations_query = conversations_ref.where(filter=FieldFilter('is_locked', '==', True))

    batch = db.batch()
    docs = locked_conversations_query.stream()
    count = 0
    for doc in docs:
        batch.update(doc.reference, {'is_locked': False})
        count += 1
        if count >= 499:  # Firestore batch limit is 500
            batch.commit()
            batch = db.batch()
            count = 0
    if count > 0:
        batch.commit()
    print(f"Unlocked all conversations for user {uid}")


def get_public_conversations(data: List[Tuple[str, str]]):
    """
    Fetches multiple public conversations sequentially.
    """
    conversations = []
    for uid, conversation_id in data:
        # get_conversation is already decorated to return a fully populated and decrypted conversation
        conversation_data = get_conversation(uid=uid, conversation_id=conversation_id)
        if conversation_data and conversation_data.get('visibility') == 'public':
            # Normalize apps_results and filter out invalid entries
            conversation_data['apps_results'] = _normalize_apps_results(
                conversation_data.get('apps_results')
            )
            conversations.append(conversation_data)
    return conversations


# ****************************************
# ********** POSTPROCESSING **************
# ****************************************


def set_postprocessing_status(
    uid: str,
    conversation_id: str,
    status: PostProcessingStatus,
    fail_reason: str = None,
    model: PostProcessingModel = PostProcessingModel.fal_whisperx,
):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.update(
        {'postprocessing.status': status, 'postprocessing.model': model, 'postprocessing.fail_reason': fail_reason}
    )


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
    uid: str, conversation_id: str, model_name: str, predictions: List[hume.HumeJobModelPredictionResponseModel]
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
        batch.set(
            prediction_ref,
            {
                "created_at": now,
                "start": prediction.time[0],
                "end": prediction.time[1],
                "emotions": json.dumps(hume.HumePredictionEmotionResponseModel.to_multi_dict(prediction.emotions)),
            },
        )
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

    conversation_snapshot = conversation_ref.get(field_paths=['data_protection_level'])
    level = 'standard'
    if conversation_snapshot.exists:
        level = conversation_snapshot.to_dict().get('data_protection_level', 'standard')

    photos_ref = conversation_ref.collection('photos')
    batch = db.batch()
    for photo in photos:
        photo_id = photo.id or str(uuid.uuid4())
        photo_ref = photos_ref.document(photo_id)
        data = photo.dict()
        data['id'] = photo_id
        prepared_data = _prepare_photo_for_write(data, uid, level)
        batch.set(photo_ref, prepared_data)
    batch.commit()


# ********************************
# ********** SYNCING *************
# ********************************


@prepare_for_read(decrypt_func=_prepare_conversation_for_read)
@with_photos(get_conversation_photos)
def get_closest_conversation_to_timestamps(uid: str, start_timestamp: int, end_timestamp: int) -> Optional[dict]:
    start_threshold = datetime.fromtimestamp(start_timestamp, tz=timezone.utc) - timedelta(minutes=2)
    end_threshold = datetime.fromtimestamp(end_timestamp, tz=timezone.utc) + timedelta(minutes=2)

    query = (
        db.collection('users')
        .document(uid)
        .collection(conversations_collection)
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
@with_photos(get_conversation_photos)
def get_last_completed_conversation(uid: str) -> Optional[dict]:
    query = (
        db.collection('users')
        .document(uid)
        .collection(conversations_collection)
        .where(filter=FieldFilter('status', '==', ConversationStatus.completed))
        .order_by('created_at', direction=firestore.Query.DESCENDING)
        .limit(1)
    )
    conversations = [doc.to_dict() for doc in query.stream()]
    conversation = conversations[0] if conversations else None
    return conversation
