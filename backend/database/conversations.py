import copy
import json
import logging
import uuid
import zlib
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any, Callable

from google.api_core.exceptions import AlreadyExists, Conflict, NotFound
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

import utils.other.hume as hume
from database import users as users_db
from models.audio_file import AudioFile
from models.conversation_enums import ConversationStatus, PostProcessingModel, PostProcessingStatus
from models.conversation_photo import ConversationPhoto
from models.transcript_segment import TranscriptSegment
from utils import encryption
from ._client import db, get_firestore_client
from .helpers import set_data_protection_level, prepare_for_write, prepare_for_read, with_photos
from utils.other.storage import list_audio_chunks

logger = logging.getLogger(__name__)

conversations_collection = 'conversations'


_LIFECYCLE_FIELDS = frozenset({'status', 'discarded'})
_PUBLIC_TRANSCRIPT_MAX_STORED_BYTES = 256 * 1024
_PUBLIC_TRANSCRIPT_MAX_DECODED_BYTES = 512 * 1024
_PUBLIC_TRANSCRIPT_MAX_SEGMENTS = 4096
_PUBLIC_TRANSCRIPT_MAX_SEGMENT_TEXT_CHARS = 24_000


def get_conversation_ids(uid: str) -> List[str]:
    """Return all conversation document IDs for a user without decrypting any fields.

    IDs-only projection (``select([])``) — used for bulk operations like account deletion where
    only the IDs are needed (e.g. to purge derived Pinecone vectors).
    """
    coll = db.collection('users').document(uid).collection(conversations_collection)
    return [doc.id for doc in coll.select([]).stream()]


