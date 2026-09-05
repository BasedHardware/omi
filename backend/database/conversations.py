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
from models.audio_file import AudioFile
from models.client_processing import PROJECTION_FAMILY_FIELDS
from models.conversation_enums import ConversationStatus, PostProcessingModel, PostProcessingStatus
from models.conversation_photo import ConversationPhoto
from models.transcript_segment import TranscriptSegment
from utils import encryption
from utils.conversations.transcript_hash import (
    canonicalize_transcript_segments_for_storage,
    transcript_sha256_for_binding,
)
from ._client import db, delete_collection_recursive, get_firestore_client, run_transactional
from .firestore_index_registry import MCP_CONVERSATION_CARD_QUERY_SPECS, STALE_IN_PROGRESS_CONVERSATIONS_QUERY
from .firestore_read_metrics import FirestoreReadOutcome, FirestoreReadSite, record_document_read
from .helpers import set_data_protection_level, prepare_for_write, prepare_for_read, with_photos
from utils.other.list_budget import ListReadBudget, ListReadBudgetExhausted, budgeted_stream_iter
from utils.other.storage import list_audio_chunks
from .first_open_obligations import (
    FIRST_OPEN_EFFECTS,
    claim_authorized_first_open_work,
    claim_first_open_work,
    commit_first_open_app_result,
    commit_first_open_app_usage,
    commit_first_open_conversation_patch,
    commit_first_open_folder_count,
    complete_first_open_effect,
    finish_first_open_work,
    first_open_effect_is_authorized,
    initialize_first_open_work,
)

logger = logging.getLogger(__name__)

conversations_collection = 'conversations'

_LIFECYCLE_FIELDS = frozenset({'status', 'discarded'})
_PUBLIC_TRANSCRIPT_MAX_STORED_BYTES = 256 * 1024
_PUBLIC_TRANSCRIPT_MAX_DECODED_BYTES = 512 * 1024
_PUBLIC_TRANSCRIPT_MAX_SEGMENTS = 4096
_PUBLIC_TRANSCRIPT_MAX_SEGMENT_TEXT_CHARS = 24_000
_MCP_CONVERSATION_CARD_FIELD_PATHS = (
    'id',
    'discarded',
    'created_at',
    'started_at',
    'finished_at',
    'language',
    'is_locked',
    'data_protection_level',
    'user_title',
    'structured.title',
    'structured.overview',
    'structured.category',
    'structured.emoji',
)
_MCP_CONVERSATION_TRANSCRIPT_FIELD_PATHS = _MCP_CONVERSATION_CARD_FIELD_PATHS + (
    'transcript_segments',
    'transcript_segments_compressed',
)


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
        data['transcript_segments'] = canonicalize_transcript_segments_for_storage(data['transcript_segments'])
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


def _require_segment_list(parsed: Any) -> List[Any]:
    if not isinstance(parsed, list):
        raise ValueError(f'undecodable transcript_segments: parsed {type(parsed).__name__}')
    return parsed


def _decode_transcript_segments_strict(uid: str, raw_segments: Any, compressed: bool) -> List[Any]:
    """Decode a stored ``transcript_segments`` blob, raising when it cannot be read.

    The read path swallows decode failures into an empty list, which is safe for
    rendering but unsafe for a caller deciding whether a conversation is empty
    or whether a client projection may bind to it. Binding is authorization,
    not display: an unreadable blob must not become ``[]``.
    """
    if isinstance(raw_segments, list):
        return raw_segments
    if isinstance(raw_segments, str):
        payload = encryption.decrypt(raw_segments, uid)
        if compressed:
            parsed = json.loads(zlib.decompress(bytes.fromhex(payload)).decode('utf-8'))
        else:
            parsed = json.loads(payload)
        return _require_segment_list(parsed)
    if isinstance(raw_segments, bytes) and compressed:
        return _require_segment_list(json.loads(zlib.decompress(raw_segments).decode('utf-8')))
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


def prepare_photo_for_write(data: Dict[str, Any], uid: str, level: str) -> Dict[str, Any]:
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