def _ensure_timezone_aware(dt: datetime) -> datetime:
    """
    Ensure a datetime object is timezone-aware.
    If naive, assume UTC timezone.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _firestore_revision_datetime(value: Any) -> Optional[datetime]:
    """Normalize Firestore snapshot metadata to an aware API datetime.

    The production client exposes ``DatetimeWithNanoseconds`` (a datetime
    subclass), while Firestore emulators and fakes may expose protobuf-like
    ``seconds``/``nanos`` values. Keep that SDK variation at the database
    boundary so response models always receive the same public type.
    """
    if isinstance(value, datetime):
        return _ensure_timezone_aware(value)

    to_datetime = getattr(value, 'ToDatetime', None)
    if callable(to_datetime):
        try:
            return _ensure_timezone_aware(to_datetime(tzinfo=timezone.utc))
        except (TypeError, ValueError, OverflowError):
            return None

    try:
        seconds = getattr(value, 'seconds')
        nanos = getattr(value, 'nanos')
        if isinstance(seconds, str) and isinstance(nanos, str):
            timestamp = float(f'{seconds}.{nanos}')
        else:
            timestamp = float(seconds) + (float(nanos) / 1_000_000_000)
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (AttributeError, IndexError, TypeError, ValueError, OverflowError):
        return None


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
            logger.error(f"{e} {uid}")
            data['transcript_segments'] = []
    # backward compatibility, will be removed soon
    elif isinstance(data['transcript_segments'], bytes):
        try:
            compressed_bytes = data['transcript_segments']
            if data.get('transcript_segments_compressed'):
                decompressed_json = zlib.decompress(compressed_bytes).decode('utf-8')
                data['transcript_segments'] = json.loads(decompressed_json)
        except (json.JSONDecodeError, TypeError, zlib.error, ValueError) as e:
            logger.error(f"{e} {uid}")
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


def encode_conversation_for_write(
    uid: str, conversation_data: Dict[str, Any], level: str = 'standard'
) -> Dict[str, Any]:
    """Encode a conversation exactly as the write path stores it.

    The seam exists for harnesses that seed Firestore directly: a hand-written
    document with a plain ``transcript_segments`` list is a state production
    never writes, and seeding one hides encoding-aware guard bugs.
    """
    return _prepare_conversation_for_write(conversation_data, uid, level)


def _decode_transcript_segments_strict(uid: str, raw_segments: Any, compressed: bool) -> List[Any]:
    """Decode a stored ``transcript_segments`` blob, raising when it cannot be read.

    The read path swallows decode failures into an empty list, which is safe for
    rendering but unsafe for a caller deciding whether a conversation is empty.
    """
    if isinstance(raw_segments, list):
        return raw_segments
    if isinstance(raw_segments, str):
        payload = encryption.decrypt(raw_segments, uid)
        if compressed:
            return json.loads(zlib.decompress(bytes.fromhex(payload)).decode('utf-8'))
        return json.loads(payload)
    if isinstance(raw_segments, bytes) and compressed:
        return json.loads(zlib.decompress(raw_segments).decode('utf-8'))
    raise ValueError(f'undecodable transcript_segments: {type(raw_segments).__name__} compressed={compressed}')


def _decode_public_transcript_segments_bounded(
    uid: str,
    raw_segments: Any,
    *,
    compressed: bool,
    max_stored_bytes: int = _PUBLIC_TRANSCRIPT_MAX_STORED_BYTES,
    max_decoded_bytes: int = _PUBLIC_TRANSCRIPT_MAX_DECODED_BYTES,
    max_segments: int = _PUBLIC_TRANSCRIPT_MAX_SEGMENTS,
    max_segment_text_chars: int = _PUBLIC_TRANSCRIPT_MAX_SEGMENT_TEXT_CHARS,
    decompressor_factory: Callable[[], Any] = zlib.decompressobj,
) -> List[Dict[str, Any]]:
    """Decode only the bounded compressed transcript shape used by public chat."""

    def invalid() -> ValueError:
        return ValueError('invalid bounded public transcript')

    if (
        compressed is not True
        or max_stored_bytes <= 0
        or max_decoded_bytes <= 0
        or max_segments < 0
        or max_segment_text_chars < 0
    ):
        raise invalid()

    try:
        if isinstance(raw_segments, str):
            # Enhanced storage encrypts the hex-encoded compressed bytes. Check
            # the encoded representation before invoking the decryptor so a
            # malformed Firestore value cannot allocate without a fixed bound.
            max_encrypted_chars = (((max_stored_bytes * 2) + 28 + 2) // 3) * 4
            if not raw_segments.isascii() or len(raw_segments) > max_encrypted_chars:
                raise invalid()
            decrypted_hex = encryption.decrypt(raw_segments, uid)
            if len(decrypted_hex) > max_stored_bytes * 2 or len(decrypted_hex) % 2 != 0:
                raise invalid()
            compressed_bytes = bytes.fromhex(decrypted_hex)
        elif isinstance(raw_segments, (bytes, bytearray, memoryview)):
            if len(raw_segments) > max_stored_bytes:
                raise invalid()
            compressed_bytes = bytes(raw_segments)
        else:
            raise invalid()

        if len(compressed_bytes) > max_stored_bytes:
            raise invalid()

        decompressor = decompressor_factory()
        decoded = decompressor.decompress(compressed_bytes, max_decoded_bytes + 1)
        if (
            len(decoded) > max_decoded_bytes
            or decompressor.unconsumed_tail
            or not decompressor.eof
            or decompressor.unused_data
        ):
            raise invalid()

        parsed = json.loads(decoded.decode('utf-8'))
        if not isinstance(parsed, list) or len(parsed) > max_segments:
            raise invalid()

        safe_segments: List[Dict[str, Any]] = []
        for segment in parsed:
            if not isinstance(segment, Mapping):
                raise invalid()
            text = segment.get('text')
            if not isinstance(text, str) or len(text) > max_segment_text_chars:
                raise invalid()
            safe_segment: Dict[str, Any] = {'text': text}
            is_user = segment.get('is_user')
            if isinstance(is_user, bool):
                safe_segment['is_user'] = is_user
            speaker_id = segment.get('speaker_id')
            if isinstance(speaker_id, int) and not isinstance(speaker_id, bool):
                safe_segment['speaker_id'] = speaker_id
            safe_segments.append(safe_segment)
        return safe_segments
    except (json.JSONDecodeError, RecursionError, TypeError, UnicodeDecodeError, ValueError, zlib.error) as exc:
        if isinstance(exc, ValueError) and str(exc) == 'invalid bounded public transcript':
            raise
        raise invalid() from exc


def raw_conversation_has_content(uid: str, conversation: Dict[str, Any]) -> bool:
    """Decide whether an un-decoded Firestore snapshot holds user content.

    ``transcript_segments`` is written compressed (and encrypted for enhanced
    users), so an empty segment list is a non-empty blob on the raw document.
    Only the decoded value distinguishes an empty recording from a real one.
    Undecodable segments count as content: never delete data we cannot read.
    """
    if conversation.get('has_content') or conversation.get('photos'):
        return True
    raw_segments = conversation.get('transcript_segments')
    if not raw_segments:
        return False
    try:
        segments = _decode_transcript_segments_strict(
            uid, raw_segments, bool(conversation.get('transcript_segments_compressed'))
        )
    except (json.JSONDecodeError, TypeError, zlib.error, ValueError) as e:
        logger.error(f'raw_conversation_has_content: undecodable segments, assuming content. {uid} {e}')
        return True
    return bool(segments)


def _prepare_conversation_for_read(conversation_data: Optional[Dict[str, Any]], uid: str) -> Optional[Dict[str, Any]]:
    if not conversation_data:
        return None

    data = copy.deepcopy(conversation_data)
    # User titles are durable overrides. Conversation processing owns the
    # generated title, but must never erase an explicit user edit.
    user_title = data.get('user_title')
    if isinstance(user_title, str):
        structured = data.get('structured')
        if not isinstance(structured, dict):
            structured = {}
            data['structured'] = structured
        structured['title'] = user_title
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
                logger.error(e)
                pass

    return data


def _document_data_with_revision(document) -> Optional[Dict[str, Any]]:
    """Return Firestore document data with its canonical server revision."""
    data = document.to_dict()
    if data is None:
        return None
    revision = _firestore_revision_datetime(getattr(document, 'update_time', None))
    if revision is not None:
        data['updated_at'] = revision
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
def upsert_conversation_with_lifecycle(uid: str, conversation_data: dict):
    # `updated_at` is Firestore document metadata exposed by reads, never an
    # application-owned field to replay into a later write.
    conversation_data.pop('updated_at', None)
    if 'audio_base64_url' in conversation_data:
        del conversation_data['audio_base64_url']
    if 'photos' in conversation_data:
        del conversation_data['photos']

    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_data['id'])
    transaction = db.transaction()

    @firestore.transactional
    def _write_processing_result(transaction):
        write_data = copy.deepcopy(conversation_data)
        existing_snapshot = conversation_ref.get(transaction=transaction)
        if getattr(existing_snapshot, 'exists', False):
            existing = existing_snapshot.to_dict() or {}

            # Processing owns generated content, while these fields are explicitly
            # user-owned. The transaction retries if a concurrent mutation lands,
            # so an older in-memory Conversation cannot clobber that edit.
            # A null existing value means "never user-set" (stub docs dump None
            # fields), so only non-null values are preserved — otherwise the
            # stub's folder_id: None would revert every AI folder assignment.
            for field in ('starred', 'folder_id', 'visibility', 'user_title'):
                if existing.get(field) is not None:
                    write_data[field] = existing[field]

            # folder_id is user-owned even when explicitly cleared: the folder
            # move endpoints stamp folder_user_set, so "no folder" chosen by the
            # user (folder_id None + marker) must survive processing output.
            # Only a stub's never-user-touched None may be overwritten by the
            # AI folder assignment above.
            if existing.get('folder_user_set'):
                write_data['folder_id'] = existing.get('folder_id')

            user_title = existing.get('user_title')
            if isinstance(user_title, str):
                structured = write_data.get('structured')
                if not isinstance(structured, dict):
                    structured = {}
                    write_data['structured'] = structured
                structured['title'] = user_title

            transaction.set(conversation_ref, write_data, merge=True)
            return

        transaction.set(conversation_ref, write_data)

    _write_processing_result(transaction)


@set_data_protection_level(data_arg_name='conversation_data')
@prepare_for_write(
    data_arg_name='conversation_data',
    prepare_func=_prepare_conversation_for_write,
    preserve_result=True,
)
def persist_processing_result_with_lifecycle(
    uid: str,
    conversation_data: dict,
    *,
    expected_statuses: set[str],
) -> bool:
    """Persist a processor result only while its lifecycle generation remains current.

    A processor works from an in-memory snapshot.  This transaction fences that
    snapshot against a concurrent discard, delete, or terminal transition before
    merging generated content back into the conversation document.
    """
    conversation_data.pop('updated_at', None)
    if 'audio_base64_url' in conversation_data:
        del conversation_data['audio_base64_url']
    if 'photos' in conversation_data:
        del conversation_data['photos']

    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_data['id'])
    transaction = db.transaction()

    @firestore.transactional
    def _persist(transaction) -> bool:
        write_data = copy.deepcopy(conversation_data)
        existing_snapshot = conversation_ref.get(transaction=transaction)
        if not getattr(existing_snapshot, 'exists', False):
            # A processor is never an authority to recreate a conversation.
            # Treat deletion as the same terminal fence as a discard so a
            # finalizer cannot resurrect it and emit derived side effects.
            return False

        existing = existing_snapshot.to_dict() or {}
        if existing.get('discarded') or existing.get('status') not in expected_statuses:
            return False

        # Generated processing content never owns user-managed fields.
        # A null existing value means "never user-set" (stub docs dump None
        # fields), so only non-null values are preserved — otherwise the
        # stub's folder_id: None would revert every AI folder assignment.
        for field in ('starred', 'folder_id', 'visibility', 'user_title'):
            if existing.get(field) is not None:
                write_data[field] = existing[field]

        # folder_id is user-owned even when explicitly cleared: the folder
        # move endpoints stamp folder_user_set, so "no folder" chosen by the
        # user (folder_id None + marker) must survive processing output.
        # Only a stub's never-user-touched None may be overwritten by the
        # AI folder assignment above.
        if existing.get('folder_user_set'):
            write_data['folder_id'] = existing.get('folder_id')

        user_title = existing.get('user_title')
        if isinstance(user_title, str):
            structured = write_data.get('structured')
            if not isinstance(structured, dict):
                structured = {}
                write_data['structured'] = structured
            structured['title'] = user_title

        transaction.set(conversation_ref, write_data, merge=True)
        return True

    return _persist(transaction)


@set_data_protection_level(data_arg_name='conversation_data')
@prepare_for_write(
    data_arg_name='conversation_data',
    prepare_func=_prepare_conversation_for_write,
    preserve_result=True,
)
def create_conversation_if_absent_with_lifecycle(uid: str, conversation_data: dict) -> bool:
    """Atomically create a conversation document if it does not already exist."""
    conversation_data.pop('updated_at', None)
    if 'audio_base64_url' in conversation_data:
        del conversation_data['audio_base64_url']
    if 'photos' in conversation_data:
        del conversation_data['photos']

    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_data['id'])
    try:
        conversation_ref.create(conversation_data)
        return True
    except (AlreadyExists, Conflict):
        return False


@prepare_for_read(decrypt_func=_prepare_conversation_for_read)
@with_photos(get_conversation_photos)
def get_conversation(uid, conversation_id):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_data = _document_data_with_revision(conversation_ref.get())
    return conversation_data


def get_public_shared_conversation_bounded(
    uid: str,
    conversation_id: str,
    *,
    firestore_client: Any = None,
) -> Optional[Dict[str, Any]]:
    """Read only public-chat fields and decode the transcript within fixed bounds."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    conversation_ref = (
        client.collection('users').document(uid).collection(conversations_collection).document(conversation_id)
    )
    snapshot = conversation_ref.get(
        field_paths=[
            'visibility',
            'is_locked',
            'transcript_segments_compressed',
            'transcript_segments',
        ]
    )
    if not snapshot.exists:
        return None
    raw = snapshot.to_dict()
    if not isinstance(raw, dict):
        return None

    visibility = raw.get('visibility')
    is_locked = raw.get('is_locked', False)
    public_conversation: Dict[str, Any] = {
        'visibility': visibility,
        'is_locked': is_locked,
    }
    if not isinstance(visibility, str) or visibility not in {'shared', 'public'} or is_locked:
        return public_conversation

    try:
        public_conversation['transcript_segments'] = _decode_public_transcript_segments_bounded(
            uid,
            raw.get('transcript_segments'),
            compressed=raw.get('transcript_segments_compressed') is True,
        )
    except ValueError:
        return None
    return public_conversation


def get_conversation_audio_stamp(uid: str, conversation_id: str) -> Optional[dict]:
    """Field-masked read of just the conversation_audio stamp — cheap enough for
    the pusher's per-batch staleness check (the full doc carries transcripts)."""
    doc_ref = db.collection('users').document(uid).collection(conversations_collection).document(conversation_id)
    snapshot = doc_ref.get(field_paths=['conversation_audio'])
    if not snapshot.exists:
        return None
    return (snapshot.to_dict() or {}).get('conversation_audio')


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
    date_field: str = 'created_at',
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
        conversations_ref = conversations_ref.where(filter=FieldFilter(date_field, '>=', start_date))
    if end_date:
        conversations_ref = conversations_ref.where(filter=FieldFilter(date_field, '<=', end_date))

    # Sort — must match the range-filter field to satisfy Firestore index requirements
    sort_field = date_field if (start_date or end_date) else 'created_at'
    conversations_ref = conversations_ref.order_by(sort_field, direction=firestore.Query.DESCENDING)

    # Limits
    conversations_ref = conversations_ref.limit(limit).offset(offset)

    conversations = [_document_data_with_revision(doc) for doc in conversations_ref.stream()]
    conversations = [conversation for conversation in conversations if conversation is not None]
    return conversations


def get_conversations_count(
    uid: str,
    include_discarded: bool = False,
    statuses: Optional[List[str]] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    categories: Optional[List[str]] = None,
    folder_id: Optional[str] = None,
    starred: Optional[bool] = None,
    sources: Optional[List[str]] = None,
):
    conversations_ref = db.collection('users').document(uid).collection(conversations_collection)
    if not include_discarded:
        conversations_ref = conversations_ref.where(filter=FieldFilter('discarded', '==', False))
    if sources:
        conversations_ref = conversations_ref.where(filter=FieldFilter('source', 'in', sources))
    if statuses:
        conversations_ref = conversations_ref.where(filter=FieldFilter('status', 'in', statuses))
    if categories:
        conversations_ref = conversations_ref.where(filter=FieldFilter('structured.category', 'in', categories))
    if folder_id:
        conversations_ref = conversations_ref.where(filter=FieldFilter('folder_id', '==', folder_id))
    if starred is not None:
        conversations_ref = conversations_ref.where(filter=FieldFilter('starred', '==', starred))
    if start_date:
        conversations_ref = conversations_ref.where(filter=FieldFilter('created_at', '>=', start_date))
    if end_date:
        conversations_ref = conversations_ref.where(filter=FieldFilter('created_at', '<=', end_date))
    result = conversations_ref.count().get()
    return int(result[0][0].value)


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
    folder_id: Optional[str] = None,
    starred: Optional[bool] = None,
):
    """
    Same as get_conversations but without loading photos.
    Much faster for list endpoints and bulk operations where full photo base64 isn't needed.
    """
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

    conversations = [_document_data_with_revision(doc) for doc in conversations_ref.stream()]
    conversations = [conversation for conversation in conversations if conversation is not None]
    return conversations