def iter_all_conversation_photos(uid: str):
    start_key = db.document(f'users/{uid}/conversations/ /photos/ ')
    end_key = db.document(f'users/{uid}/conversations//photos/')
    query = (
        db.collection_group('photos')
        .where(filter=FieldFilter('__name__', '>=', start_key))
        .where(filter=FieldFilter('__name__', '<=', end_key))
    )
    for doc in query.stream():
        # Path format: users/{uid}/conversations/{conversation_id}/photos/{photo_id}
        parts = doc.reference.path.split('/')
        if len(parts) >= 6 and parts[-2] == 'photos' and parts[-4] == 'conversations':
            conversation_id = parts[-3]
            yield conversation_id, doc.to_dict()


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

        write_data.setdefault('has_photos', False)
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
) -> bool:
    """Merge a processor result into its conversation.

    Only deletion is refused.  Lifecycle state is not: a discard is the system's
    own verdict that a conversation held nothing, and a status is bookkeeping
    about which generation ran, and every processor re-derives what it writes
    from the content in front of it.  Fencing on either stranded conversations a
    later sync had filled with speech — transcribed, untitled, and invisible to
    their owner — to prevent races that had never been observed.
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
            # Deleting one is a decision its owner made, and a merge write to a
            # missing document would create it, so a late processor could bring
            # back what they removed and emit derived side effects from it.
            return False

        existing = existing_snapshot.to_dict() or {}

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
    conversation_data.setdefault('has_photos', False)

    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_data['id'])
    try:
        conversation_ref.create(conversation_data)
        return True
    except (AlreadyExists, Conflict):
        return False


@prepare_for_read(decrypt_func=_prepare_conversation_for_read)
@with_photos(get_conversation_photos)
def get_conversation(uid, conversation_id, *, read_site: FirestoreReadSite = FirestoreReadSite.UNATTRIBUTED):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_data = _document_data_with_revision(conversation_ref.get())
    record_document_read(
        read_site, FirestoreReadOutcome.HIT if conversation_data is not None else FirestoreReadOutcome.MISS
    )
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
        # The archive's `sources=omi` must compose with the multi-status `in`
        # filter below. Firestore allows only one disjunctive `in` filter per
        # query, so a singleton source is an equality predicate, not a
        # degenerate `in` predicate.
        if len(sources) == 1:
            conversations_ref = conversations_ref.where(filter=FieldFilter('source', '==', sources[0]))
        else:
            conversations_ref = conversations_ref.where(filter=FieldFilter('source', 'in', sources))
    if statuses:
        if len(statuses) == 1:
            conversations_ref = conversations_ref.where(filter=FieldFilter('status', '==', statuses[0]))
        else:
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
    sources: Optional[List[str]] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    categories: Optional[List[str]] = None,
    folder_id: Optional[str] = None,
    starred: Optional[bool] = None,
    budget: Optional[ListReadBudget] = None,
):
    """
    Same as get_conversations but without loading photos.
    Much faster for list endpoints and bulk operations where full photo base64 isn't needed.

    With a request ``budget`` (#11831) the server-side ``offset()`` is charged
    before the query — Firestore bills and streams every skipped row, so a
    large offset consumes real read work — and the page's stream runs under
    the budget's per-RPC timeout with each fetched row charged. An offset
    that exhausts the allowance returns an empty, explicitly truncated page
    instead of pretending to be complete.
    """
    conversations_ref = db.collection('users').document(uid).collection(conversations_collection)
    if not include_discarded:
        conversations_ref = conversations_ref.where(filter=FieldFilter('discarded', '==', False))
    if sources:
        # Keep the paginated list semantically identical to the count query;
        # see `get_conversations_count` for why a singleton is equality.
        if len(sources) == 1:
            conversations_ref = conversations_ref.where(filter=FieldFilter('source', '==', sources[0]))
        else:
            conversations_ref = conversations_ref.where(filter=FieldFilter('source', 'in', sources))
    if len(statuses) > 0:
        if len(statuses) == 1:
            conversations_ref = conversations_ref.where(filter=FieldFilter('status', '==', statuses[0]))
        else:
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

    if budget is not None and offset > 0:
        # Charge the skipped prefix before querying: Firestore streams (and
        # bills) every offset row even though none is yielded here.
        try:
            budget.charge(offset)
        except ListReadBudgetExhausted:
            return []

    # Limits
    conversations_ref = conversations_ref.limit(limit).offset(offset)

    conversations = []
    try:
        for doc in budgeted_stream_iter(conversations_ref, budget):
            conversations.append(_document_data_with_revision(doc))
    except ListReadBudgetExhausted:
        # Deadline or allowance ended mid-page: rows already fetched stay in
        # the list as an honest created_at-DESC prefix; the budget remains
        # flagged truncated so the route marks the response (#11831).
        pass
    conversations = [conversation for conversation in conversations if conversation is not None]
    return conversations


@prepare_for_read(decrypt_func=_prepare_conversation_for_read)
def get_mcp_conversation_cards(
    uid: str,
    limit: int,
    offset: int,
    *,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    categories: Optional[List[str]] = None,
    firestore_client: Any = None,
) -> List[Dict[str, Any]]:
    """Return the transcript-free Firestore projection used by hosted MCP lists."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    collection = client.collection('users').document(uid).collection(conversations_collection)
    query_spec = MCP_CONVERSATION_CARD_QUERY_SPECS[(bool(categories), start_date is not None, end_date is not None)]
    query = query_spec.build(
        collection,
        {
            'discarded': False,
            'status': 'completed',
            'categories': categories,
            'start_date': start_date,
            'end_date': end_date,
        },
        field_filter_factory=FieldFilter,
    )
    query = (
        query.order_by('created_at', direction=firestore.Query.DESCENDING)
        .select(list(_MCP_CONVERSATION_CARD_FIELD_PATHS))
        .limit(limit)
        .offset(offset)
    )
    conversations: List[Dict[str, Any]] = []
    for doc in query.stream():
        conversation = _document_data_with_revision(doc)
        if conversation is None:
            continue
        conversation.setdefault('id', doc.id)
        conversations.append(conversation)
    return conversations


@prepare_for_read(decrypt_func=_prepare_conversation_for_read)
def get_mcp_conversations_by_id(
    uid: str,
    conversation_ids: List[str],
    *,
    include_transcript: bool,
    include_discarded: bool = False,
    firestore_client: Any = None,
) -> List[Dict[str, Any]]:
    """Return MCP card fields, optionally with transcript blobs, without photos or other result payloads."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    conversations_ref = client.collection('users').document(uid).collection(conversations_collection)
    doc_refs = [conversations_ref.document(str(conversation_id)) for conversation_id in conversation_ids]
    field_paths = _MCP_CONVERSATION_TRANSCRIPT_FIELD_PATHS if include_transcript else _MCP_CONVERSATION_CARD_FIELD_PATHS
    docs = client.get_all(doc_refs, field_paths=list(field_paths))
    conversations_by_id: Dict[str, Dict[str, Any]] = {}
    for doc in docs:
        if not doc.exists:
            continue
        data = _document_data_with_revision(doc)
        if data is None:
            continue
        if data.get('discarded') and not include_discarded:
            continue
        data.setdefault('id', doc.id)
        conversations_by_id[str(data['id'])] = data
    return [
        conversations_by_id[str(conversation_id)]
        for conversation_id in conversation_ids
        if str(conversation_id) in conversations_by_id
    ]


def iter_all_conversations(uid: str, batch_size: int = 400, include_discarded: bool = True):
    """Yield all conversations for a user, decrypted, in batches. Used for streaming data export."""
    conversations_ref = db.collection('users').document(uid).collection(conversations_collection)
    if not include_discarded:
        conversations_ref = conversations_ref.where(filter=FieldFilter('discarded', '==', False))
    conversations_ref = conversations_ref.order_by('created_at', direction=firestore.Query.DESCENDING)
    cursor = None
    while True:
        batch_ref = conversations_ref.limit(batch_size)
        if cursor is not None:
            batch_ref = batch_ref.start_after(cursor)
        batch = []
        snapshots = list(batch_ref.stream())
        for doc in snapshots:
            conv = doc.to_dict()
            conv = _prepare_conversation_for_read(conv, uid) or conv
            batch.append(conv)
        yield from batch
        if len(snapshots) < batch_size:
            break
        cursor = snapshots[-1]


def update_conversation(uid: str, conversation_id: str, update_data: dict) -> bool:
    """Apply ``update_data`` to a conversation.

    Returns False when the conversation no longer exists, so callers that keep
    producing work for it (e.g. the pusher's private-cloud audio sync) can stop
    instead of writing into a deleted owner.
    """
    lifecycle_fields = _LIFECYCLE_FIELDS.intersection(update_data)
    if lifecycle_fields:
        raise ValueError(
            'lifecycle fields may only be changed through utils.conversations.lifecycle: '
            + ', '.join(sorted(lifecycle_fields))
        )
    doc_ref = db.collection('users').document(uid).collection(conversations_collection).document(conversation_id)
    doc_snapshot = doc_ref.get()
    if not doc_snapshot.exists:
        return False

    doc_level = doc_snapshot.to_dict().get('data_protection_level', 'standard')
    prepared_data = _prepare_conversation_for_write(update_data, uid, doc_level)
    try:
        doc_ref.update(prepared_data)
    except NotFound:
        # The conversation was deleted between the existence read above and
        # this commit. The contract of this function is to report a gone owner
        # as False — not to raise — so callers like the pusher's private-cloud
        # audio sync take their designed gone-owner path (stop syncing, release
        # the audio budget) instead of logging an ERROR and retrying forever.
        return False
    return True


def try_claim_conversation_memory_analytics(uid: str, conversation_id: str, firestore_client: Any = None) -> bool:
    """Atomically claim the one analytics success slot for a conversation.

    The marker lives in Firestore under the authoritative conversation document,
    rather than in a best-effort cache. ``create`` is atomic: the caller that
    creates the marker is the only caller allowed to capture the optional
    analytics event; an existing marker means a retry/re-finalization must not
    emit again. It deliberately has no TTL, so Redis loss, cache eviction, and
    arbitrary retry windows cannot re-open the slot.

    Callers must treat storage errors as *not acquired*. This is telemetry-only:
    failing closed avoids a possible duplicate and must never interrupt the
    underlying conversation extraction.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    marker_ref = (
        client.collection('users')
        .document(uid)
        .collection(conversations_collection)
        .document(conversation_id)
        .collection('analytics_markers')
        .document('conversation_memories_extracted')
    )
    try:
        marker_ref.create({'created_at': firestore.SERVER_TIMESTAMP})
        return True
    except AlreadyExists:
        return False


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
    and silently drops the earlier edit. The same write DELETE_FIELDs
    ``client_processing``: a projection bound to the old transcript must not
    outlive it. Missing projection: DELETE_FIELD is a no-op.

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
        _invalidate_client_processing(prepared_payload)
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
    """Delete a conversation and every subcollection underneath it.

    Firestore does not cascade, and a conversation owns more than ``photos``: the per-provider
    post-processing transcripts (verbatim segment text), the Hume emotion predictions, and the
    analytics marker. Purging only photos left those behind as data no query can reach — not even
    the account-deletion wipe, which walks *existing* documents and never sees a deleted parent.
    Children are enumerated live, so a subcollection added later is purged too.
    """
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    for sub in conversation_ref.collections():
        delete_collection_recursive(sub, client=db)
    conversation_ref.delete()


@prepare_for_read(decrypt_func=_prepare_conversation_for_read)
@with_photos(get_conversation_photos)
def get_conversations_by_id(
    uid,
    conversation_ids,
    include_discarded: bool = False,
    *,
    read_site: FirestoreReadSite = FirestoreReadSite.UNATTRIBUTED,
):
    return _get_conversations_by_id(uid, conversation_ids, include_discarded=include_discarded, read_site=read_site)


@prepare_for_read(decrypt_func=_prepare_conversation_for_read)
def get_conversations_by_id_without_photos(
    uid,
    conversation_ids,
    include_discarded: bool = False,
    *,
    read_site: FirestoreReadSite = FirestoreReadSite.UNATTRIBUTED,
):
    return _get_conversations_by_id(uid, conversation_ids, include_discarded=include_discarded, read_site=read_site)


def _get_conversations_by_id(
    uid,
    conversation_ids,
    include_discarded: bool = False,
    *,
    read_site: FirestoreReadSite = FirestoreReadSite.UNATTRIBUTED,
):
    user_ref = db.collection('users').document(uid)
    conversations_ref = user_ref.collection(conversations_collection)

    doc_refs = [conversations_ref.document(str(conversation_id)) for conversation_id in conversation_ids]
    docs = db.get_all(doc_refs)

    hits = 0
    misses = 0
    conversations_by_id = {}
    for doc in docs:
        if doc.exists:
            hits += 1
            data = doc.to_dict()
            if data.get('discarded') and not include_discarded:
                continue
            data.setdefault('id', doc.id)
            conversations_by_id[str(data['id'])] = data
        else:
            misses += 1

    if hits:
        record_document_read(read_site, FirestoreReadOutcome.HIT, count=hits)
    if misses:
        record_document_read(read_site, FirestoreReadOutcome.MISS, count=misses)

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


def select_stale_in_progress(conversations, cutoff: datetime, limit: int):
    """Oldest-first bounded selection of orphaned in-progress conversations (#9809).

    A conversation owned by any live session refreshes `finished_at` on every
    segment and that session's lifecycle loop processes it within the
    conversation timeout, so anything idle past the cutoff has no owner.
    Missing or non-datetime `finished_at` is excluded: without a trustworthy
    idle clock the row cannot be proven orphaned.
    """
    stale = []
    for conversation in conversations:
        finished_at = conversation.get('finished_at')
        if isinstance(finished_at, datetime) and finished_at < cutoff:
            stale.append(conversation)
    stale.sort(key=lambda conversation: conversation['finished_at'])
    return stale[:limit]


def get_stale_in_progress_conversations(uid: str, *, older_than_seconds: int, limit: int = 10, firestore_client=None):
    """In-progress conversations whose last activity predates the cutoff (#9809).

    The composite index orders by the last activity clock, so the bounded read
    always reaches the oldest candidates. Without that ordering, an arbitrary
    first page could keep old orphaned rows beyond it invisible forever.
    """
    client = firestore_client or get_firestore_client()
    user_ref = client.collection('users').document(uid)
    conversations_ref = (
        STALE_IN_PROGRESS_CONVERSATIONS_QUERY.build(
            user_ref.collection(conversations_collection),
            {'status': ConversationStatus.in_progress.value},
            field_filter_factory=FieldFilter,
        )
        .order_by('finished_at', direction=firestore.Query.ASCENDING)
        .limit(limit)
    )
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=older_than_seconds)
    return select_stale_in_progress((doc.to_dict() for doc in conversations_ref.stream()), cutoff, limit)


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
    """Atomically transition a conversation status when the current status matches.

    Projection fields in ``extra_updates`` bind to the transactional snapshot's
    stored transcript. A T1-validated candidate is dropped on T2 without
    failing the status claim — the conversation still finalizes.
    ``extra_updates_with_bound_client_processing`` reports whether a submitted
    projection survived (attribute and optional attached bind report).
    """
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
            # Digest check against THIS snapshot, not a route-level read.
            # A T1-validated projection must not land on a T2 transcript.
            updates.update(extra_updates_with_bound_client_processing(uid, current, extra_updates))
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


def _invalidate_client_processing(payload: Dict[str, Any]) -> None:
    """Stamp an explicit projection clear onto an already-prepared write.

    Distinct from omitting the key (generic persist: leave a stored projection)
    and from writing ``None`` (stripped so a merge cannot clobber a newer write).
    A transcript-text or attribution mutation is the genuine-clear path: the
    stored projection described a transcript that no longer exists. Applied
    after ``_prepare_conversation_for_write`` so the Firestore sentinel is not
    copied through that helper. ``DELETE_FIELD`` on an absent key is a no-op.
    """
    for field in PROJECTION_FAMILY_FIELDS:
        payload[field] = firestore.DELETE_FIELD


def _projection_digest(candidate: Any) -> Any:
    if isinstance(candidate, Mapping):
        return candidate.get('transcript_sha256')
    return getattr(candidate, 'transcript_sha256', None)


def _log_unbound_projection(reason: str, candidate: Any) -> None:
    """Content-free reject. Provenance is never logged here; the route already
    warned on the pre-check. A lost race (T1 verified, T2 stored) is not a
    request error — the conversation still finalizes without the projection.
    """
    del candidate
    logger.warning('client_processing rejected reason=%s', reason)


# Out-parameter the transactional bind fills. Survives a shallow ``dict()``
# copy of extra_updates (lifecycle.admit_processing) and is never persisted:
# extra_updates_with_bound_client_processing pops it before returning the
# write payload. The string is duplicated in routers/conversations.py because
# that module loads under a stubbed database.conversations in isolation tests.
CLIENT_PROCESSING_BIND_REPORT_KEY = '_client_processing_bind_report'


class BoundExtraUpdates(dict):
    """Write payload plus whether a submitted projection survived this bind.

    Callers that treat the return as a plain dict keep working. ``submitted_projection_bound``
    is an attribute, not a Firestore key.
    """

    submitted_projection_bound: bool

    def __init__(self, mapping: Mapping[str, Any], *, submitted_projection_bound: bool) -> None:
        super().__init__(mapping)
        self.submitted_projection_bound = submitted_projection_bound


def _is_unbound_projection_field_path(key: str) -> bool:
    """True when ``key`` writes under a projection root by any spelling but its plain name.

    Firestore parses an update key as a field path, so a projection is not
    only reachable as the exact name ``client_processing``. ``a.b`` is a
    nested write, and a backtick-quoted segment is the same field spelled
    differently: a quoted projection root, alone or followed by .structure.title,
    resolves to the protected root while looking nothing like it to a string
    comparison.
    Parse with Firestore's own parser and accept only the plain exact name,
    which is what the digest bind operates on.

    A key Firestore itself cannot parse is left alone: it is not a path to
    anything, and the write rejects it.
    """
    # Imported here, not at module scope: several suites stub google.cloud.firestore_v1
    # with a plain module, which makes a top-level submodule import fail at collection.
    from google.cloud.firestore_v1.field_path import FieldPath

    try:
        parts = FieldPath.from_string(key).parts
    except (ValueError, TypeError, KeyError):
        return False
    if not parts or parts[0] not in PROJECTION_FAMILY_FIELDS:
        return False
    return len(parts) > 1 or key != parts[0]


def _stamp_bind_report(report: Any, bound: bool) -> None:
    if isinstance(report, dict):
        report['submitted_projection_bound'] = bound


def extra_updates_with_bound_client_processing(
    uid: str,
    current: Mapping[str, Any],
    extra_updates: Mapping[str, Any] | None,
) -> BoundExtraUpdates:
    """Copy ``extra_updates``, dropping any projection that does not bind to ``current``.

    The digest is over the stored transcript as this transaction sees it.
    Decode is strict: the permissive read decoder maps an undecryptable blob
    to ``[]``, whose digest is a public constant any client can send. Binding
    is not a read path — if the snapshot cannot be decoded, the projection is
    dropped and every other field is left for the caller to commit. A
    successfully decoded empty list still binds to the empty-transcript
    digest. Non-canonical stored identity (``transcript_sha256_for_binding``
    is None) and digest mismatch also drop the projection. A drop is never a
    request error; the conversation still finalizes.

    Returns a dict whose ``submitted_projection_bound`` attribute is True only
    when a submitted projection field survived. If ``extra_updates`` carries
    ``CLIENT_PROCESSING_BIND_REPORT_KEY``, that nested report is filled with
    the same answer and the key is omitted from the write payload.
    """
    updates = dict(extra_updates or {})
    report = updates.pop(CLIENT_PROCESSING_BIND_REPORT_KEY, None)
    # Every write under a projection root goes through the digest bind or not
    # at all. See ``_is_unbound_projection_field_path``.
    for key in [key for key in updates if _is_unbound_projection_field_path(key)]:
        _log_unbound_projection('projection_field_path', updates.pop(key))
    if not any(field in updates for field in PROJECTION_FAMILY_FIELDS):
        _stamp_bind_report(report, False)
        return BoundExtraUpdates(updates, submitted_projection_bound=False)
    try:
        segments = _decode_transcript_segments_strict(
            uid,
            current.get('transcript_segments'),
            bool(current.get('transcript_segments_compressed')),
        )
    except (json.JSONDecodeError, TypeError, zlib.error, ValueError, RecursionError):
        for field in PROJECTION_FAMILY_FIELDS:
            if field not in updates:
                continue
            _log_unbound_projection('transcript_undecodable', updates[field])
            updates.pop(field, None)
        _stamp_bind_report(report, False)
        return BoundExtraUpdates(updates, submitted_projection_bound=False)
    expected = transcript_sha256_for_binding(segments)
    for field in PROJECTION_FAMILY_FIELDS:
        if field not in updates:
            continue
        candidate = updates[field]
        if expected is None:
            _log_unbound_projection('stored_transcript_not_canonical', candidate)
            updates.pop(field, None)
            continue
        digest = _projection_digest(candidate)
        if not isinstance(digest, str) or digest != expected:
            _log_unbound_projection('hash_mismatch', candidate)
            updates.pop(field, None)
    bound = any(field in updates for field in PROJECTION_FAMILY_FIELDS)
    _stamp_bind_report(report, bound)
    return BoundExtraUpdates(updates, submitted_projection_bound=bound)


def bind_client_processing(
    uid: str,
    conversation_id: str,
    mutation: Mapping[str, Any],
    *,
    firestore_client: Any = None,
) -> bool:
    """Write a projection iff it binds to the stored transcript in this transaction.

    ``mutation`` is the ingress payload from ``client_processing_mutation``.
    The digest comparison uses the transactional snapshot, not a route-level
    read. Mismatch, non-canonical stored identity, or a missing row: return
    False without writing. Never raises for a lost race.
    """
    client = firestore_client if firestore_client is not None else db
    doc_ref = client.collection('users').document(uid).collection(conversations_collection).document(conversation_id)

    @firestore.transactional
    def _bind(transaction) -> bool:
        snapshot = doc_ref.get(transaction=transaction)
        if not getattr(snapshot, 'exists', False):
            return False
        current = snapshot.to_dict() or {}
        bound_updates = extra_updates_with_bound_client_processing(uid, current, mutation)
        if not any(field in bound_updates for field in PROJECTION_FAMILY_FIELDS):
            return False
        transaction.update(doc_ref, bound_updates)
        return True

    if firestore_client is not None:
        return run_transactional(client, _bind)
    return _bind(client.transaction())


def update_conversation_segments(
    uid: str,
    conversation_id: str,
    segments: List[dict],
    finished_at: datetime = None,
    data_protection_level: str = None,
    *,
    started_at: datetime = None,
    firestore_client: Any = None,
    invalidate_client_processing: bool = True,
):
    """Replace a conversation's transcript segments.

    ``invalidate_client_processing`` defaults to TRUE, and that default is the
    point. This function's whole job is replacing the transcript, and a stored
    client projection is bound by digest to the transcript it described — so a
    caller that changes the segments and keeps the projection is displaying a
    summary of text that no longer exists. Opt-in invalidation would leave
    every existing and future call site carrying that bug silently; three
    separate leaks in this shard came from exactly that shape of default.
    Pass ``False`` to skip the *unconditional* ``DELETE_FIELD`` sentinel (the
    live-capture write loop). The transaction still clears a projection that
    is actually present on the document, so a finalize overlapping capture cannot
    leave a hash-bound summary of text that then changed.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    doc_ref = client.collection('users').document(uid).collection(conversations_collection).document(conversation_id)

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
        if invalidate_client_processing:
            _invalidate_client_processing(prepared_payload)
        elif any(current.get(field) is not None for field in PROJECTION_FAMILY_FIELDS):
            # Opt-out skips the sentinel so the ~0.6s live loop stays cheap when
            # no projection exists. A projection that is really there (overlap
            # with finalize) must still be cleared in this same write.
            _invalidate_client_processing(prepared_payload)
        transaction.update(doc_ref, prepared_payload)
        return True

    return run_transactional(client, _write_segments)


# ***********************************
# ********** VISIBILITY *************
# ***********************************


# A claim this old is treated as abandoned: the process that took it died
# mid-dispatch, and holding the recipient hostage forever would make the send
# unretryable. Comfortably longer than the provider request timeout.
SHARE_EMAIL_CLAIM_TTL_SECONDS = 180


def _in_flight_field(email: str) -> str:
    """Field path for one recipient's dispatch claim.

    An address contains characters (dots, `@`) that Firestore's field-path
    syntax reads as structure, so the segment is quoted by the client's own
    FieldPath rather than by hand — escaping only the dots still left `@`
    unparseable and failed the write.
    """
    from google.cloud.firestore_v1.field_path import FieldPath

    return FieldPath('share_email_in_flight', email).to_api_repr()


def reserve_share_email_recipients(
    uid: str, conversation_id: str, emails: list[str], *, now_epoch: float | None = None
) -> tuple[list[str], list[str], list[str]]:
    """Atomically decide who this request owns dispatching.

    Returns ``(to_dispatch, already_sent, in_flight_elsewhere)``.

    Two ledgers, deliberately distinct. ``share_email_sent_to`` means an email
    definitively went out; ``share_email_in_flight`` means some request is
    dispatching right now. Collapsing them lets a concurrent duplicate report
    success for a send that is still in flight — and if that send then fails and
    releases its claim, nobody sent anything while somebody was told otherwise.
    A caller that finds a live claim it does not own is told so, not lied to.
    """
    import time as _time

    from google.cloud import firestore as gc_firestore

    stamp = now_epoch if now_epoch is not None else _time.time()
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)

    @gc_firestore.transactional
    def _reserve(transaction):
        snapshot = conversation_ref.get(transaction=transaction)
        data = snapshot.to_dict() or {}
        sent = {e for e in (data.get('share_email_sent_to') or []) if isinstance(e, str)}
        raw_in_flight = data.get('share_email_in_flight')
        in_flight = raw_in_flight if isinstance(raw_in_flight, dict) else {}

        to_dispatch: list[str] = []
        already_sent: list[str] = []
        in_flight_elsewhere: list[str] = []
        claims: dict[str, float] = {}
        for email in emails:
            if email in sent:
                already_sent.append(email)
                continue
            claimed_at = in_flight.get(email)
            fresh = isinstance(claimed_at, (int, float)) and (stamp - claimed_at) < SHARE_EMAIL_CLAIM_TTL_SECONDS
            if fresh:
                in_flight_elsewhere.append(email)
                continue
            to_dispatch.append(email)
            claims[_in_flight_field(email)] = stamp

        if claims:
            transaction.update(conversation_ref, claims)
        return to_dispatch, already_sent, in_flight_elsewhere

    return run_transactional(db, _reserve)


def confirm_share_email_recipients(uid: str, conversation_id: str, emails: list[str]) -> None:
    """Record a definitive send and drop its in-flight claim, in that order."""
    from google.cloud import firestore as gc_firestore

    if not emails:
        return
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    update: dict[str, object] = {'share_email_sent_to': gc_firestore.ArrayUnion(emails)}
    for email in emails:
        update[_in_flight_field(email)] = gc_firestore.DELETE_FIELD
    conversation_ref.update(update)


def release_share_email_recipients(uid: str, conversation_id: str, emails: list[str]) -> None:
    """Drop claims after a definitive failure so a retry can dispatch again.

    Only the in-flight claim is dropped; nothing is removed from the sent
    ledger, because a recipient only lands there once delivery was definitive.
    """
    from google.cloud import firestore as gc_firestore

    if not emails:
        return
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.update({_in_flight_field(email): gc_firestore.DELETE_FIELD for email in emails})


def set_conversation_visibility(uid: str, conversation_id: str, visibility: str):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.update({'visibility': visibility})


def publish_conversation_visibility_if_private(uid: str, conversation_id: str):
    """Atomically flip visibility private→shared, preserving concurrent shares.

    The write carries a last_update_time precondition from the same read that
    observed 'private', so a concurrent writer (including one setting 'public')
    voids this publish instead of being downgraded. Returns
    ``(published, update_time)`` where ``update_time`` is the publish write's
    own WriteResult timestamp — the CAS token for rollback. ``(False, None)``
    means the conversation was (or became) link-visible some other way and this
    request must neither re-publish nor roll back.
    """
    from google.api_core import exceptions as gcloud_exceptions

    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    for _ in range(3):
        snapshot = conversation_ref.get()
        data = snapshot.to_dict() or {}
        if data.get('visibility') in ('shared', 'public'):
            return (False, None)
        try:
            result = conversation_ref.update(
                {'visibility': 'shared'},
                option=db.write_option(last_update_time=snapshot.update_time),
            )
            return (True, getattr(result, 'update_time', None))
        except gcloud_exceptions.FailedPrecondition:
            continue
    # Retries exhausted under contention. Only concede when another writer
    # actually made the conversation link-visible; a still-private doc means
    # nothing may be emailed (the link would be dead), so fail definitively.
    final = conversation_ref.get().to_dict() or {}
    if final.get('visibility') in ('shared', 'public'):
        return (False, None)
    raise RuntimeError('could not publish conversation visibility under contention')


def set_conversation_visibility_if_unchanged(uid: str, conversation_id: str, visibility: str, last_update_time) -> bool:
    """Write visibility only if the doc is untouched since ``last_update_time``.

    Firestore's native precondition makes this an ownership check: any
    concurrent write — even one that stored the same visibility value — bumps
    update_time and fails the precondition, so a rollback can never clobber
    another actor's share. Returns False when skipped.
    """
    from google.api_core import exceptions as gcloud_exceptions

    if last_update_time is None:
        return False
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    try:
        conversation_ref.update(
            {'visibility': visibility},
            option=db.write_option(last_update_time=last_update_time),
        )
        return True
    except gcloud_exceptions.FailedPrecondition:
        return False


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
    model: PostProcessingModel = PostProcessingModel.prerecorded,
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
    prerecorded_ref = conversation_ref.collection('prerecorded')

    # Sort each provider's segments by start time, tolerating a legacy/partial doc missing 'start'
    # (a bare x['start'] would KeyError and 500 the whole transcripts response).
    return {
        'deepgram': list(sorted([doc.to_dict() for doc in deepgram_ref.stream()], key=lambda x: x.get('start', 0))),
        'soniox': list(sorted([doc.to_dict() for doc in soniox_ref.stream()], key=lambda x: x.get('start', 0))),
        'speechmatics': list(
            sorted([doc.to_dict() for doc in speechmatics_ref.stream()], key=lambda x: x.get('start', 0))
        ),
        'whisperx': list(sorted([doc.to_dict() for doc in whisperx_ref.stream()], key=lambda x: x.get('start', 0))),
        'prerecorded': list(
            sorted([doc.to_dict() for doc in prerecorded_ref.stream()], key=lambda x: x.get('start', 0))
        ),
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
            transaction.set(photo_ref, prepare_photo_for_write(data, uid, level))
        transaction.update(conversation_ref, {'has_content': True, 'has_photos': True})
        return True

    return _store(transaction)


# ********************************
# ********** SYNCING *************
# ********************************


def is_soft_deleted(conversation: Optional[dict]) -> bool:
    """Whether a conversation is a soft-deleted tombstone.

    A tombstone is invisible to the user, so any content operation that reads it
    and writes derived state — merging its segments, or reprocessing to
    regenerate structured data, action items, memories and embeddings —
    resurrects data the user deleted. Such operations must reject a tombstone.

    Shared predicate behind that contract (sync #10119 via `eligible_merge_target`,
    merge #10262, reprocess). Deliberately distinct from `discarded`, which stays
    revivable: the merge and reprocess paths intentionally revive a discarded row.
    """
    return bool(conversation) and bool(conversation.get('deleted'))


def eligible_merge_target(conversation: Optional[dict]) -> bool:
    """Whether synced audio may merge into this conversation (#10033).

    A soft-deleted tombstone must never absorb new segments: the user cannot
    see it, so merged audio disappears — recordings that "never create a
    conversation". Discarded rows stay eligible; the merge path reprocesses
    and revives them.
    """
    return bool(conversation) and not is_soft_deleted(conversation)


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