def iter_all_conversations(uid: str, batch_size: int = 400, include_discarded: bool = True):
    """Yield all conversations for a user, decrypted, in batches. Used for streaming data export."""
    conversations_ref = db.collection('users').document(uid).collection(conversations_collection)
    if not include_discarded:
        conversations_ref = conversations_ref.where(filter=FieldFilter('discarded', '==', False))
    conversations_ref = conversations_ref.order_by('created_at', direction=firestore.Query.DESCENDING)
    offset = 0
    while True:
        batch_ref = conversations_ref.limit(batch_size).offset(offset)
        batch = []
        for doc in batch_ref.stream():
            conv = doc.to_dict()
            conv = _prepare_conversation_for_read(conv, uid) or conv
            batch.append(conv)
        yield from batch
        if len(batch) < batch_size:
            break
        offset += batch_size


def update_conversation(uid: str, conversation_id: str, update_data: dict):
    lifecycle_fields = _LIFECYCLE_FIELDS.intersection(update_data)
    if lifecycle_fields:
        raise ValueError(
            'lifecycle fields may only be changed through utils.conversations.lifecycle: '
            + ', '.join(sorted(lifecycle_fields))
        )
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

    # Group chunks based on gap rule (90s threshold accommodates both 5s and 60s chunk durations)
    audio_files = []
    current_group = []
    gap_threshold = 90  # seconds — must exceed max chunk duration (60s) to avoid false splits

    for i, chunk in enumerate(chunks):
        if not current_group:
            current_group.append(chunk)
        else:
            # Check if there's a gap between chunks exceeding the threshold
            prev_chunk = current_group[-1]
            time_gap = chunk['timestamp'] - prev_chunk['timestamp']
            if time_gap > gap_threshold:
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

    # Calculate started_at and duration from timestamps and blob sizes
    started_at = datetime.fromtimestamp(chunk_group[0]['timestamp'], tz=timezone.utc)
    last_chunk_start = datetime.fromtimestamp(chunk_group[-1]['timestamp'], tz=timezone.utc)
    # Estimate last chunk duration from blob size (PCM16 mono at 16kHz = 32000 bytes/sec).
    # Approximate for opus-encoded blobs; conversation_audio.captured_duration (from
    # decoded PCM) is the display source of truth.
    last_chunk_size = chunk_group[-1].get('size', 0)
    last_chunk_duration = last_chunk_size / 32000.0 if last_chunk_size > 0 else 5.0
    duration = (last_chunk_start - started_at).total_seconds() + last_chunk_duration

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

    conversation_ref.update({'structured.title': title, 'user_title': title})


def update_conversation_summary(uid: str, conversation_id: str, app_id: Optional[str], content: str) -> str:
    """
    Update the conversation's displayed summary.

    If app_id is None: writes to structured.overview (default backend overview).
    If app_id is set: rewrites the matching apps_results entry's content.

    Returns:
        'ok' on success, 'not_found' if conversation missing,
        'app_result_not_found' if app_id given but no matching apps_results entry.
    """
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)

    doc_snapshot = conversation_ref.get()
    if not doc_snapshot.exists:
        return 'not_found'

    if app_id is None:
        conversation_ref.update({'structured.overview': content})
        return 'ok'

    raw = doc_snapshot.to_dict() or {}
    apps_results = list(raw.get('apps_results') or [])
    found = False
    for entry in apps_results:
        if isinstance(entry, dict) and entry.get('app_id') == app_id:
            entry['content'] = content
            found = True
            break
    if not found:
        return 'app_result_not_found'

    conversation_ref.update({'apps_results': apps_results})
    return 'ok'


def update_conversation_segment_text(uid: str, conversation_id: str, segment_id: str, text: str) -> str:
    """
    Update a single segment's text in a conversation.

    The read-modify-write runs in a Firestore transaction so concurrent edits
    (e.g. the same conversation open in two tabs) can't lose-update each other.
    Without it, two edits that both read the pre-edit transcript_segments array
    and each rewrite the whole array clobber one another — the later write wins
    and silently drops the earlier edit.

    Returns:
        'ok' on success, 'not_found' if conversation missing, 'locked' if conversation is locked,
        'segment_not_found' if segment_id not found.
    """
    doc_ref = db.collection('users').document(uid).collection(conversations_collection).document(conversation_id)
    transaction = db.transaction()

    @firestore.transactional
    def _update_segment_text(transaction) -> str:
        doc_snapshot = doc_ref.get(transaction=transaction)
        if not doc_snapshot.exists:
            return 'not_found'

        raw_data = doc_snapshot.to_dict()
        if raw_data.get('is_locked', False):
            return 'locked'

        conversation_data = _prepare_conversation_for_read(raw_data, uid)
        if not conversation_data:
            return 'not_found'

        segments = conversation_data.get('transcript_segments', [])
        found = False
        for segment in segments:
            if isinstance(segment, dict) and segment.get('id') == segment_id:
                segment['text'] = text
                found = True
                break

        if not found:
            return 'segment_not_found'

        doc_level = conversation_data.get('data_protection_level', 'standard')
        prepared_payload = _prepare_conversation_for_write({'transcript_segments': segments}, uid, doc_level)
        transaction.update(doc_ref, prepared_payload)
        return 'ok'

    return _update_segment_text(transaction)


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


@prepare_for_read(decrypt_func=_prepare_conversation_for_read)
@with_photos(get_conversation_photos)
def get_conversations_by_id(uid, conversation_ids, include_discarded: bool = False):
    return _get_conversations_by_id(uid, conversation_ids, include_discarded=include_discarded)


@prepare_for_read(decrypt_func=_prepare_conversation_for_read)
def get_conversations_by_id_without_photos(uid, conversation_ids, include_discarded: bool = False):
    return _get_conversations_by_id(uid, conversation_ids, include_discarded=include_discarded)


def _get_conversations_by_id(uid, conversation_ids, include_discarded: bool = False):
    user_ref = db.collection('users').document(uid)
    conversations_ref = user_ref.collection(conversations_collection)

    doc_refs = [conversations_ref.document(str(conversation_id)) for conversation_id in conversation_ids]
    docs = db.get_all(doc_refs)

    conversations_by_id = {}
    for doc in docs:
        if doc.exists:
            data = doc.to_dict()
            if data.get('discarded') and not include_discarded:
                continue
            data.setdefault('id', doc.id)
            conversations_by_id[str(data['id'])] = data

    return [
        conversations_by_id[str(conversation_id)]
        for conversation_id in conversation_ids
        if str(conversation_id) in conversations_by_id
    ]


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
            logger.warning(f"Conversation {doc_snapshot.id} not found, skipping.")
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
def get_processing_conversations(uid: str):
    user_ref = db.collection('users').document(uid)
    conversations_ref = user_ref.collection(conversations_collection).where(
        filter=FieldFilter('status', '==', 'processing')
    )
    conversations = [doc.to_dict() for doc in conversations_ref.stream()]
    # Exclude lazy-deferred conversations: they intentionally sit in `processing` (no LLM summary
    # yet) until the user opens them, where they're enriched on demand. They must NOT be swept
    # back to pusher for background processing — that would defeat the freemium cost saving.
    conversations = [c for c in conversations if not c.get('deferred')]
    return conversations


def transition_conversation_status(uid: str, conversation_id: str, status: str):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.update({'status': status})


def claim_conversation_status(
    uid: str,
    conversation_id: str,
    expected_status: ConversationStatus,
    claimed_status: ConversationStatus,
    extra_updates: Optional[Dict[str, Any]] = None,
) -> bool:
    """Atomically transition a conversation status when the current status matches."""
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    transaction = db.transaction()

    @firestore.transactional
    def _claim(transaction):
        snapshot = conversation_ref.get(transaction=transaction)
        if not snapshot.exists:
            raise NotFound(f'Conversation {conversation_id} not found')
        current = snapshot.to_dict() or {}
        if current.get('discarded') or current.get('status') != expected_status.value:
            return False
        updates = {'status': claimed_status.value}
        if extra_updates:
            updates.update(extra_updates)
        transaction.update(conversation_ref, updates)
        return True

    claimed = _claim(transaction)
    return claimed


def set_conversation_as_discarded(uid: str, conversation_id: str):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.update({'discarded': True})


def restore_conversation_from_discarded(uid: str, conversation_id: str):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.update({'discarded': False})


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


def update_conversation_segments(
    uid: str,
    conversation_id: str,
    segments: List[dict],
    finished_at: datetime = None,
    data_protection_level: str = None,
    *,
    started_at: datetime = None,
    firestore_client: Any = None,
):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    doc_ref = client.collection('users').document(uid).collection(conversations_collection).document(conversation_id)
    transaction = client.transaction()

    @firestore.transactional
    def _write_segments(transaction) -> bool:
        doc_snapshot = doc_ref.get(transaction=transaction)
        if not getattr(doc_snapshot, 'exists', False):
            return False
        current = doc_snapshot.to_dict() or {}
        doc_level = data_protection_level or current.get('data_protection_level', 'standard')
        update_payload = {
            'transcript_segments': segments,
            # Once a live generation has received content, empty cleanup must
            # never reclaim it even if an older in-memory snapshot is empty.
            'has_content': bool(current.get('has_content')) or bool(segments),
        }
        if finished_at:
            update_payload['finished_at'] = finished_at
        if started_at:
            update_payload['started_at'] = started_at
        prepared_payload = _prepare_conversation_for_write(update_payload, uid, doc_level)
        transaction.update(doc_ref, prepared_payload)
        return True

    return _write_segments(transaction)


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
    logger.info(f"Unlocked all conversations for user {uid}")


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
        batch.set(segment_ref, segment.model_dump())
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

    # Sort each provider's segments by start time, tolerating a legacy/partial doc missing 'start'
    # (a bare x['start'] would KeyError and 500 the whole transcripts response).
    return {
        'deepgram': list(sorted([doc.to_dict() for doc in deepgram_ref.stream()], key=lambda x: x.get('start', 0))),
        'soniox': list(sorted([doc.to_dict() for doc in soniox_ref.stream()], key=lambda x: x.get('start', 0))),
        'speechmatics': list(
            sorted([doc.to_dict() for doc in speechmatics_ref.stream()], key=lambda x: x.get('start', 0))
        ),
        'whisperx': list(sorted([doc.to_dict() for doc in whisperx_ref.stream()], key=lambda x: x.get('start', 0))),
    }


# ***********************************
# ********** OPENGLASS **************
# ***********************************


def store_conversation_photos(
    uid: str,
    conversation_id: str,
    photos: List[ConversationPhoto],
    *,
    firestore_client: Any = None,
) -> bool:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    user_ref = client.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    photos_ref = conversation_ref.collection('photos')
    transaction = client.transaction()

    @firestore.transactional
    def _store(transaction) -> bool:
        conversation_snapshot = conversation_ref.get(transaction=transaction)
        if not getattr(conversation_snapshot, 'exists', False):
            return False
        level = (conversation_snapshot.to_dict() or {}).get('data_protection_level', 'standard')
        for photo in photos:
            photo_id = photo.id or str(uuid.uuid4())
            photo_ref = photos_ref.document(photo_id)
            data = photo.model_dump()
            data['id'] = photo_id
            transaction.set(photo_ref, _prepare_photo_for_write(data, uid, level))
        transaction.update(conversation_ref, {'has_content': True})
        return True

    return _store(transaction)


# ********************************
# ********** SYNCING *************
# ********************************


def eligible_merge_target(conversation: Optional[dict]) -> bool:
    """Whether synced audio may merge into this conversation (#10033).

    A soft-deleted tombstone must never absorb new segments: the user cannot
    see it, so merged audio disappears — recordings that "never create a
    conversation". Discarded rows stay eligible; the merge path reprocesses
    and revives them.
    """
    return bool(conversation) and not conversation.get('deleted')


def select_closest_conversation(conversations, start_timestamp: int, end_timestamp: int) -> Optional[dict]:
    """Pure closest-by-boundary choice among eligible merge targets (#10033)."""
    closest_conversation = None
    min_diff = float('inf')
    for conversation in conversations:
        if not eligible_merge_target(conversation):
            continue
        conversation_start_timestamp = conversation['started_at'].timestamp()
        conversation_end_timestamp = conversation['finished_at'].timestamp()
        diff1 = abs(conversation_start_timestamp - start_timestamp)
        diff2 = abs(conversation_end_timestamp - end_timestamp)
        if diff1 < min_diff or diff2 < min_diff:
            min_diff = min(diff1, diff2)
            closest_conversation = conversation
    return closest_conversation


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
    logger.info(f'get_closest_conversation_to_timestamps len(conversations) {len(conversations)}')
    if not conversations:
        return None

    logger.info('get_closest_conversation_to_timestamps found:')
    for conversation in conversations:
        logger.info(f"- {conversation['id']} {conversation['started_at']} {conversation['finished_at']}")

    closest_conversation = select_closest_conversation(conversations, start_timestamp, end_timestamp)
    if closest_conversation is None:
        logger.info('get_closest_conversation_to_timestamps: no eligible merge target (deleted rows excluded)')
        return None

    logger.info(f"get_closest_conversation_to_timestamps closest_conversation: {closest_conversation['id']}")
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
