from database import conversation_visibility_counts, processing_backlog, speaker_auto_enroll
from utils.conversations import summary_delivery, lifecycle_clocks
from config.refactor_modes import serving_for, shadow_or_serve
import copy
import hashlib
import json
import logging
import uuid
import zlib
from collections.abc import Mapping
from functools import wraps
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any, Callable, Tuple
from database import chat_edits
from database.dream_dirty import after_write
from google.api_core.exceptions import AlreadyExists, Conflict, FailedPrecondition, NotFound
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter
import utils.other.hume as hume
from models.audio_file import AudioFile, ChunkSpan
from models.note_claims import claim_references_segment
from models.client_processing import PROJECTION_FAMILY_FIELDS
from models.conversation_enums import ConversationStatus, PostProcessingModel, PostProcessingStatus
from models.conversation_photo import ConversationPhoto
from models.capture_window_proof import CaptureWindowProof
from models.transcript_segment import TranscriptSegment, legacy_conversation_segment_id
from utils import encryption
from utils.conversation_page_cursor import BookmarkDict, decode_cursor, encode_cursor, query_scope
from config.firestore_read_levers import lever_enabled
from utils.conversations.fragment_visibility import is_completed_rule_discard, is_user_curated
from utils.conversations.transcript_hash import (
    canonicalize_transcript_segments_for_storage,
    transcript_sha256_for_binding,
)
from utils.observability.speaker_identification import record_speaker_review
from utils.open_loops.extraction import OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD, OPEN_LOOP_EXTRACTIONS_FIELD
from models.person_confidence import SOURCE_MANUAL
from utils.manual_speaker_assignments import (
    LIVE_TRANSCRIPT_REPLAY_RECEIPT_COMMIT_LIMIT,
    replay_receipt_commits,
    apply_manual_assignments,
    donor_selected_ids,
    validate_assignment_range,
    manual_assignment,
    merge_live_segments,
    normalize_rejection,
    remap_absorbed_receipt,
)
from database.mcp_read_queries import MCP_CONVERSATION_CARD_FIELD_PATHS, MCP_CONVERSATION_TRANSCRIPT_FIELD_PATHS
from database.quiet_check_retirement import restore_quiet_check_in_transaction, stop_quiet_check_for_conversation
from ._client import db, delete_collection_recursive, get_firestore_client, run_transactional
from database.sync_assignment import (
    SyncAssignmentClock,
    SyncAssignmentDiscovery,
    encode_sync_assignment_plan,
    run_sync_assignment,
)
from database.sync_conversation_snapshot import read_redirected, resolve_snapshot
from database.sync_live_overlap import find_sync_live_overlap_candidates
from utils.sync.live_overlap import live_overlap_enabled
from .audio_timeline import group_chunks_by_coverage
from .capture_groups import CAPTURE_GROUP_FIELD, leave_capture_group, preserve_duplicate_hint, transcript_fingerprint
from .firestore_index_registry import (
    CONVERSATIONS_BY_STATUS_FINISHED_AFTER_QUERY,
)
from .firestore_read_metrics import FirestoreReadOutcome, FirestoreReadSite, record_document_read
from .firestore_read_origin import read_origin
from .conversation_revisions import ensure_timezone_aware, firestore_revision_datetime
from .helpers import set_data_protection_level, prepare_for_write, prepare_for_read, with_photos
from .people_stats_cache import invalidate_people_stats_cache
from .read_boundary import parse_payload_strict
from utils.other.list_budget import (
    ListReadBudget,
    ListReadBudgetExhausted,
    budgeted_get_all,
    budgeted_stream_iter,
    indexed_list_reads_enabled,
)
from utils.other.portability_read import (
    check_portability_read,
    current_portability_read,
    iter_portability_guarded,
    verified_encrypted_read,
)
from config.transcription_final_pass import authoritative_for
import config.speaker_match_scores as match_scores
import config.owner_recognition_diagnostics as owner_diagnostics
import utils.firestore_document_size as document_size
from utils.other.playback_identity import source_fingerprint, retain_aliases
from utils.other.storage import list_audio_chunks
from utils.observability.fallback import record_fallback
from config.translation import resolve_ondemand_config
from database.translation_admission import TranslationReservation, reservation_is_current
from utils.llm.model_constants import LUNA_MODEL

logger = logging.getLogger(__name__)

conversations_collection = 'conversations'

_LIFECYCLE_FIELDS = frozenset({'status', 'discarded'})
# Top-level fields behind the Typesense conversation projection (see
# utils/conversations/typesense_index.py). A generic update re-syncs the index
# only when it touches one of these roots — segment/photo/app-result writes
# never reach Typesense, so they must not pay for it.
_SEARCH_INDEXED_FIELD_ROOTS = frozenset({'structured', 'created_at', 'started_at', 'finished_at', 'geolocation'})
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


# ******* ENCRYPTION HELPERS ******
# *********************************


def _decrypt_conversation_data(conversation_data: Dict[str, Any], uid: str) -> Dict[str, Any]:
    data = copy.deepcopy(conversation_data)
    _reveal_match_scores_for_read(data, uid)

    if 'transcript_segments' not in data:
        _reveal_manual_speaker_assignments_for_read(data, uid)
        return data

    if current_portability_read() is not None:
        data['transcript_segments'] = _decode_transcript_segments_strict(
            uid,
            data['transcript_segments'],
            bool(data.get('transcript_segments_compressed')),
            require_decryption=True,
        )
        _reveal_manual_speaker_assignments_for_read(data, uid)
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

    if isinstance(segments := data.get('transcript_segments'), list):
        from utils.conversations.speaker_grouping_storage import reveal_segments

        reveal_segments(segments, uid)
    _reveal_manual_speaker_assignments_for_read(data, uid)
    return data


def _protect_json_value(value: Any, uid: str, level: str) -> Any:
    payload = json.dumps(value)
    compressed = zlib.compress(payload.encode('utf-8'))
    if level == 'enhanced':
        return encryption.encrypt(compressed.hex(), uid)
    return compressed


def _reveal_json_value(raw: Any, uid: str, compressed: bool) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        payload = verified_encrypted_read(raw, encryption.decrypt(raw, uid))
        if compressed:
            return json.loads(zlib.decompress(bytes.fromhex(payload)).decode('utf-8'))
        return json.loads(payload)
    if isinstance(raw, bytes) and compressed:
        return json.loads(zlib.decompress(raw).decode('utf-8'))
    raise ValueError(f'undecodable json blob: {type(raw).__name__} compressed={compressed}')


def decode_manual_speaker_assignments(uid: str, raw: Any, compressed: bool) -> dict:
    if raw is None:
        return {}
    parsed = _reveal_json_value(raw, uid, compressed)
    if not isinstance(parsed, dict):
        if current_portability_read() is not None:
            raise ValueError(f'undecodable manual_speaker_assignments: parsed {type(parsed).__name__}')
        return {}
    return parsed


def _reveal_manual_speaker_assignments_for_read(data: Dict[str, Any], uid: str) -> None:
    if 'manual_speaker_assignments' not in data:
        return
    try:
        data['manual_speaker_assignments'] = decode_manual_speaker_assignments(
            uid, data.get('manual_speaker_assignments'), bool(data.get('manual_speaker_assignments_compressed'))
        )
    except (json.JSONDecodeError, TypeError, zlib.error, ValueError) as error:
        if current_portability_read() is not None:
            raise
        logger.error(f"{error} {uid}")
        data['manual_speaker_assignments'] = {}
    if data['manual_speaker_assignments'] and isinstance(segments := data.get('transcript_segments'), list):
        data['transcript_segments'] = apply_manual_assignments(segments, data['manual_speaker_assignments'])


def _reveal_match_scores_for_read(data: Dict[str, Any], uid: str) -> None:
    if match_scores.FIELD not in data:
        return
    try:
        data[match_scores.FIELD] = match_scores.normalize(_reveal_json_value(data[match_scores.FIELD], uid, True))
    except Exception:
        if current_portability_read() is not None:
            raise
        _drop_match_scores(data, 'malformed_doc')


def _drop_match_scores(data: dict, reason: str = 'other') -> None:
    data.pop(match_scores.FIELD, None)
    match_scores.record_failure(logger, reason=reason)


def guard_match_score_size(data: dict, existing: Optional[dict] = None, path: Optional[str] = None) -> None:
    """Optional scores cannot push the existing document towards Firestore's ceiling.
    Uses only the snapshot already read by the write owner. The 124 KiB
    headroom matches sync's existing budget and covers unknown SDK types.
    """
    if match_scores.FIELD not in data and match_scores.FIELD not in (existing or {}):
        return
    try:
        stored = {**(existing or {}), **data}
        if stored.get(match_scores.FIELD) is firestore.DELETE_FIELD:
            stored.pop(match_scores.FIELD, None)
        if (
            document_size.estimate_firestore_document_bytes(stored, path if isinstance(path, str) else None)
            > 900 * 1024
        ):
            _drop_match_scores(data, 'capacity_full')
            if existing is not None and match_scores.FIELD in existing:
                data[match_scores.FIELD] = firestore.DELETE_FIELD
    except Exception:
        _drop_match_scores(data)


def _merge_owner_diagnostics(payload: dict, current: dict, path=None) -> None:
    """Optional plaintext metadata; existing content commits must win every size/fault race."""
    if owner_diagnostics.FIELD not in payload:
        return
    try:
        value = owner_diagnostics.merge(current.get(owner_diagnostics.FIELD), payload.pop(owner_diagnostics.FIELD))
        if value:
            for row in value.get('live', []):
                if row.get('scores_generated'):
                    scores = payload.get(match_scores.FIELD, current.get(match_scores.FIELD))
                    row['scores'] = 'present' if scores and scores is not firestore.DELETE_FIELD else 'absent'
            value = owner_diagnostics.normalize(value)
            candidate = {**current, **payload, owner_diagnostics.FIELD: value}
            if (
                document_size.estimate_firestore_document_bytes(candidate, path if isinstance(path, str) else None)
                <= 900 * 1024
            ):
                payload[owner_diagnostics.FIELD] = value
    except Exception:
        payload.pop(owner_diagnostics.FIELD, None)
        record_fallback(
            component='other', from_mode='none', to_mode='none', reason='other', outcome='degraded', log=logger
        )


def update_owner_recognition_diagnostics(uid: str, conversation_id: str, diagnostics: dict, *, firestore_client=None):
    """Metadata-only terminal flush, including generations that never produced an identity map."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection(conversations_collection).document(conversation_id)

    @firestore.transactional
    def persist(transaction):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            return False
        current = snapshot.to_dict() or {}
        if any(current.get(k) for k in ('deleted', 'is_locked')):
            return False
        patch = {owner_diagnostics.FIELD: diagnostics}
        _merge_owner_diagnostics(patch, current, ref.path)
        if patch and patch.get(owner_diagnostics.FIELD) != current.get(owner_diagnostics.FIELD):
            transaction.update(ref, patch)
        return True

    return run_transactional(client, persist)


def _prepare_conversation_for_write(
    data: Dict[str, Any], uid: str, level: str, *, preserve_transcript_identity: bool = False
) -> Dict[str, Any]:
    data = copy.deepcopy(data)

    summary_delivery.prepare(data, uid)
    if owner_diagnostics.FIELD in data:
        try:
            value = owner_diagnostics.normalize(data[owner_diagnostics.FIELD])
        except Exception:
            value = {}
            record_fallback(
                component='other', from_mode='none', to_mode='none', reason='other', outcome='degraded', log=logger
            )
        if value:
            data[owner_diagnostics.FIELD] = value
        else:
            data.pop(owner_diagnostics.FIELD, None)
    if level not in {'standard', 'enhanced'}:
        data.pop('record_lane_owner', None)
    segments = data.get('transcript_segments')
    if isinstance(segments, list) and any('original_text' in segment for segment in segments):
        from utils.agent_capabilities.transcripts import originals

        segments = data['transcript_segments'] = originals(segments)
    try:
        _reveal_match_scores_for_read(data, uid)
        if isinstance(segments, list):
            updates = match_scores.from_segments(segments)
            if updates and match_scores.enabled():
                data[match_scores.FIELD] = match_scores.merge(data.get(match_scores.FIELD), updates)
    except Exception:
        # Optional metadata must never block content when decoding/merging fails.
        _drop_match_scores(data)
    if isinstance(segments, list):
        for segment in segments:
            segment.pop(match_scores.FIELD, None)
    if 'transcript_segments' in data and isinstance(data['transcript_segments'], list):
        if not preserve_transcript_identity:
            data['transcript_segments'] = canonicalize_transcript_segments_for_storage(data['transcript_segments'])
        from utils.conversations.speaker_grouping_storage import protect_segments

        protect_segments(data['transcript_segments'], uid)
        data['transcript_segments'] = _protect_json_value(data['transcript_segments'], uid, level)
        data['transcript_segments_compressed'] = True
    if match_scores.FIELD in data:
        try:
            encoded, trimmed = match_scores.encode_bounded(
                data[match_scores.FIELD], lambda rows: _protect_json_value(rows, uid, level)
            )
            if encoded is not None:
                data[match_scores.FIELD] = encoded
                if trimmed:
                    match_scores.record_failure(logger, trimmed=True, reason='capacity_full')
            else:
                _drop_match_scores(data, 'capacity_full')
        except Exception:
            # Never fall back to plaintext for enhanced protection.
            _drop_match_scores(data)
    if 'manual_speaker_assignments' in data:
        if not isinstance(data['manual_speaker_assignments'], dict):
            raise ValueError('manual_speaker_assignments must be an object')
        receipt = data['manual_speaker_assignments']
        if receipt:
            data['manual_speaker_assignments'] = _protect_json_value(receipt, uid, level)
            data['manual_speaker_assignments_compressed'] = True
        else:
            data.pop('manual_speaker_assignments', None)
            data.pop('manual_speaker_assignments_compressed', None)
    if 'user_corrections' in data and isinstance(data['user_corrections'], list):
        data['user_corrections'] = _protect_json_value(data['user_corrections'], uid, level)
        data['user_corrections_compressed'] = True
    if OPEN_LOOP_EXTRACTIONS_FIELD in data:
        # Server-only derived content (quotes from the conversation), so it
        # rides the same compressed/encrypted-at-rest protection as the other
        # derived JSON blobs. An explicit null clears a prior value together
        # with its marker; merge=True would otherwise keep both.
        open_loops = data.get(OPEN_LOOP_EXTRACTIONS_FIELD)
        if open_loops:
            if not isinstance(open_loops, dict):
                raise ValueError('open_loop_extractions must be an object')
            data[OPEN_LOOP_EXTRACTIONS_FIELD] = _protect_json_value(open_loops, uid, level)
            data[OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD] = True
        else:
            data[OPEN_LOOP_EXTRACTIONS_FIELD] = None
            data[OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD] = None
    guard_match_score_size(data)
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


def _is_verified_recovery_discard(write_data: Dict[str, Any]) -> bool:
    # Imported lazily: several unit harnesses load this module with a stubbed
    # ``utils`` package that has no ``utils.conversations`` subpackage.
    from utils.conversations.recovery import verified_recovery_discard

    return verified_recovery_discard(write_data.get('discarded'), write_data.get('relevance_decision'))


def _decode_transcript_segments_strict(
    uid: str, raw_segments: Any, compressed: bool, *, require_decryption: bool = False
) -> List[Any]:
    from utils.conversations.speaker_grouping_storage import reveal_segments

    segments = _decode_transcript_segments_blob(uid, raw_segments, compressed, require_decryption=require_decryption)
    reveal_segments(segments, uid)
    return segments


def _decode_transcript_segments_blob(
    uid: str, raw_segments: Any, compressed: bool, *, require_decryption: bool = False
) -> List[Any]:
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
        if require_decryption and payload == raw_segments:
            # decrypt's display fallback returns the input on authentication
            # failure. Even parseable plaintext is not a successful decode.
            raise ValueError('undecodable transcript_segments: decryption failed')
        if compressed:
            parsed = json.loads(zlib.decompress(bytes.fromhex(payload)).decode('utf-8'))
        else:
            parsed = json.loads(payload)
        return _require_segment_list(parsed)
    if isinstance(raw_segments, bytes) and compressed:
        return _require_segment_list(json.loads(zlib.decompress(raw_segments).decode('utf-8')))
    raise ValueError(f'undecodable transcript_segments: {type(raw_segments).__name__} compressed={compressed}')


def decode_transcript_segments_verified(uid: str, raw_segments: Any, compressed: bool) -> List[Any]:
    """Strict decode for callers outside this module: raises unless the blob decodes and decrypts."""
    return _decode_transcript_segments_strict(uid, raw_segments, compressed, require_decryption=True)


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
    retain_anchors: bool = False,
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
            if retain_anchors:
                for field in ('id', 'segment_id'):
                    value = segment.get(field)
                    if value is not None:
                        if not isinstance(value, str) or len(value) > 256:
                            raise invalid()
                        safe_segment[field] = value
                for field in ('start', 'end'):
                    value = segment.get(field)
                    if value is not None:
                        if isinstance(value, bool) or not isinstance(value, (int, float)):
                            raise invalid()
                        safe_segment[field] = value
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


def effective_user_title(user_title: Any) -> Optional[str]:
    """The user's title override, or ``None`` when there is none.

    A blank string is no override: applying it would erase the generated (or
    deterministic) title and render the row "Untitled". Readers and the
    processing persists that re-apply the override resolve ``user_title``
    through this one rule, so the stored ``structured.title`` shows. The
    user-facing title writes (PATCH, ``set_title``) are unchanged.
    """
    return user_title if isinstance(user_title, str) and user_title.strip() else None


def _reveal_user_corrections_for_read(data: Dict[str, Any], uid: str) -> None:
    if data.get('user_corrections_compressed'):
        data['user_corrections'] = _reveal_json_value(data.get('user_corrections'), uid, True)


def decode_open_loop_extractions(uid: str, raw: Any, compressed: bool) -> Optional[dict]:
    """Strict write-side round trip; unreadable retained content must abort the write."""
    if raw is None:
        return None
    value = _reveal_json_value(raw, uid, compressed)
    if not isinstance(value, dict):
        raise ValueError('open_loop_extractions must be an object')
    return value


def get_open_loop_extractions(uid: str, conversation_data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Decode the server-only open-loop extractions from one raw conversation document.

    Server-only by construction: the field is outside the Conversation wire
    model, and this helper (not ``prepare_conversation_for_read``) is the only
    intended reader. An absent, cleared, or undecodable value is None; a later
    daily pass treats that as "no extractions", never as an error.
    """
    if not conversation_data:
        return None
    if not conversation_data.get(OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD):
        return None
    try:
        value = _reveal_json_value(conversation_data.get(OPEN_LOOP_EXTRACTIONS_FIELD), uid, True)
    except (ValueError, TypeError, json.JSONDecodeError, zlib.error):
        return None
    return value if isinstance(value, dict) else None


def prepare_conversation_for_read(
    conversation_data: Optional[Dict[str, Any]],
    uid: str,
    *,
    firestore_client: Any = None,
    read_budget: Optional[ListReadBudget] = None,
) -> Optional[Dict[str, Any]]:
    if not conversation_data:
        return None

    data = copy.deepcopy(conversation_data)
    data.pop('live_transcript_replay_receipt', None)
    _reveal_user_corrections_for_read(data, uid)
    if is_completed_rule_discard(data):
        data['discarded'] = True
    # User titles are durable overrides. Conversation processing owns the
    # generated title, but must never erase an explicit user edit.
    user_title = effective_user_title(data.get('user_title'))
    if user_title is not None:
        structured = data.get('structured')
        if not isinstance(structured, dict):
            structured = {}
            data['structured'] = structured
        structured['title'] = user_title
    level = data.get('data_protection_level')

    if level == 'enhanced':
        from utils.agent_capabilities.transcripts import project

        return project(
            uid, _decrypt_conversation_data(data, uid), firestore_client=firestore_client, read_budget=read_budget
        )

    # Handle standard level with potential compression
    if data.get('transcript_segments_compressed'):
        if 'transcript_segments' in data and isinstance(data['transcript_segments'], bytes):
            try:
                decompressed_json = zlib.decompress(data['transcript_segments']).decode('utf-8')
                data['transcript_segments'] = json.loads(decompressed_json)
            except (json.JSONDecodeError, TypeError, zlib.error) as e:
                logger.error(e)
                pass

    if isinstance(segments := data.get('transcript_segments'), list):
        from utils.conversations.speaker_grouping_storage import reveal_segments

        reveal_segments(segments, uid)
    _reveal_manual_speaker_assignments_for_read(data, uid)
    _reveal_match_scores_for_read(data, uid)
    from utils.agent_capabilities.transcripts import project

    return project(uid, data, firestore_client=firestore_client, read_budget=read_budget)


def document_data_with_revision(document) -> Optional[Dict[str, Any]]:
    """Return Firestore document data with its canonical server revision."""
    data = document.to_dict()
    if data is None:
        return None
    revision = firestore_revision_datetime(getattr(document, 'update_time', None))
    if revision is not None:
        data['updated_at'] = revision
    return data


def prepare_photo_for_write(data: Dict[str, Any], uid: str, level: str) -> Dict[str, Any]:
    data = copy.deepcopy(data)
    data['data_protection_level'] = level
    if level == 'enhanced' and 'base64' in data and isinstance(data['base64'], str):
        data['base64'] = encryption.encrypt(data['base64'], uid)
    return data


def prepare_photo_for_read(photo_data: Optional[Dict[str, Any]], uid: str) -> Optional[Dict[str, Any]]:
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
        data['base64'] = verified_encrypted_read(photo_data['base64'], data['base64'])
    return data


@prepare_for_read(decrypt_func=prepare_photo_for_read)
def get_conversation_photos(uid: str, conversation_id: str, *, firestore_client: Any = None):
    client = firestore_client if firestore_client is not None else db
    user_ref = client.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    photos_ref = conversation_ref.collection('photos')
    photos = [doc.to_dict() for doc in photos_ref.stream()]
    return photos


def iter_all_conversation_photos(uid: str):
    start_key = db.document(f'users/{uid}/conversations/ /photos/ ')
    end_key = db.document(f'users/{uid}/conversations//photos/')
    query = db.collection_group('photos').where(filter=FieldFilter('__name__', '>=', start_key))
    query = query.where(filter=FieldFilter('__name__', '<=', end_key))
    for doc in iter_portability_guarded(query.stream()):
        check_portability_read()
        # Path format: users/{uid}/conversations/{conversation_id}/photos/{photo_id}
        parts = doc.reference.path.split('/')
        if len(parts) >= 6 and parts[-2] == 'photos' and parts[-4] == 'conversations':
            conversation_id = parts[-3]
            yield conversation_id, prepare_photo_for_read(doc.to_dict(), uid) or doc.to_dict()


def _sync_conversation_search_index(uid: str, conversation_id: str) -> None:
    """Converge the Typesense projection after a durable write (fail-open).

    The import stays inside the hook on purpose: several test harnesses load
    this module against stubbed ``utils`` packages without a real
    ``utils.conversations`` path, and a module-top import of the projection
    breaks them (PR #12819 round one).
    """
    try:
        from utils.conversations.typesense_index import sync_conversation_index_after_write

        sync_conversation_index_after_write(uid, conversation_id)
    except Exception as exc:
        logger.warning(
            "conversation Typesense sync hook failed uid=%s conversation_id=%s: %s", uid, conversation_id, exc
        )


def _delete_conversation_search_index(uid: str, conversation_id: str) -> None:
    """Remove one conversation from Typesense after a durable delete (fail-open)."""
    try:
        from utils.conversations.typesense_index import delete_conversation_index_doc

        delete_conversation_index_doc(uid, conversation_id)
    except Exception as exc:
        logger.warning(
            "conversation Typesense delete hook failed uid=%s conversation_id=%s: %s", uid, conversation_id, exc
        )


# *****************************
# ********** CRUD *************
# *****************************


def _reapply_current_manual_assignments(uid: str, write_data: dict, existing: dict) -> None:
    """A processor owns content, never the receipt read in its commit transaction."""
    write_data.pop('manual_speaker_assignments', None)
    write_data.pop('manual_speaker_assignments_compressed', None)
    level = existing.get('data_protection_level') or write_data.get('data_protection_level') or 'standard'
    if OPEN_LOOP_EXTRACTIONS_FIELD in write_data and write_data.get('data_protection_level') != level:
        # Processing may have encoded fresh extractions before a protection
        # migration committed. Re-protect that output at the transaction's level.
        extracted = decode_open_loop_extractions(
            uid, write_data[OPEN_LOOP_EXTRACTIONS_FIELD], bool(write_data.get(OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD))
        )
        write_data.update(_prepare_conversation_for_write({OPEN_LOOP_EXTRACTIONS_FIELD: extracted}, uid, level))
        write_data['data_protection_level'] = level
    if 'transcript_segments' not in write_data:
        return
    if existing.get('has_transcript_corrections'):
        # A reprocessor owns generated output, not captured speech or its legacy
        # anchors. Keep the exact committed blob and encoding across snapshots.
        for field in ('transcript_segments', 'transcript_segments_compressed', 'data_protection_level'):
            if field in existing:
                write_data[field] = existing[field]
        return
    receipt = decode_manual_speaker_assignments(
        uid, existing.get('manual_speaker_assignments'), bool(existing.get('manual_speaker_assignments_compressed'))
    )
    segments = _decode_transcript_segments_strict(
        uid, write_data['transcript_segments'], bool(write_data.get('transcript_segments_compressed'))
    )
    payload = {
        'transcript_segments': apply_manual_assignments(segments, receipt),
        'manual_speaker_assignments': receipt,
    }
    if match_scores.FIELD in write_data:
        # A processing snapshot can predate a protection migration. Remove its
        # prepared blob first so a failed re-encode cannot retain old plaintext.
        snapshot_scores = write_data.pop(match_scores.FIELD)
        try:
            current_scores = (
                _reveal_json_value(existing[match_scores.FIELD], uid, True) if match_scores.FIELD in existing else []
            )
            payload[match_scores.FIELD] = match_scores.merge_processing(
                current_scores,
                _reveal_json_value(snapshot_scores, uid, True),
                replace_resolution=(write_data.get('speaker_resolution') or {}).get('status')
                in ('resolved', 'unavailable'),
            )
        except Exception:
            # Omitting this optional update leaves the current stored blob intact.
            match_scores.record_failure(logger, reason='malformed_doc')
    if owner_diagnostics.FIELD in write_data:
        payload[owner_diagnostics.FIELD] = write_data.pop(owner_diagnostics.FIELD)
        _merge_owner_diagnostics(payload, existing)
    write_data.update(_prepare_conversation_for_write(payload, uid, level))
    write_data['data_protection_level'] = level


def is_soft_deleted(conversation: Optional[Mapping[str, Any]]) -> bool:
    """Whether a conversation is a soft-deleted tombstone.

    A tombstone is invisible to the user, so any content operation that reads it
    and writes derived state — merging its segments, or reprocessing to
    regenerate structured data, action items, memories and embeddings —
    resurrects data the user deleted. Such operations must reject a tombstone.

    Shared predicate behind that contract (sync #10119 via `eligible_merge_target`,
    merge #10262, reprocess, list/count/search after #15193 donor redirects).
    Deliberately distinct from `discarded`, which stays revivable: the merge and
    reprocess paths intentionally revive a discarded row. Redirect tombstones
    also stamp `discarded=True` so the indexed `discarded == False` filter hides
    them; `include_discarded=True` readers still consult this predicate.
    """
    return bool(conversation) and bool(conversation.get('deleted'))


def is_visible_conversation(conversation: Optional[Mapping[str, Any]], *, include_discarded: bool = False) -> bool:
    """Whether a stored conversation may be put in front of a user or downstream job."""
    if not conversation:
        return False
    if is_soft_deleted(conversation):
        return False
    if not include_discarded:
        # Dream duplicate captures are folded out of product reads, but the
        # preserved recordings stay visible to export/compliance readers.
        if (
            conversation.get('dream_duplicate_of')
            or conversation.get('discarded')
            or is_completed_rule_discard(conversation)
        ):
            return False
    return True


# Legacy completed rule-discards still match ``discarded == False``. Skip at
# most this many of them while filling one page: one stale row must not empty
# the page, and a pile must not walk the collection. Past the cap the page
# may be short; that bound is preferable to an unbounded scan or a new index.
_RULE_DISCARD_PAGE_SKIP_CAP = 64


def _conversation_list_cursor_enabled(uid: Optional[str]) -> bool:
    if uid is None:
        return False
    try:
        return lever_enabled('conversation_list_cursor', uid)
    except ValueError:
        # WQ4's new lever is registered by the integrator in a separate file.
        # Until then, the unknown-name guard must keep existing lists working.
        return False


def _with_conversation_cursor_envelope(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        uid = args[0] if args else kwargs.get('uid')
        if (
            not kwargs.get('page_envelope', False)
            or kwargs.get('metadata_only', False)
            or not _conversation_list_cursor_enabled(uid)
        ):
            return func(*args, **kwargs)
        page = {}
        kwargs['cursor_page'] = page
        # Wrap after existing decorators have decrypted/hydrated individual rows.
        rows = func(*args, **kwargs)
        return {'conversations': rows, 'next_cursor': page.get('next_cursor')}

    return wrapper


def _collect_cursor_conversation_page(conversations_ref, *, limit, include_discarded, budget, bookmark):
    """Bound the scan by page size plus the existing hidden-row allowance."""
    conversations = []
    last_doc = None
    skipped = 0
    query = conversations_ref.start_after(bookmark)
    try:
        while len(conversations) < limit and skipped <= _RULE_DISCARD_PAGE_SKIP_CAP:
            batch_limit = min(limit - len(conversations), _RULE_DISCARD_PAGE_SKIP_CAP - skipped + 1)
            fetched = 0
            for doc in budgeted_stream_iter(query.limit(batch_limit), budget):
                fetched += 1
                last_doc = doc
                conversation = document_data_with_revision(doc)
                if conversation is None or not is_visible_conversation(
                    conversation, include_discarded=include_discarded
                ):
                    skipped += 1
                    continue
                conversations.append(conversation)
            if fetched < batch_limit or last_doc is None:
                break
            query = conversations_ref.start_after(last_doc)
    except ListReadBudgetExhausted:
        pass
    return conversations, last_doc


def _collect_visible_conversation_page(
    conversations_ref: Any,
    *,
    limit: int,
    offset: int,
    include_discarded: bool,
    budget: Optional[ListReadBudget] = None,
    uid: Optional[str] = None,
    cursor: Optional[str] = None,
    cursor_page: Optional[Dict[str, Any]] = None,
    cursor_filters: Optional[Dict[str, Any]] = None,
    sort_field: str = 'created_at',
) -> List[Dict[str, Any]]:
    """Page visible rows.

    ``include_discarded=True`` scans and fills, because donor tombstones are not
    excluded by an indexed flag. ``include_discarded=False`` keeps the indexed
    ``discarded == False`` query's server ``limit``/``offset`` (desktop parity).
    If that window is full but some rows are completed rule-discards, keep
    reading after the last snapshot until the page is full or the skip cap hits.
    """
    cursor_enabled = _conversation_list_cursor_enabled(uid)
    scope = (
        query_scope(dict(uid=uid, sort_field=sort_field, include_discarded=include_discarded, **(cursor_filters or {})))
        if cursor_enabled
        else None
    )
    last_doc = None

    def finish(rows):
        if cursor_enabled and cursor_page is not None:
            cursor_page['next_cursor'] = None
            if last_doc is not None:
                try:
                    cursor_page['next_cursor'] = encode_cursor(last_doc.to_dict().get(sort_field), last_doc.id, scope)
                except (ValueError, TypeError, AttributeError):
                    # A null/corrupt ordering key must omit the cursor, not 500 the list route.
                    logger.warning('conversation_list_cursor: ordering key unavailable; next cursor omitted')
        return rows

    if cursor_enabled and cursor is not None:
        try:
            stamp, doc_id = decode_cursor(cursor, scope)
        except ValueError:
            record_fallback(
                component='firestore_read',
                from_mode='cursor',
                to_mode='offset',
                reason='malformed',
                outcome='degraded',
                log=logger,
            )
        else:
            # Firestore implicitly orders document IDs in the last order's
            # direction. Make that tie-break explicit for the value cursor.
            ordered = conversations_ref.order_by('__name__', direction=firestore.Query.DESCENDING)
            conversations, last_doc = _collect_cursor_conversation_page(
                ordered,
                limit=limit,
                include_discarded=include_discarded,
                budget=budget,
                bookmark=BookmarkDict({sort_field: stamp, '__name__': doc_id}),
            )
            return finish(conversations)

    if include_discarded:
        skipped_visible = 0
        conversations: List[Dict[str, Any]] = []
        try:
            for doc in budgeted_stream_iter(conversations_ref, budget):
                last_doc = doc
                conversation = document_data_with_revision(doc)
                if conversation is None or not is_visible_conversation(
                    conversation, include_discarded=include_discarded
                ):
                    continue
                if skipped_visible < offset:
                    skipped_visible += 1
                    continue
                conversations.append(conversation)
                if len(conversations) >= limit:
                    break
        except ListReadBudgetExhausted:
            pass
        return finish(conversations)

    if budget is not None and offset > 0:
        try:
            budget.charge(offset)
        except ListReadBudgetExhausted:
            return finish([])
    page_query = conversations_ref.limit(limit).offset(offset)
    conversations = []
    last_doc = None
    fetched = 0
    batch_limit = limit
    try:
        for doc in budgeted_stream_iter(page_query, budget):
            fetched += 1
            last_doc = doc
            conversation = document_data_with_revision(doc)
            if conversation is None or not is_visible_conversation(conversation, include_discarded=False):
                continue
            conversations.append(conversation)
    except ListReadBudgetExhausted:
        return finish(conversations)

    skipped = fetched - len(conversations)
    while (
        len(conversations) < limit
        and fetched == batch_limit
        and last_doc is not None
        and skipped <= _RULE_DISCARD_PAGE_SKIP_CAP
        and hasattr(conversations_ref, 'start_after')
    ):
        # A shortfall-sized follow-up lets one stale row end the scan while
        # visible rows remain. Ask for another full window; the skip cap still
        # bounds the walk.
        follow = conversations_ref.start_after(last_doc).limit(batch_limit)
        fetched = 0
        try:
            for doc in budgeted_stream_iter(follow, budget):
                fetched += 1
                last_doc = doc
                conversation = document_data_with_revision(doc)
                if conversation is None or not is_visible_conversation(conversation, include_discarded=False):
                    skipped += 1
                    if skipped > _RULE_DISCARD_PAGE_SKIP_CAP:
                        return finish(conversations)
                    continue
                conversations.append(conversation)
                if len(conversations) >= limit:
                    return finish(conversations)
        except ListReadBudgetExhausted:
            return finish(conversations)
        if fetched < batch_limit:
            break
    return finish(conversations)


def _drop_summary_memo(uid: str) -> None:
    """Forget a request-scoped summary read after its transaction commits.

    Importing the memo cache registers Prometheus series. Conversation imports
    stay free of that until a summary write has actually committed.
    """
    from database.fsr_read_cache import forget_request_reads

    forget_request_reads(uid)


@set_data_protection_level(data_arg_name='conversation_data')
@prepare_for_write(data_arg_name='conversation_data', prepare_func=_prepare_conversation_for_write)
@after_write('conversations')
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
    summary_receipt = None
    summary_changed = False

    @firestore.transactional
    def _write_processing_result(transaction):
        nonlocal summary_receipt, summary_changed
        summary_receipt = None
        summary_changed = False
        write_data = copy.deepcopy(conversation_data)
        # Capture-group membership has one writer (database.capture_groups).
        write_data.pop(CAPTURE_GROUP_FIELD, None)
        existing_snapshot = conversation_ref.get(transaction=transaction)
        if getattr(existing_snapshot, 'exists', False):
            existing = existing_snapshot.to_dict() or {}
            preserve_duplicate_hint(write_data, existing)
            if existing.get('record_lane_owner'):
                write_data['record_lane_owner'] = existing['record_lane_owner']
            else:
                write_data.pop('record_lane_owner', None)

            # Processing owns generated content, while these fields are explicitly
            # user-owned. The transaction retries if a concurrent mutation lands,
            # so an older in-memory Conversation cannot clobber that edit.
            # A null existing value means "never user-set" (stub docs dump None
            # fields), so only non-null values are preserved — otherwise the
            # stub's folder_id: None would revert every AI folder assignment.
            for field in (
                'starred',
                'folder_id',
                'visibility',
                'user_title',
                'user_corrections',
                'user_corrections_compressed',
                'user_overview',
            ):
                if existing.get(field) is not None:
                    write_data[field] = existing[field]

            # folder_id is user-owned even when explicitly cleared: the folder
            # move endpoints stamp folder_user_set, so "no folder" chosen by the
            # user (folder_id None + marker) must survive processing output.
            # Only a stub's never-user-touched None may be overwritten by the
            # AI folder assignment above.
            if existing.get('folder_user_set'):
                write_data['folder_id'] = existing.get('folder_id')

            user_title = effective_user_title(existing.get('user_title'))
            if user_title is not None:
                structured = write_data.get('structured')
                if not isinstance(structured, dict):
                    structured = {}
                    write_data['structured'] = structured
                structured['title'] = user_title
            if existing.get('user_overview'):
                write_data.setdefault('structured', {})['overview'] = existing['user_overview']

            _reapply_current_manual_assignments(uid, write_data, existing)
            guard_match_score_size(write_data, existing, getattr(conversation_ref, 'path', None))

            summary_receipt = summary_delivery.merge_result(existing, write_data, uid)
            summary_changed = processing_backlog.stage_transition(
                transaction, uid, conversation_data['id'], existing, write_data, firestore_client=db
            )
            transaction.set(conversation_ref, write_data, merge=True)
            return

        write_data.setdefault('has_photos', False)

        summary_receipt = summary_delivery.creation_result(write_data, uid)
        summary_changed = processing_backlog.stage_transition(
            transaction, uid, conversation_data['id'], {}, write_data, firestore_client=db
        )
        transaction.set(conversation_ref, write_data)

    run_transactional(db, _write_processing_result)
    stop_quiet_check_for_conversation(uid, conversation_data['id'], firestore_client=db)
    if summary_changed:
        _drop_summary_memo(uid)

    summary_delivery.emit(summary_receipt)
    invalidate_people_stats_cache(uid)
    _sync_conversation_search_index(uid, conversation_data['id'])


@set_data_protection_level(data_arg_name='conversation_data')
@prepare_for_write(
    data_arg_name='conversation_data',
    prepare_func=_prepare_conversation_for_write,
    preserve_result=True,
)
@after_write('conversations')
def persist_processing_result_with_lifecycle(
    uid: str,
    conversation_data: dict,
    *,
    on_first_completion: Callable[[], None] | None = None,
    smart_merge_refresh: tuple[int, str] | None = None,
) -> bool:
    """Merge a processor result into its conversation.

    Deletion and stale sync transcript revisions are refused. Lifecycle state is not:
    processors re-derive their verdict from current content, so earlier discard or
    status bookkeeping must not strand rows a later sync filled with speech.

    ``on_first_completion`` runs after a successful commit that transitioned the
    existing row onto ``completed``. It must not raise; the persist outcome is
    independent of observers.
    """
    conversation_data.pop('updated_at', None)
    if 'audio_base64_url' in conversation_data:
        del conversation_data['audio_base64_url']
    if 'photos' in conversation_data:
        del conversation_data['photos']

    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_data['id'])

    stale_sync_revision = False
    first_completed = False
    summary_receipt = None
    summary_changed = False

    @firestore.transactional
    def _persist(transaction) -> bool:
        nonlocal stale_sync_revision, first_completed, summary_receipt, summary_changed
        summary_changed = False
        summary_receipt = None
        stale_sync_revision = False
        first_completed = False
        write_data = copy.deepcopy(conversation_data)
        # Capture-group membership has one writer (database.capture_groups).
        write_data.pop(CAPTURE_GROUP_FIELD, None)
        existing_snapshot = conversation_ref.get(transaction=transaction)
        if not getattr(existing_snapshot, 'exists', False):
            # A processor is never an authority to recreate a conversation.
            # Deleting one is a decision its owner made, and a merge write to a
            # missing document would create it, so a late processor could bring
            # back what they removed and emit derived side effects from it.
            return False

        existing = existing_snapshot.to_dict() or {}
        preserve_duplicate_hint(write_data, existing)
        if existing.get('record_lane_owner'):
            write_data['record_lane_owner'] = existing['record_lane_owner']
        if (
            existing.get('deleted')
            or summary_delivery.repair_fenced(existing)
            or summary_delivery.processing_fenced(existing)
        ):
            return False
        if smart_merge_refresh is not None:
            expected_revision, expected_owner = smart_merge_refresh
            merge_state = existing.get('smart_merge') or {}
            lease = merge_state.get('refresh_lease') or {}
            until = lease.get('until')
            if (
                merge_state.get('revision') != expected_revision
                or lease.get('owner') != expected_owner
                or not isinstance(until, datetime)
                or until <= datetime.now(timezone.utc)
            ):
                return False
        # A processor that read before another sync append cannot replace that
        # transcript or publish a summary derived from an obsolete revision.
        if existing.get('sync_content_revision') is not None and (
            write_data.get('sync_content_revision') != existing['sync_content_revision']
        ):
            stale_sync_revision = True
            return False

        if write_data.get('discarded') is True and _is_verified_recovery_discard(write_data):
            from utils.conversations.recovery import (
                RecoveryStructureUnavailableError,
                structured_has_protected_content,
            )

            try:
                _decode_transcript_segments_strict(
                    uid,
                    existing.get('transcript_segments', []),
                    bool(existing.get('transcript_segments_compressed')),
                    require_decryption=True,
                )
            except (TypeError, ValueError, zlib.error) as error:
                raise RecoveryStructureUnavailableError(
                    'server recovery discard requires a decoded transcript'
                ) from error
            # Admission and processing snapshots can precede a title edit or
            # restore. Refuse before writing any verdict/content: the existing
            # typed-minimum terminal path preserves a visible row and selfheal
            # reports dead_letter rather than a contradictory completed discard.
            if existing.get('sync_relevance_user_kept') or structured_has_protected_content(
                existing.get('structured'), existing.get('user_title')
            ):
                raise RecoveryStructureUnavailableError('server recovery discard lost to protected content')
        decision = write_data.get('relevance_decision')
        if isinstance(decision, dict) and decision.get('trigger') in {'server_recovery', 'silent_backfill'}:
            # Recovery enriches the durable capture; neither model normalization
            # nor a stale snapshot owns its encoding, audio, or speaker metadata.
            for field in (
                'transcript_segments',
                'transcript_segments_compressed',
                'data_protection_level',
                'audio_files',
                'speaker_resolution',
                match_scores.FIELD,
            ):
                write_data.pop(field, None)

        # Restoring a legacy review row is an explicit user decision. A
        # processor that started before the restore may still carry the old
        # review/discarded verdict, so preserve the server-owned marker and
        # force the restored lifecycle state on every successful merge.
        if existing.get('sync_relevance_user_kept'):
            write_data['sync_relevance_user_kept'] = True
            write_data['discarded'] = False
            write_data['sync_relevance'] = 'keep'

        # Generated processing content never owns user-managed fields.
        # A null existing value means "never user-set" (stub docs dump None
        # fields), so only non-null values are preserved — otherwise the
        # stub's folder_id: None would revert every AI folder assignment.
        for field in (
            'starred',
            'folder_id',
            'visibility',
            'user_title',
            'user_corrections',
            'user_corrections_compressed',
            'user_overview',
        ):
            if existing.get(field) is not None:
                write_data[field] = existing[field]

        # folder_id is user-owned even when explicitly cleared: the folder
        # move endpoints stamp folder_user_set, so "no folder" chosen by the
        # user (folder_id None + marker) must survive processing output.
        # Only a stub's never-user-touched None may be overwritten by the
        # AI folder assignment above.
        if existing.get('folder_user_set'):
            write_data['folder_id'] = existing.get('folder_id')

        user_title = effective_user_title(existing.get('user_title'))
        if user_title is not None:
            structured = write_data.get('structured')
            if not isinstance(structured, dict):
                structured = {}
                write_data['structured'] = structured
            structured['title'] = user_title

        if existing.get('user_overview'):
            write_data.setdefault('structured', {})['overview'] = existing['user_overview']

        _reapply_current_manual_assignments(uid, write_data, existing)
        guard_match_score_size(write_data, existing, getattr(conversation_ref, 'path', None))

        summary_receipt = summary_delivery.merge_result(existing, write_data, uid)
        summary_changed = processing_backlog.stage_transition(
            transaction, uid, conversation_data['id'], existing, write_data, firestore_client=db
        )
        transaction.set(conversation_ref, write_data, merge=True)
        existing_status = existing.get('status')
        write_status = write_data.get('status')
        first_completed = existing_status not in (
            ConversationStatus.completed,
            ConversationStatus.completed.value,
        ) and write_status in (ConversationStatus.completed, ConversationStatus.completed.value)
        return True

    persisted = run_transactional(db, _persist)
    stop_quiet_check_for_conversation(uid, conversation_data['id'], firestore_client=db)
    if summary_changed:
        _drop_summary_memo(uid)
    if persisted:

        summary_delivery.emit(summary_receipt)
    if persisted:
        invalidate_people_stats_cache(uid)
    if persisted or stale_sync_revision:
        _sync_conversation_search_index(uid, conversation_data['id'])
    else:
        # A processor result for a conversation whose owner is already gone:
        # converge the search index to absence too.
        _delete_conversation_search_index(uid, conversation_data['id'])
    if persisted and first_completed and on_first_completion is not None:
        try:
            on_first_completion()
        except Exception:
            pass
    return persisted


@set_data_protection_level(data_arg_name='conversation_data')
@prepare_for_write(
    data_arg_name='conversation_data',
    prepare_func=_prepare_conversation_for_write,
    preserve_result=True,
)
@after_write('conversations')
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

    summary_receipt = summary_delivery.creation_result(conversation_data, uid)
    summary_changed = False
    try:
        if conversation_data.get('processing_deferred'):

            @firestore.transactional
            def create_waiting(transaction):
                nonlocal summary_changed
                summary_changed = False
                if conversation_ref.get(transaction=transaction).exists:
                    raise AlreadyExists('conversation exists')
                summary_changed = processing_backlog.stage_transition(
                    transaction, uid, conversation_data['id'], {}, conversation_data, firestore_client=db
                )
                transaction.create(conversation_ref, conversation_data)

            run_transactional(db, create_waiting)
            if summary_changed:
                _drop_summary_memo(uid)
        else:
            conversation_ref.create(conversation_data)
    except (AlreadyExists, Conflict):
        # The conversation exists but may be new to the search index (writer
        # lag, backfill gap); the read-back sync converges it either way.
        _sync_conversation_search_index(uid, conversation_data['id'])
        return False
    summary_delivery.emit(summary_receipt)
    invalidate_people_stats_cache(uid)
    _sync_conversation_search_index(uid, conversation_data['id'])
    return True


@prepare_for_read(decrypt_func=prepare_conversation_for_read)
@with_photos(get_conversation_photos)
def get_conversation(
    uid,
    conversation_id,
    *,
    firestore_client: Any = None,
    read_site: FirestoreReadSite = FirestoreReadSite.UNATTRIBUTED,
    include_transcript_decode_status: bool = False,
):
    client = firestore_client if firestore_client is not None else db
    user_ref = client.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_data = document_data_with_revision(conversation_ref.get())
    record_document_read(
        read_site, FirestoreReadOutcome.HIT if conversation_data is not None else FirestoreReadOutcome.MISS
    )
    if conversation_data is not None and include_transcript_decode_status:
        # Recovery needs evidence from the raw field, before the tolerant read
        # decoder turns corruption into an empty transcript. Other readers keep
        # their existing behavior and never receive this server-only marker.
        try:
            _decode_transcript_segments_strict(
                uid,
                conversation_data.get('transcript_segments', []),
                bool(conversation_data.get('transcript_segments_compressed')),
                require_decryption=True,
            )
            conversation_data['_recovery_transcript_decoded'] = True
        except (TypeError, ValueError, zlib.error):
            conversation_data['_recovery_transcript_decoded'] = False
            conversation_data['transcript_segments'] = []
    return conversation_data


def get_conversation_raw_snapshot(
    uid: str, conversation_id: str, *, firestore_client: Any = None, field_paths: Optional[List[str]] = None
) -> Optional[Dict[str, Any]]:
    """Return the stored conversation document with no read-path decoding.

    Self-heal recovery verification compares the byte length of the stored
    (compressed/encrypted) transcript field against the length recorded at
    admission. The decoded ``get_conversation`` path would decompress it and
    make every correct recovery look like content drift, so this read is the
    raw ``to_dict()`` snapshot only.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)
    snapshot = ref.get() if field_paths is None else ref.get(field_paths=field_paths)
    if not getattr(snapshot, 'exists', False):
        return None
    return snapshot.to_dict()


def resolve_sync_conversation_redirect(
    uid: str, conversation_id: str, *, firestore_client: Any = None, max_hops: int = 16
) -> Optional[str]:
    """Resolve an owner bridge; user deletion remains terminal at every hop."""
    resolved = resolve_snapshot(
        uid,
        conversation_id,
        client_factory=lambda: firestore_client if firestore_client is not None else get_firestore_client(),
        max_hops=max_hops,
    )
    return resolved.conversation_id if resolved is not None else None


@prepare_for_read(decrypt_func=prepare_conversation_for_read)
@with_photos(get_conversation_photos)
def _hydrate_sync_conversation_snapshot(
    uid: str,
    conversation_data: dict,
    *,
    firestore_client: Any = None,
    read_site: FirestoreReadSite = FirestoreReadSite.UNATTRIBUTED,
) -> Optional[dict]:
    record_document_read(read_site, FirestoreReadOutcome.HIT)
    return conversation_data


@read_origin('job:sync_operation_snapshot')
def get_sync_redirected_conversation(
    uid: str,
    conversation_id: str,
    *,
    firestore_client: Any = None,
    read_site: FirestoreReadSite = FirestoreReadSite.UNATTRIBUTED,
) -> Optional[dict]:
    """Hydrate one checked snapshot; mutations still reread/CAS independently."""
    return read_redirected(
        uid,
        conversation_id,
        client_factory=lambda: firestore_client if firestore_client is not None else get_firestore_client(),
        hydrate=_hydrate_sync_conversation_snapshot,
        read_current=get_conversation,
        read_site=read_site,
    )


def get_manual_speaker_receipt(uid: str, conversation_id: str, *, firestore_client: Any = None) -> dict:
    """The conversation's manual speaker receipt alone, without reading its transcript."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    user_ref = client.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    snapshot = conversation_ref.get(field_paths=['manual_speaker_assignments', 'manual_speaker_assignments_compressed'])
    data = snapshot.to_dict() if getattr(snapshot, 'exists', False) else None
    if not data:
        return {}
    return decode_manual_speaker_assignments(
        uid, data.get('manual_speaker_assignments'), bool(data.get('manual_speaker_assignments_compressed'))
    )


def discover_public_conversation_owner(conversation_id: str, cached_uid: str = '') -> str:
    """Resolve a public owner from Firestore; cached hints never authorize access.

    IDs are not globally unique. Discovery accepts exactly one stored-id match,
    including private/deleted matches in the ambiguity check, and validates the
    actual users/{uid}/conversations/{id} path before trusting owner_uid.
    """
    from .firestore_read_metrics import FirestoreReadFamily, FirestoreReadMode, record_firestore_read

    fields = ['id', 'owner_uid', 'visibility', 'deleted', 'is_locked']
    if cached_uid:
        snapshot = (
            db.collection('users')
            .document(cached_uid)
            .collection(conversations_collection)
            .document(conversation_id)
            .get(field_paths=fields)
        )
        record_document_read(
            FirestoreReadSite.PUBLIC_CONVERSATION_OWNER_CACHE,
            FirestoreReadOutcome.HIT if snapshot.exists else FirestoreReadOutcome.MISS,
        )
        if snapshot.exists:
            candidates = [snapshot]
        else:
            candidates = []
    else:
        candidates = []
    if not candidates:
        candidates = list(
            db.collection_group(conversations_collection)
            .where(filter=FieldFilter('id', '==', conversation_id))
            .select(fields)
            .limit(2)
            .stream()
        )
        record_firestore_read(FirestoreReadFamily.PUBLIC_CONVERSATION_OWNER, FirestoreReadMode.BOUNDED, len(candidates))
    if len(candidates) != 1:
        return ''
    snapshot = candidates[0]
    path = snapshot.reference.path.split('/')
    if len(path) != 4 or path[0] != 'users' or path[2:] != [conversations_collection, conversation_id]:
        return ''
    raw = snapshot.to_dict() or {}
    uid = path[1]
    if (
        raw.get('id') != conversation_id
        or raw.get('owner_uid', uid) != uid
        or raw.get('visibility') not in {'shared', 'public'}
        or is_soft_deleted(raw)
        or raw.get('is_locked', False)
    ):
        return ''
    return uid


def get_public_shared_conversation_bounded(
    uid: str,
    conversation_id: str,
    *,
    firestore_client: Any = None,
) -> Optional[Dict[str, Any]]:
    """Read only public-chat fields and decode the transcript within fixed bounds."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    user_ref = client.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    snapshot = conversation_ref.get(
        field_paths=[
            'visibility',
            'deleted',
            'is_locked',
            'transcript_segments_compressed',
            'transcript_segments',
            'has_transcript_corrections',
        ]
    )
    record_document_read(
        FirestoreReadSite.PUBLIC_SHARED_CHAT,
        FirestoreReadOutcome.HIT if snapshot.exists else FirestoreReadOutcome.MISS,
    )
    if not snapshot.exists:
        return None
    raw = snapshot.to_dict()
    if not isinstance(raw, dict):
        return None

    if is_soft_deleted(raw):
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
            retain_anchors=True,
        )
    except ValueError:
        return None
    from utils.agent_capabilities.transcripts import project

    public_conversation.update(
        id=conversation_id, has_transcript_corrections=raw.get('has_transcript_corrections', False)
    )
    try:
        projected = project(uid, public_conversation, firestore_client=client)
        segments = projected['transcript_segments']
        if (
            any(len(segment['text']) > _PUBLIC_TRANSCRIPT_MAX_SEGMENT_TEXT_CHARS for segment in segments)
            or len(json.dumps(segments, ensure_ascii=False).encode()) > _PUBLIC_TRANSCRIPT_MAX_DECODED_BYTES
        ):
            return None
        for segment in segments:
            for field in ('id', 'segment_id', 'start', 'end'):
                segment.pop(field, None)
        projected.pop('id', None)
        projected.pop('has_transcript_corrections', None)
        return projected
    except ValueError:
        return None


def get_conversation_audio_stamp(uid: str, conversation_id: str) -> Optional[dict]:
    """Field-masked read of just the conversation_audio stamp — cheap enough for
    the pusher's per-batch staleness check (the full doc carries transcripts)."""
    doc_ref = db.collection('users').document(uid).collection(conversations_collection).document(conversation_id)
    snapshot = doc_ref.get(field_paths=['conversation_audio'])
    if not snapshot.exists:
        return None
    return (snapshot.to_dict() or {}).get('conversation_audio')


@_with_conversation_cursor_envelope
@prepare_for_read(decrypt_func=prepare_conversation_for_read)
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
    *,
    metadata_only: bool = False,
    cursor: Optional[str] = None,
    page_envelope: bool = False,
    cursor_page: Optional[Dict[str, Any]] = None,
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

    if metadata_only:
        # Support needs presence, never decoded content or photo hydration. Bound
        # the query itself, including discarded/deleted lifecycle evidence.
        fields = [
            'id',
            'started_at',
            'finished_at',
            'status',
            'postprocessing.status',
            'postprocessing_status',
            'audio_files',
            'transcript_segments_compressed',
            'discarded',
            'deleted',
        ]
        return [
            dict(doc.to_dict() or {}, id=doc.id)
            for doc in conversations_ref.select(fields).limit(limit).offset(offset).stream()
        ]

    return _collect_visible_conversation_page(
        conversations_ref,
        limit=limit,
        offset=offset,
        include_discarded=include_discarded,
        uid=uid,
        cursor=cursor,
        cursor_page=cursor_page,
        sort_field=sort_field,
        cursor_filters=dict(
            statuses=statuses,
            start_date=start_date,
            end_date=end_date,
            categories=categories,
            folder_id=folder_id,
            starred=starred,
        ),
    )


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
    if start_date or end_date:
        conversations_ref = conversations_ref.order_by('created_at', direction=firestore.Query.DESCENDING)
    result = conversations_ref.count().get()
    matching = int(result[0][0].value)
    matching -= conversation_visibility_counts.count_hidden(
        db.collection('users').document(uid).collection(conversations_collection),
        include_discarded=include_discarded,
        statuses=statuses,
        sources=sources,
        start_date=start_date,
        end_date=end_date,
        categories=categories,
        folder_id=folder_id,
        starred=starred,
    )
    return matching


def count_conversations_with_geolocation(uid: str, *, firestore_client: Any = None) -> int:
    """Approximate count of the user's conversations that carry a geolocation.

    Single-field ``geolocation.latitude != null`` aggregation, served by
    Firestore's automatic single-field index. Adding ``discarded == False``
    would combine an inequality with an equality and need a composite index
    that is not declared, so discarded conversations (including redirect
    tombstones, which are stamped ``discarded=True``) are included in this count.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    conversations_ref = client.collection('users').document(uid).collection(conversations_collection)
    query = conversations_ref.where(filter=FieldFilter('geolocation.latitude', '!=', None))
    result = query.count().get()
    return int(result[0][0].value or 0)


@_with_conversation_cursor_envelope
@prepare_for_read(decrypt_func=prepare_conversation_for_read)
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
    list_fields_only: bool = False,
    *,
    cursor: Optional[str] = None,
    page_envelope: bool = False,
    cursor_page: Optional[Dict[str, Any]] = None,
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
    if list_fields_only and indexed_list_reads_enabled():
        # The archive list contract permits omitted transcript detail. Exclude
        # the large blob before download/decompression and correction-overlay
        # point reads, rather than fetching it and discarding it at the router.
        # Keep every other response field and all visibility/title metadata.
        from models.conversation import Conversation

        fields = set(Conversation.model_fields) - {'transcript_segments', 'transcript_segments_compressed'}
        fields.update(
            {
                'data_protection_level',
                'user_title',
                'user_corrections_compressed',
                'deleted',
                'dream_duplicate_of',
                'relevance_decision',
                'sync_relevance_user_kept',
                'has_photos',
                'folder_user_set',
            }
        )
        conversations_ref = conversations_ref.select(sorted(fields))
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

    return _collect_visible_conversation_page(
        conversations_ref,
        limit=limit,
        offset=offset,
        include_discarded=include_discarded,
        budget=budget,
        uid=uid,
        cursor=cursor,
        cursor_page=cursor_page,
        cursor_filters=dict(
            statuses=statuses,
            sources=sources,
            start_date=start_date,
            end_date=end_date,
            categories=categories,
            folder_id=folder_id,
            starred=starred,
        ),
    )


@prepare_for_read(decrypt_func=prepare_conversation_for_read)
def get_mcp_conversations_by_id(
    uid: str,
    conversation_ids: List[str],
    *,
    include_transcript: bool,
    include_discarded: bool = False,
    firestore_client: Any = None,
    extra_field_paths: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Return MCP card fields, optionally with transcript blobs, without photos or other result payloads."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    conversations_ref = client.collection('users').document(uid).collection(conversations_collection)
    doc_refs = [conversations_ref.document(str(conversation_id)) for conversation_id in conversation_ids]
    field_paths = list(
        MCP_CONVERSATION_TRANSCRIPT_FIELD_PATHS if include_transcript else MCP_CONVERSATION_CARD_FIELD_PATHS
    )
    if extra_field_paths:
        field_paths.extend(extra_field_paths)
    docs = client.get_all(doc_refs, field_paths=list(field_paths))
    conversations_by_id: Dict[str, Dict[str, Any]] = {}
    for doc in docs:
        if not doc.exists:
            continue
        data = document_data_with_revision(doc)
        if data is None:
            continue
        if not is_visible_conversation(data, include_discarded=include_discarded):
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
        snapshots = list(iter_portability_guarded(batch_ref.stream()))
        for doc in snapshots:
            check_portability_read()
            conv = doc.to_dict()
            conv = prepare_conversation_for_read(conv, uid) or conv
            if not is_visible_conversation(conv, include_discarded=include_discarded):
                continue
            batch.append(conv)
        yield from batch
        if len(snapshots) < batch_size:
            break
        cursor = snapshots[-1]


def mark_playback_deferred(uid: str, conversation_id: str, epoch: str) -> bool:
    """Write opaque rollback metadata without reading or recreating the owner."""
    ref = db.collection('users').document(uid).collection(conversations_collection).document(conversation_id)
    try:
        ref.update({'playback_eager_epoch': epoch})
    except NotFound:
        return False
    return True


@after_write('conversations')
def update_conversation(
    uid: str, conversation_id: str, update_data: dict, *, record_owner_out: dict | None = None
) -> bool:
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

    if record_owner_out is not None:
        owner = doc_snapshot.to_dict().get('record_lane_owner')
        if owner in {'batch_live_v1', 'batch_sync_v1'}:
            record_owner_out[conversation_id] = owner
    doc_level = doc_snapshot.to_dict().get('data_protection_level', 'standard')
    if isinstance(update_data.get('audio_files'), list):
        update_data = {
            **update_data,
            'audio_files': retain_aliases(update_data['audio_files'], doc_snapshot.to_dict().get('audio_files') or []),
        }
    prepared_data = _prepare_conversation_for_write(update_data, uid, doc_level)
    guard_match_score_size(prepared_data, doc_snapshot.to_dict(), getattr(doc_ref, 'path', None))
    try:
        doc_ref.update(prepared_data)
    except NotFound:
        # The conversation was deleted between the existence read above and
        # this commit. The contract of this function is to report a gone owner
        # as False — not to raise — so callers like the pusher's private-cloud
        # audio sync take their designed gone-owner path (stop syncing, release
        # the audio budget) instead of logging an ERROR and retrying forever.
        return False
    invalidate_people_stats_cache(uid)
    if _SEARCH_INDEXED_FIELD_ROOTS.intersection(str(key).split('.', 1)[0] for key in update_data):
        _sync_conversation_search_index(uid, conversation_id)
    return True


def claim_record_lane_owner(uid: str, conversation_id: str, owner: str, expected_updated_at, *, firestore_client=None):
    """CAS against the caller's loaded revision: one owner, zero added reads."""
    if owner not in {'batch_live_v1', 'batch_sync_v1', 'legacy_final_pass_v1'} or expected_updated_at is None:
        return None
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection(conversations_collection).document(conversation_id)
    try:
        result = ref.update(
            {'record_lane_owner': owner}, option=client.write_option(last_update_time=expected_updated_at)
        )
    except (NotFound, FailedPrecondition):
        return None
    return result.update_time


def seal_record_audio(uid: str, conversation_id: str) -> bool:
    """Pusher's upload barrier: blind metadata update, never recreates a row."""
    ref = (
        get_firestore_client()
        .collection('users')
        .document(uid)
        .collection(conversations_collection)
        .document(conversation_id)
    )
    try:
        ref.update({'record_audio_closed': True})
    except NotFound:
        return False
    return True


def refresh_conversation_after_chat_edit(uid: str, conversation_id: str) -> None:
    """Reconcile derived conversation views after an edit or inverse commits."""
    invalidate_people_stats_cache(uid)
    _sync_conversation_search_index(uid, conversation_id)


def record_demand_enrichment_checkpoint(
    uid: str, conversation_id: str, digest: str, *, firestore_client: Any = None
) -> bool:
    """Blind metadata-only checkpoint. Never recreate a removed conversation."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('users').document(uid).collection(conversations_collection).document(conversation_id)
    try:
        ref.update({'demand_enrichment_applied_hash': digest})
    except NotFound:
        return False
    return True


def update_conversation_chat(uid: str, conversation_id: str, expected: dict, update_data: dict) -> dict:
    """Apply a confirmed correction without touching transcript or lifecycle fields."""
    raw = get_conversation_raw_snapshot(uid, conversation_id)
    if raw is None:
        raise PermissionError('Conversation removed')
    prepared = _prepare_conversation_for_write(update_data, uid, raw.get('data_protection_level', 'standard'))
    after = chat_edits.apply_update(uid, 'conversation', conversation_id, expected, prepared)
    refresh_conversation_after_chat_edit(uid, conversation_id)
    return after


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
    user_ref = client.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    marker_ref = conversation_ref.collection('analytics_markers').document('conversation_memories_extracted')
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
    chunks = list_audio_chunks(uid, conversation_id, source_identity=True)
    if not chunks:
        return []

    # Group chunks based on gap rule (90s threshold accommodates both 5s and 60s
    # chunk durations). v2 listings split at actual uncovered ends or overlaps.
    audio_files = []
    for chunk_group in group_chunks_by_coverage(chunks, gap_threshold=90):
        audio_file = _finalize_audio_file_group(uid, conversation_id, chunk_group, audio_files)
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
    source_hash = source_fingerprint(chunk_group)
    file_id = (
        str(uuid.uuid5(uuid.NAMESPACE_OID, f'{uid}/{conversation_id}/{source_hash}'))
        if source_hash
        else str(uuid.uuid4())
    )

    # Extract timestamps
    timestamps = [chunk['timestamp'] for chunk in chunk_group]

    # v2 groups carry validated contiguous coverage spans from blob metadata;
    # duration is the authoritative span extent, never an encoded-size guess.
    spans: List[Tuple[float, float]] = []
    playback_starts: List[float] = []
    for chunk in chunk_group:
        span = chunk.get('span')
        if not isinstance(span, dict):
            spans = []
            break
        try:
            start = float(span['start'])
            samples = float(span['samples'])
            rate = float(span['sample_rate'])
        except (KeyError, TypeError, ValueError):
            spans = []
            break
        if samples <= 0 or rate <= 0:
            spans = []
            break
        spans.append((start, start + samples / rate))
        playback_start = span.get('playback_start')
        if isinstance(playback_start, (int, float)):
            playback_starts.append(float(playback_start))

    if spans:
        started_at = datetime.fromtimestamp(spans[0][0], tz=timezone.utc)
        duration = spans[-1][1] - spans[0][0]
        return AudioFile(
            id=file_id,
            source_fingerprint=source_hash,
            uid=uid,
            conversation_id=conversation_id,
            chunk_timestamps=timestamps,
            provider='gcp',
            started_at=started_at,
            duration=duration,
            chunk_spans=[ChunkSpan(start=round(start, 3), end=round(end, 3)) for start, end in spans],
            # The normalized wall basis holds only when every chunk in the
            # group carries its persisted playback start; one legacy chunk
            # leaves the part on the raw capture clock.
            playback_start=(min(playback_starts) if len(playback_starts) == len(spans) else None),
        )

    # Calculate started_at and duration from timestamps and blob sizes
    started_at = datetime.fromtimestamp(chunk_group[0]['timestamp'], tz=timezone.utc)
    last_chunk_start = datetime.fromtimestamp(chunk_group[-1]['timestamp'], tz=timezone.utc)
    # Estimate last chunk duration from blob size (PCM16 mono at 16kHz = 32000 bytes/sec).
    # Approximate for opus-encoded blobs; conversation_audio.captured_duration (from
    # decoded PCM) is the display source of truth.
    last_chunk_size = chunk_group[-1].get('size') or 0
    last_chunk_duration = last_chunk_size / 32000.0 if last_chunk_size > 0 else 5.0
    duration = (last_chunk_start - started_at).total_seconds() + last_chunk_duration

    return AudioFile(
        id=file_id,
        source_fingerprint=source_hash,
        uid=uid,
        conversation_id=conversation_id,
        chunk_timestamps=timestamps,
        provider='gcp',
        started_at=started_at,
        duration=duration,
    )


@after_write('conversations')
def update_conversation_title(uid: str, conversation_id: str, title: str):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)

    doc_snapshot = conversation_ref.get()
    if not doc_snapshot.exists:
        return

    conversation_ref.update({'structured.title': title, 'user_title': title})
    _sync_conversation_search_index(uid, conversation_id)


@after_write('conversations')
def update_conversation_summary(uid: str, conversation_id: str, app_id: Optional[str], content: str) -> str:
    """
    Update the conversation's displayed summary.

    If app_id is None: writes to structured.overview (default backend overview)
    and removes the structured sections projection.  Sections are a structured
    representation of the generated overview; once a user edits the overview,
    retaining them would expose stale evidence or let a client compose the old
    note after the new text.
    If app_id is set: rewrites the matching apps_results entry's content.

    The read and write are one transaction so the edit cannot be based on a
    stale app-result array, and both paths advance ``updated_at`` together with
    the content mutation.

    Returns:
        'ok' on success, 'not_found' if conversation missing,
        'app_result_not_found' if app_id given but no matching apps_results entry,
        'app_result_ambiguous' if multiple entries share that app_id.
    """
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)

    @firestore.transactional
    def _update(transaction) -> str:
        doc_snapshot = conversation_ref.get(transaction=transaction)
        if not doc_snapshot.exists:
            return 'not_found'

        updated_at = datetime.now(timezone.utc)
        if app_id is None:
            transaction.update(
                conversation_ref,
                {
                    'structured.overview': content,
                    'structured.sections': firestore.DELETE_FIELD,
                    'updated_at': updated_at,
                },
            )
            return 'ok'

        raw = doc_snapshot.to_dict() or {}
        stored_results = raw.get('apps_results') or []
        apps_results = copy.deepcopy(stored_results) if isinstance(stored_results, list) else []
        if sum(isinstance(entry, dict) and entry.get('app_id') == app_id for entry in apps_results) > 1:
            return 'app_result_ambiguous'
        for entry in apps_results:
            if isinstance(entry, dict) and entry.get('app_id') == app_id:
                entry['content'] = content
                transaction.update(conversation_ref, {'apps_results': apps_results, 'updated_at': updated_at})
                return 'ok'
        return 'app_result_not_found'

    result = run_transactional(db, _update)
    if result == 'ok' and app_id is None:
        _sync_conversation_search_index(uid, conversation_id)
    return result


@after_write('conversations')
def update_conversation_segment_text(
    uid: str, conversation_id: str, segment_id: str, text: str, *, firestore_client: Any = None
) -> str:
    """Correct a captured segment through an encrypted, journaled projection."""
    from database.review_transcript_changes import edit_user_segment

    return edit_user_segment(uid, conversation_id, segment_id, text, firestore_client=firestore_client)


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
    speaker_auto_enroll.retract_conversation(uid, conversation_id, firestore_client=db)
    try:
        # A deleted capture must not stay listed as a member of its event.
        leave_capture_group(uid, conversation_id, sticky=False, close=True, firestore_client=db)
    except Exception:
        logger.warning('capture group cleanup failed before delete conversation=%s', conversation_id)
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    for sub in conversation_ref.collections():
        delete_collection_recursive(sub, client=db)
    conversation_ref.delete()
    stop_quiet_check_for_conversation(uid, conversation_id, firestore_client=db)
    from config.stt_cap_dispatch import any_execution_admission_enabled

    if any_execution_admission_enabled(uid):
        processing_backlog.remove(uid, conversation_id)
    # Corrections are a sibling owner collection, not a child of the capture.
    user_ref.collection('transcript_corrections').document(conversation_id).delete()
    invalidate_people_stats_cache(uid)
    from database.proactivity import purge_source_items

    purge_source_items(uid=uid, source_kind='conversation', source_id=conversation_id, firestore_client=db)
    # A shadow metric writer can have read the parent just before deletion and
    # committed a child after our first enumeration. Its transaction prevents
    # writes once the parent is gone; this second sweep catches that narrow
    # pre-delete commit without leaving an orphan under a missing parent.
    for sub in conversation_ref.collections():
        delete_collection_recursive(sub, client=db)
    _delete_conversation_search_index(uid, conversation_id)


@prepare_for_read(decrypt_func=prepare_conversation_for_read)
@with_photos(get_conversation_photos)
def get_conversations_by_id(
    uid,
    conversation_ids,
    include_discarded: bool = False,
    *,
    read_site: FirestoreReadSite = FirestoreReadSite.UNATTRIBUTED,
):
    return _get_conversations_by_id(uid, conversation_ids, include_discarded=include_discarded, read_site=read_site)


@prepare_for_read(decrypt_func=prepare_conversation_for_read, read_budget_arg='read_budget')
def get_conversations_by_id_without_photos(
    uid,
    conversation_ids,
    include_discarded: bool = False,
    *,
    read_site: FirestoreReadSite = FirestoreReadSite.UNATTRIBUTED,
    read_budget: Optional[ListReadBudget] = None,
):
    return _get_conversations_by_id(
        uid, conversation_ids, include_discarded=include_discarded, read_site=read_site, read_budget=read_budget
    )


def _get_conversations_by_id(
    uid,
    conversation_ids,
    include_discarded: bool = False,
    *,
    read_site: FirestoreReadSite = FirestoreReadSite.UNATTRIBUTED,
    read_budget: Optional[ListReadBudget] = None,
):
    user_ref = db.collection('users').document(uid)
    conversations_ref = user_ref.collection(conversations_collection)

    doc_refs = [conversations_ref.document(str(conversation_id)) for conversation_id in conversation_ids]
    docs = budgeted_get_all(db, doc_refs, read_budget)

    hits = 0
    misses = 0
    conversations_by_id = {}
    for doc in docs:
        if doc.exists:
            hits += 1
            data = doc.to_dict()
            if not is_visible_conversation(data, include_discarded=include_discarded):
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
    Migrates each conversation atomically; photos retain their batched migration path.
    """
    batch = db.batch()
    batch_count = 0
    conversations_ref = db.collection('users').document(uid).collection(conversations_collection)
    doc_refs = [conversations_ref.document(conv_id) for conv_id in conversation_ids]
    doc_snapshots = db.get_all(
        doc_refs,
        field_paths=[
            'data_protection_level',
            'transcript_segments',
            'transcript_segments_compressed',
            'manual_speaker_assignments',
            'manual_speaker_assignments_compressed',
        ],
    )

    for doc_snapshot in doc_snapshots:
        if not doc_snapshot.exists:
            logger.warning(f"Conversation {doc_snapshot.id} not found, skipping.")
            continue

        @firestore.transactional
        def _migrate(transaction):
            current = doc_snapshot.reference.get(transaction=transaction).to_dict()
            if not current or current.get('deleted') or current.get('visibility') in ('public', 'shared'):
                return False
            if current.get('data_protection_level', 'standard') == target_level:
                return False
            payload = {'data_protection_level': target_level}
            had_match_scores = match_scores.FIELD in current
            if 'transcript_segments' in current:
                payload['transcript_segments'] = _decode_transcript_segments_strict(
                    uid, current['transcript_segments'], bool(current.get('transcript_segments_compressed'))
                )
            if match_scores.FIELD in current:
                _reveal_match_scores_for_read(current, uid)
                if match_scores.FIELD in current:
                    payload[match_scores.FIELD] = current[match_scores.FIELD]
            if OPEN_LOOP_EXTRACTIONS_FIELD in current:
                payload[OPEN_LOOP_EXTRACTIONS_FIELD] = decode_open_loop_extractions(
                    uid,
                    current[OPEN_LOOP_EXTRACTIONS_FIELD],
                    bool(current.get(OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD)),
                )
            if 'manual_speaker_assignments' in current:
                payload['manual_speaker_assignments'] = decode_manual_speaker_assignments(
                    uid,
                    current['manual_speaker_assignments'],
                    bool(current.get('manual_speaker_assignments_compressed')),
                )
            prepared = _prepare_conversation_for_write(
                payload, uid, target_level, preserve_transcript_identity=bool(current.get('has_transcript_corrections'))
            )
            guard_match_score_size(prepared, current, getattr(doc_snapshot.reference, 'path', None))
            if had_match_scores and match_scores.FIELD not in prepared:
                # Failed re-encryption must not retain a standard blob after
                # the document switches to enhanced protection.
                prepared[match_scores.FIELD] = firestore.DELETE_FIELD
            if 'manual_speaker_assignments' in payload and not payload['manual_speaker_assignments']:
                prepared['manual_speaker_assignments'] = firestore.DELETE_FIELD
                prepared['manual_speaker_assignments_compressed'] = firestore.DELETE_FIELD
            transaction.update(doc_snapshot.reference, prepared)
            return True

        if not run_transactional(db, _migrate):
            continue

        # Photos retain their separate batched migration path.
        photos_ref = doc_snapshot.reference.collection('photos')
        photos_stream = photos_ref.select(['data_protection_level', 'base64']).stream()
        for photo_doc in photos_stream:
            photo_data = photo_doc.to_dict()
            current_photo_level = photo_data.get('data_protection_level', 'standard')
            if current_photo_level == target_level:
                continue

            # Decrypt first to get a clean state
            plain_photo_data = prepare_photo_for_read(photo_data, uid)

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


@prepare_for_read(decrypt_func=prepare_conversation_for_read)
@with_photos(get_conversation_photos)
def get_in_progress_conversation(uid: str):
    user_ref = db.collection('users').document(uid)
    conversations_ref = user_ref.collection(conversations_collection).where(
        filter=FieldFilter('status', '==', 'in_progress')
    )
    conversations_ref = conversations_ref.order_by('created_at', direction=firestore.Query.DESCENDING).limit(8)
    docs = [doc.to_dict() for doc in conversations_ref.stream()]
    conversations = [conversation for conversation in docs if conversation and not is_soft_deleted(conversation)]
    conversation = conversations[0] if conversations else None
    return conversation


@prepare_for_read(decrypt_func=prepare_conversation_for_read)
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
    conversations = [c for c in conversations if not c.get('deferred') and not is_soft_deleted(c)]
    return conversations


@prepare_for_read(decrypt_func=prepare_conversation_for_read)
def get_conversations_finished_after(
    uid: str,
    *,
    status: str,
    finished_after: datetime,
    limit: int = 25,
    firestore_client=None,
) -> List[Dict[str, Any]]:
    """Conversations in ``status`` whose last activity is at or after ``finished_after``.

    Duplicate-capture detection (#3244) asks for the captures that were still
    running when this recording started; ordering by the activity clock keeps
    the bounded page on the rows nearest that start. Later rows may also
    overlap; the caller reports saturation. Photos are not loaded.
    """
    client = firestore_client or get_firestore_client()
    user_ref = client.collection('users').document(uid)
    conversations_ref = (
        CONVERSATIONS_BY_STATUS_FINISHED_AFTER_QUERY.build(
            user_ref.collection(conversations_collection),
            {'status': status, 'finished_after': finished_after},
            field_filter_factory=FieldFilter,
        )
        .order_by('finished_at', direction=firestore.Query.ASCENDING)
        .limit(limit)
    )
    conversations: List[Dict[str, Any]] = []
    for doc in conversations_ref.stream():
        data = doc.to_dict()
        if data and not is_soft_deleted(data):
            conversations.append(data)
    return conversations


def get_conversation_for_capture_check(uid: str, conversation_id: str, *, firestore_client=None):
    """Decrypted conversation plus the fingerprint of the stored transcript, from one snapshot.

    Capture grouping confirms shared speech on the decrypted text, then fences
    its transaction on the fingerprint so a transcript that changed in between
    cannot be grouped on stale evidence. Returns ``(None, None)`` when absent.
    """
    client = firestore_client or get_firestore_client()
    user_ref = client.collection('users').document(uid)
    snapshot = user_ref.collection(conversations_collection).document(conversation_id).get()
    raw = snapshot.to_dict() if getattr(snapshot, 'exists', False) else None
    if not raw:
        return None, None
    return prepare_conversation_for_read(raw, uid), transcript_fingerprint(raw)


def link_duplicate_capture(uid: str, primary: Any, secondary: Any, overlap: dict, *, firestore_client=None) -> bool:
    """Add a hint only while both completed capture snapshots still match.

    Read both documents before writing; deletion, discard, or capture-window
    changes after discovery fence the link. Never alter lifecycle or content.
    """
    client = firestore_client or get_firestore_client()
    collection = client.collection('users').document(uid).collection(conversations_collection)
    primary_ref = collection.document(primary.conversation_id)
    secondary_ref = collection.document(secondary.conversation_id)

    @firestore.transactional
    def link(transaction):
        primary_row = primary_ref.get(transaction=transaction).to_dict()
        secondary_row = secondary_ref.get(transaction=transaction).to_dict()
        for row, expected in ((primary_row, primary), (secondary_row, secondary)):
            if not row or row.get('discarded') or row.get('deleted') or row.get('status') != 'completed':
                return False
            compared = lifecycle_clocks.overlap_fields(uid, row)
            if any(
                compared.get(field) != getattr(expected, field) for field in ('started_at', 'finished_at', 'source')
            ):
                return False
        external_data = dict(secondary_row.get('external_data') or {})
        if external_data.get('duplicate_capture_of') or (primary_row.get('external_data') or {}).get(
            'duplicate_capture_of'
        ):
            return False
        external_data.update(
            duplicate_capture_of=primary.conversation_id,
            cross_device_duplicate={**overlap, 'primary_conversation_id': primary.conversation_id},
        )
        transaction.update(secondary_ref, {'external_data': external_data})
        return True

    return run_transactional(client, link)


def transition_conversation_status(uid: str, conversation_id: str, status: str):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.update({'status': status})
    if status != 'in_progress':
        stop_quiet_check_for_conversation(uid, conversation_id, firestore_client=db)
    invalidate_people_stats_cache(uid)


def claim_conversation_status(
    uid: str,
    conversation_id: str,
    expected_status: ConversationStatus,
    claimed_status: ConversationStatus,
    extra_updates: Optional[Dict[str, Any]] = None,
    *,
    expected_fields: Optional[Dict[str, Any]] = None,
    allow_discarded: bool = False,
) -> bool:
    """CAS the status and optional privacy/job-generation guards.

    Projection updates bind to this transaction's stored transcript. A stale
    hash-bound projection is dropped without failing the status claim.
    """
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)

    @firestore.transactional
    def _claim(transaction):
        snapshot = conversation_ref.get(transaction=transaction)
        if not snapshot.exists:
            raise NotFound(f'Conversation {conversation_id} not found')
        current = snapshot.to_dict() or {}
        if (current.get('discarded') and not allow_discarded) or current.get('status') != expected_status.value:
            return False
        if any(
            (bool(current.get(k)) if isinstance(v, bool) else current.get(k)) != v
            for k, v in (expected_fields or {}).items()
        ):
            return False
        updates = {'status': claimed_status.value}
        if extra_updates:
            # Digest check against THIS snapshot, not a route-level read.
            # A T1-validated projection must not land on a T2 transcript.
            corrections = None
            if current.get('has_transcript_corrections'):
                from utils.agent_capabilities.transcripts import load_entries

                corrections = load_entries(uid, conversation_id, firestore_client=db, transaction=transaction)
            updates.update(
                extra_updates_with_bound_client_processing(
                    uid, current, extra_updates, transcript_corrections=corrections
                )
            )
        if expected_status == ConversationStatus.processing and claimed_status == ConversationStatus.in_progress:
            restore_quiet_check_in_transaction(transaction, db, uid, conversation_id, current | updates)
        transaction.update(conversation_ref, updates)
        return True

    claimed = run_transactional(db, _claim)
    if claimed:
        if claimed_status != ConversationStatus.in_progress:
            stop_quiet_check_for_conversation(uid, conversation_id, firestore_client=db)
        invalidate_people_stats_cache(uid)
        if serving_for('LIFECYCLE_V2_MODE', uid):
            _sync_conversation_search_index(uid, conversation_id)
    return claimed


def set_conversation_as_discarded(uid: str, conversation_id: str):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.update({'discarded': True, 'sync_relevance_user_kept': False})
    stop_quiet_check_for_conversation(uid, conversation_id, firestore_client=db)
    invalidate_people_stats_cache(uid)
    _sync_conversation_search_index(uid, conversation_id)


def rule_discard_outcome(
    uid: str,
    conversation_id: str,
    relevance_decision: dict,
    *,
    expected_sync_content_revision: Optional[int] = None,
) -> str:
    """Hide a row the relevance rules settled after the fact (backfill).

    Transactional so it never overrides what happened since the scan: a
    deleted, user-restored or revised row is ``refused``. A row that is already
    stored hidden is ``already_discarded``: that state is what the caller wanted,
    but nothing changed, so no cache or index side effect runs. Only a write
    returns ``discarded``.
    """
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)

    @firestore.transactional
    def _discard(transaction):
        snapshot = conversation_ref.get(transaction=transaction)
        if not getattr(snapshot, 'exists', False):
            return 'refused'
        current = snapshot.to_dict() or {}
        if is_soft_deleted(current):
            return 'refused'
        if current.get('discarded'):
            return 'already_discarded'
        status = getattr(current.get('status'), 'value', current.get('status'))
        if status != 'completed' or is_user_curated(current):
            return 'refused'
        if (
            expected_sync_content_revision is not None
            and current.get('sync_content_revision') != expected_sync_content_revision
        ):
            return 'refused'
        transaction.update(conversation_ref, {'discarded': True, 'relevance_decision': relevance_decision})
        return 'discarded'

    outcome = run_transactional(db, _discard)
    if outcome in {'discarded', 'already_discarded'}:
        stop_quiet_check_for_conversation(uid, conversation_id, firestore_client=db)
    if outcome == 'discarded':
        invalidate_people_stats_cache(uid)
        _sync_conversation_search_index(uid, conversation_id)
    return outcome


def discard_by_relevance(
    uid: str,
    conversation_id: str,
    relevance_decision: dict,
    *,
    expected_sync_content_revision: Optional[int] = None,
) -> bool:
    """True only when this call hid the row; see ``rule_discard_outcome``."""
    return (
        rule_discard_outcome(
            uid,
            conversation_id,
            relevance_decision,
            expected_sync_content_revision=expected_sync_content_revision,
        )
        == 'discarded'
    )


def restore_conversation_from_discarded(uid: str, conversation_id: str):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)

    @firestore.transactional
    def _restore(transaction):
        snapshot = conversation_ref.get(transaction=transaction)
        if not getattr(snapshot, 'exists', False):
            return False
        current = snapshot.to_dict() or {}
        if is_soft_deleted(current):
            # Redirect tombstones reuse discarded=True for the indexed hide.
            # Restoring them would put a merged-away donor back on lists.
            return False
        # A restore is the user's verdict and outranks every later relevance
        # assessment (sync appends reassess the whole recording). Legacy review
        # rows are also hidden by the read predicate, so they flip to keep.
        updates = {'discarded': False, 'sync_relevance_user_kept': True}
        if current.get('sync_relevance') == 'review':
            updates['sync_relevance'] = 'keep'
        relevance_decision = current.get('relevance_decision')
        if (
            current.get('discarded')
            and isinstance(relevance_decision, Mapping)
            and relevance_decision.get('verdict') == 'discard'
            and relevance_decision.get('decided_by') == 'jev'
        ):
            # Restored-from-Jev stays countable after reassessment replaces
            # relevance_decision; the marker is written once and never cleared.
            updates['jev_discard_restored'] = True
        transaction.update(conversation_ref, updates)
        return True

    restored = run_transactional(db, _restore)
    if restored:
        invalidate_people_stats_cache(uid)
        _sync_conversation_search_index(uid, conversation_id)
    return restored


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


def _page_eligible_action_item_count(conversation: dict, include_completed: bool) -> int:
    """How many of a conversation's action items the flattening below would keep."""
    kept = 0
    for item in conversation.get('structured', {}).get('action_items', []):
        if isinstance(item, dict):
            if item.get('deleted', False):
                continue
            if not include_completed and item.get('completed', False):
                continue
        kept += 1
    return kept


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

    # Read only as far as the requested page needs. The stream is ordered by the
    # same created_at the flattened items are sorted by, and every item inherits
    # its conversation's timestamp, so the first offset+limit items collected here
    # are the ones the slice at the end would have kept anyway.
    needed = offset + limit
    conversations = []
    collected = 0
    for doc in conversations_ref.stream():
        conversation_data = doc.to_dict()
        if is_soft_deleted(conversation_data):
            continue

        # Check if conversation has action items
        structured = conversation_data.get('structured', {})
        raw_action_items = structured.get('action_items', [])

        if raw_action_items:
            # Decrypt conversation data for proper reading
            decrypted_data = prepare_conversation_for_read(conversation_data, uid)
            conversations.append(decrypted_data)
            collected += _page_eligible_action_item_count(decrypted_data, include_completed)
            if needed > 0 and collected >= needed:
                break

    # Extract and flatten action items with metadata
    action_items = []
    for conversation in conversations:
        conversation_id = conversation['id']
        conversation_title = conversation.get('structured', {}).get('title', 'Untitled')
        conversation_created_at = ensure_timezone_aware(conversation['created_at'])

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
                created_at = ensure_timezone_aware(created_at)
            if completed_at is not None:
                completed_at = ensure_timezone_aware(completed_at)

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
    conversation_ref.update({'finished_at': finished_at, **lifecycle_clocks.activity_updates(uid, {}, finished_at)})
    invalidate_people_stats_cache(uid)
    # refactor: superseded by status-change indexing when LIFECYCLE_V2_MODE=serve
    if not serving_for('LIFECYCLE_V2_MODE', uid):
        _sync_conversation_search_index(uid, conversation_id)


def clear_client_processing(payload: Dict[str, Any]) -> None:
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


def summary_source_reference_invalidations(structured: Any, segment_id: str) -> Dict[str, Any]:
    """Return structured fields whose evidence includes an edited segment.

    Structured summaries remain user-visible after a transcript edit, so this
    deliberately preserves every item's content and metadata. Clearing the
    complete reference list for an affected item avoids presenting a partial
    set of IDs as authoritative for text that has changed. The returned paths
    are suitable for merging into the same Firestore transaction payload.
    """
    if not isinstance(structured, dict):
        return {}

    invalidations: Dict[str, Any] = {}
    for field in ('sections', 'action_items'):
        items = structured.get(field)
        if not isinstance(items, list):
            continue

        copied_items = copy.deepcopy(items)
        changed = False
        for item in copied_items:
            if not isinstance(item, dict):
                continue
            references = item.get('source_segment_ids')
            if isinstance(references, (list, tuple, set)) and segment_id in references:
                item['source_segment_ids'] = []
                changed = True
        if changed:
            invalidations[f'structured.{field}'] = copied_items

    claims = structured.get('note_claims')
    if isinstance(claims, list):
        kept = [claim for claim in claims if not claim_references_segment(claim, segment_id)]
        if len(kept) != len(claims):
            invalidations['structured.note_claims'] = kept

    return invalidations


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
    *,
    transcript_corrections: list[dict] | None = None,
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
        if current.get('has_transcript_corrections'):
            from utils.agent_capabilities.transcripts import apply_entries

            if transcript_corrections is None:
                raise ValueError('Transcript corrections must be read in the binding transaction')
            segments = apply_entries(segments, transcript_corrections)
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
        corrections = None
        if current.get('has_transcript_corrections'):
            from utils.agent_capabilities.transcripts import load_entries

            try:
                corrections = load_entries(uid, conversation_id, firestore_client=client, transaction=transaction)
            except ValueError:
                return False
        bound_updates = extra_updates_with_bound_client_processing(
            uid, current, mutation, transcript_corrections=corrections
        )
        if not any(field in bound_updates for field in PROJECTION_FAMILY_FIELDS):
            return False
        transaction.update(doc_ref, bound_updates)
        return True

    return run_transactional(client, _bind)


def assign_conversation_speaker(
    uid: str,
    conversation_id: str,
    *,
    person_id=None,
    is_user=False,
    segment_ids=None,
    speaker_id=None,
    segment_index=None,
    use_for_speech_training=True,
    evidence_source=SOURCE_MANUAL,
    firestore_client=None,
    rejection=None,
    owner_segment_ids=None,
    time_range=None,
    segment_only=False,
    owner_confirmation=None,
):
    """Commit the manual edit, provenance, label evidence and invalidation in one transaction."""
    from database.speaker_assignment_effects import persist_assignment_effects, run_assignment_transaction
    from database.speaker_learning_jobs import extract_learning_receipt_markers, record_speaker_learning_job_events

    validate_assignment_range(time_range)
    rejection = normalize_rejection(rejection)
    client = firestore_client if firestore_client is not None else get_firestore_client()
    user_ref = client.collection('users').document(uid)
    collection = user_ref.collection(conversations_collection)

    def assign(transaction, bookkeeping):
        if not (source := collection.document(conversation_id).get(transaction=transaction).to_dict()):
            raise LookupError('Conversation not found')
        if owner_confirmation is not None and source.get('deleted'):
            raise LookupError('Owner question conversation changed')
        source_segments = None
        selected_segment_ids, selected_speaker_id, selected_segment_index = segment_ids, speaker_id, segment_index
        current_id, raw, seen = conversation_id, source, set()
        while raw.get('deleted') and raw.get('sync_merged_into'):
            if current_id in seen or len(seen) >= 16:
                raise LookupError('Conversation not found')
            seen.add(current_id)
            if source_segments is None:
                source_segments = _decode_transcript_segments_strict(
                    uid, source.get('transcript_segments', []), bool(source.get('transcript_segments_compressed'))
                )
            current_id = raw['sync_merged_into']
            if not (raw := collection.document(current_id).get(transaction=transaction).to_dict()):
                raise LookupError('Conversation not found')
        if raw.get('deleted'):
            raise LookupError('Conversation not found')
        ref = collection.document(current_id)
        if raw.get('is_locked'):
            raise PermissionError('Conversation is locked')
        # Bridge donors use stable segment IDs, never reassigned speaker numbers.
        if source_segments is not None:
            selected_segment_ids = donor_selected_ids(
                source_segments,
                segment_ids=segment_ids,
                speaker_id=speaker_id,
                segment_index=segment_index,
                strict_speaker=rejection is not None,
                time_range=time_range,
            )
            selected_speaker_id = selected_segment_index = None
        current = copy.deepcopy(raw)
        _reveal_user_corrections_for_read(current, uid)
        current['id'] = current_id
        current['transcript_segments'] = _decode_transcript_segments_strict(
            uid, raw.get('transcript_segments', []), bool(raw.get('transcript_segments_compressed'))
        )
        current['manual_speaker_assignments'] = decode_manual_speaker_assignments(
            uid, raw.get('manual_speaker_assignments'), bool(raw.get('manual_speaker_assignments_compressed'))
        )
        owner_updates = {}
        if owner_confirmation is not None:
            # Read-only conversation consumers do not depend on prompt models.
            # Load the authorization contract only for the explicit excerpt path.
            from utils.speaker_tag_prompts.owner_confirmation import (
                FIELD as OWNER_CONFIRMATION_FIELD,
                StaleOwnerConfirmation,
                validate_binding as validate_owner_confirmation,
            )

            binding = validate_owner_confirmation(
                current,
                owner_confirmation['prompt_id'],
                owner_confirmation['evidence_id'],
                selected_segment_ids,
                require_played=True,
            )
            if not segment_only or selected_speaker_id != binding['speaker_id'] or owner_segment_ids:
                raise StaleOwnerConfirmation('Owner excerpt cannot authorize whole-voice assignment or learning')
            owner_updates[OWNER_CONFIRMATION_FIELD] = dict(binding, answered='yes' if is_user else 'no')
        before = copy.deepcopy(current['transcript_segments'])
        if source_segments is not None:
            before_ids = {s.get('id') for s in before}
            if not selected_segment_ids or any(sid not in before_ids for sid in selected_segment_ids):
                raise ValueError('Selected speaker is no longer in the merged conversation')
        segments, receipt, resolved, previous = manual_assignment(
            current,
            person_id=person_id,
            is_user=is_user,
            segment_ids=selected_segment_ids,
            speaker_id=selected_speaker_id,
            segment_index=selected_segment_index,
            use_for_speech_training=use_for_speech_training,
            rejection=rejection,
            time_range=time_range if source_segments is None else None,
            segment_only=segment_only or time_range is not None,
        )
        removed, relabeled = persist_assignment_effects(
            transaction,
            user_ref,
            uid,
            current_id,
            before,
            segments,
            receipt,
            resolved,
            previous,
            person_id=person_id,
            is_user=is_user,
            use_for_speech_training=use_for_speech_training,
            evidence_source=evidence_source,
            rejection=rejection,
            donor_ids=(current_id, *seen),
            bookkeeping=bookkeeping,
            owner_segment_ids=owner_segment_ids,
        )
        extract_learning_receipt_markers(receipt, current)
        written = {'transcript_segments': segments, 'manual_speaker_assignments': receipt, **owner_updates}
        current.update(owner_updates)
        payload = _prepare_conversation_for_write(
            written,
            uid,
            raw.get('data_protection_level', 'standard'),
            preserve_transcript_identity=bool(raw.get('has_transcript_corrections')),
        )
        clear_client_processing(payload)
        guard_match_score_size(payload, raw, getattr(ref, 'path', None))
        transaction.update(ref, payload)
        current.update(transcript_segments=segments, manual_speaker_assignments=receipt)
        if payload.get(match_scores.FIELD) is firestore.DELETE_FIELD:
            current.pop(match_scores.FIELD, None)
        for field in PROJECTION_FAMILY_FIELDS:
            current.pop(field, None)
        return current, resolved, removed, relabeled

    result = run_assignment_transaction(client, assign)
    invalidate_people_stats_cache(uid)
    current, resolved, _, before = result
    if any(s.get('speaker_grouping_shadow') for s in current.get('transcript_segments') or []):
        try:
            from utils.conversations.speaker_grouping_shadow import record_correction

            record_correction(current, resolved)
        except Exception as error:
            # A committed user correction cannot fail because optional telemetry
            # is unavailable (including its lazy import).
            from utils.observability.fallback import record_fallback

            record_fallback(
                component='other',
                from_mode='speaker_grouping',
                to_mode='incumbent',
                reason='other',
                outcome='recovered',
                log=logger,
            )
            logger.warning(
                'event=speaker_grouping_correction outcome=unavailable exception_type=%s', type(error).__name__
            )
    record_speaker_review(uid, current['id'], before, current['transcript_segments'])
    record_speaker_learning_job_events(current.pop('_speaker_learning_job_events', ()))
    try:
        _reveal_match_scores_for_read(current, uid)
    except Exception:
        _drop_match_scores(current, 'malformed_doc')
    return result


def update_conversation_segments(
    uid: str,
    conversation_id: str,
    segments: List[dict],
    finished_at: datetime = None,
    data_protection_level: str = None,
    *,
    started_at: datetime = None,
    audio_timeline: Optional[dict] = None,
    capture_evidence: Optional[dict] = None,
    firestore_client: Any = None,
    invalidate_client_processing: bool = True,
    return_segments: bool = False,
    preserve_unseen: bool = False,
    live_segments: Optional[List[dict]] = None,
    live_capture_reasons: Optional[Dict[str, str]] = None,
    live_capture_proofs: Optional[Dict[str, CaptureWindowProof]] = None,
    segment_update_fields: Optional[tuple[str, ...]] = None,
    owner_recognition_diagnostics: Optional[dict] = None,
):
    """Merge live speech transactionally against the current receipt and pinned timeline.

    Field-only writes preserve stored text/spans. Live writes return the durable
    merge and clear any hash-bound client projection that the new transcript
    invalidates. ``invalidate_client_processing=False`` avoids a redundant clear
    only when no projection is stored. The first audio-timeline marker and its
    origin pin atomically; later callers cannot move that origin.
    """
    if live_segments is not None and segment_update_fields is not None:
        raise ValueError('Live merge and field-only segment updates are mutually exclusive')
    if segment_update_fields is not None and not set(segment_update_fields) <= {
        'translations',
        'person_id',
        'is_user',
        'speaker_identity_status',
        'speaker_match_source',
    }:
        raise ValueError('Field-only writers cannot change segment identity or speech boundaries')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    doc_ref = client.collection('users').document(uid).collection(conversations_collection).document(conversation_id)

    @firestore.transactional
    def _write_segments(transaction):
        doc_snapshot = doc_ref.get(transaction=transaction)
        if not getattr(doc_snapshot, 'exists', False):
            return False
        current = doc_snapshot.to_dict() or {}
        if current.get('record_projection_revision') and segment_update_fields is None:
            # The durable record owns the finalized capture. A delayed socket
            # flush cannot append its provisional twin after projection.
            return False
        doc_level = current.get('data_protection_level') or data_protection_level or 'standard'
        receipt = decode_manual_speaker_assignments(
            uid, current.get('manual_speaker_assignments'), bool(current.get('manual_speaker_assignments_compressed'))
        )
        planned = None
        prior_commits: list[list[str]] = []
        if live_segments is not None:
            persisted = _decode_transcript_segments_strict(
                uid, current.get('transcript_segments', []), bool(current.get('transcript_segments_compressed'))
            )
            if 'live_transcript_replay_receipt' in current:
                prior_commits = replay_receipt_commits(
                    _reveal_json_value(current['live_transcript_replay_receipt'], uid, True),
                    doc_ref.path,
                )
            planned = merge_live_segments(
                persisted,
                live_segments,
                receipt,
                absorbed_ids=[absorbed_id for commit in prior_commits for absorbed_id in commit],
                capture_reasons=live_capture_reasons,
                capture_proofs=live_capture_proofs,
            )
        remap = planned.absorbed_into if planned is not None else {}
        if remap:
            receipt = remap_absorbed_receipt(receipt, remap)
        incoming = planned.segments if planned is not None else list(segments)
        if planned is not None:
            # Inference may update identity fields, never replay cached text/spans.
            identities = {s.get('id'): s for s in segments}
            incoming = [
                (
                    dict(
                        s,
                        **{
                            k: identities[s.get('id')][k]
                            for k in ('person_id', 'is_user', 'speaker_identity_status', 'speaker_match_source')
                            if k in identities[s.get('id')]
                        },
                    )
                    if s.get('id') in identities
                    else s
                )
                for s in incoming
            ]
        if segment_update_fields is not None:
            persisted = _decode_transcript_segments_strict(
                uid, current.get('transcript_segments', []), bool(current.get('transcript_segments_compressed'))
            )
            updates = {s.get('id'): s for s in incoming}
            incoming = [
                dict(
                    s,
                    **{
                        k: updates.get(s.get('id'), {})[k]
                        for k in segment_update_fields
                        if k in updates.get(s.get('id'), {})
                    },
                )
                for s in persisted
            ]
        elif preserve_unseen and planned is None:
            known = {s.get('id') for s in incoming}
            persisted = _decode_transcript_segments_strict(
                uid, current.get('transcript_segments', []), bool(current.get('transcript_segments_compressed'))
            )
            incoming.extend(s for s in persisted if s.get('id') not in known)
            incoming.sort(key=lambda s: (s.get('start', 0), s.get('end', 0)))
        accepted = apply_manual_assignments(incoming, receipt)
        if current.get('has_transcript_corrections'):
            from utils.agent_capabilities.transcripts import load_entries, originals, preserves_correction_anchors

            accepted = originals(accepted)
            captured = decode_transcript_segments_verified(
                uid, current.get('transcript_segments') or [], bool(current.get('transcript_segments_compressed'))
            )
            corrections = load_entries(uid, conversation_id, firestore_client=client, transaction=transaction)
            if not preserves_correction_anchors(captured, accepted, corrections):
                return False
        score_updates = []
        try:
            score_updates = match_scores.merge(
                match_scores.from_segments(segments), match_scores.from_segments(accepted)
            )
        except Exception:
            _drop_match_scores({})
        # Numeric snapshots never count as transcript content or reach live deltas.
        accepted = [{k: v for k, v in segment.items() if k != match_scores.FIELD} for segment in accepted]
        update_payload = {
            'transcript_segments': accepted,
            # Once a live generation has received content, empty cleanup must
            # never reclaim it even if an older in-memory snapshot is empty.
            'has_content': bool(current.get('has_content')) or bool(accepted),
        }
        if live_segments is not None and current.get('sync_live_target') and accepted != persisted:
            # Sync and live now share this transcript. A processor that read
            # before fresh live speech must lose the same revision fence as
            # one that read before a sync append. Retries with no change do
            # not invalidate a current processor. Adoption is fleet-wide, so
            # this fence must not depend on the lineage rollout allowlist.
            update_payload['sync_content_revision'] = (current.get('sync_content_revision') or 0) + 1
        if score_updates and match_scores.enabled():
            try:
                score_current = dict(current)
                _reveal_match_scores_for_read(score_current, uid)
                update_payload[match_scores.FIELD] = match_scores.merge(
                    score_current.get(match_scores.FIELD), score_updates
                )
            except Exception:
                _drop_match_scores(update_payload)
        if owner_recognition_diagnostics is not None:
            update_payload[owner_diagnostics.FIELD] = owner_recognition_diagnostics
        if capture_evidence is not None:
            update_payload['capture_evidence'] = capture_evidence
        if remap:
            update_payload['manual_speaker_assignments'] = receipt
            update_payload['live_transcript_replay_receipt'] = _protect_json_value(
                {'commits': [*prior_commits, list(remap)][-LIVE_TRANSCRIPT_REPLAY_RECEIPT_COMMIT_LIMIT:]},
                uid,
                'enhanced',
            )
        if finished_at:
            update_payload['finished_at'] = finished_at
            update_payload.update(
                lifecycle_clocks.segment_activity_updates(uid, current, finished_at, live_segments, started_at)
            )
        pinned_timeline = isinstance(current.get('audio_timeline'), dict) and current.get('audio_timeline')
        if audio_timeline is not None and not pinned_timeline:
            # Fenced compare-and-set: the marker and the projected first-audio
            # origin land in the same transaction, exactly once per row.
            update_payload['audio_timeline'] = audio_timeline
            if started_at:
                update_payload['started_at'] = started_at
        elif started_at and not pinned_timeline:
            update_payload['started_at'] = started_at
        # With the marker already present, a stale started_at is ignored: the
        # origin was pinned with the marker and must not move.
        prepared_payload = _prepare_conversation_for_write(
            update_payload, uid, doc_level, preserve_transcript_identity=bool(current.get('has_transcript_corrections'))
        )
        if invalidate_client_processing:
            clear_client_processing(prepared_payload)
        elif any(current.get(field) is not None for field in PROJECTION_FAMILY_FIELDS):
            # Opt-out skips the sentinel so the ~0.6s live loop stays cheap when
            # no projection exists. A projection that is really there (overlap
            # with finalize) must still be cleared in this same write.
            clear_client_processing(prepared_payload)
        guard_match_score_size(prepared_payload, current, getattr(doc_ref, 'path', None))
        _merge_owner_diagnostics(prepared_payload, current, getattr(doc_ref, 'path', None))
        transaction.update(doc_ref, prepared_payload)
        if planned is not None:
            return planned.with_segments(accepted)
        return accepted if return_segments else True

    result = run_transactional(client, _write_segments)
    if result is not False:
        invalidate_people_stats_cache(uid)
    return result


def translation_materialization_is_current(
    uid: str,
    conversation: Dict[str, Any],
    segment: Dict[str, Any],
    target: str,
    policy_version: str,
    source_hint: str = '',
) -> bool:
    """Treat missing or mismatched private provenance as a cache miss."""
    raw = conversation.get('translation_materializations')
    try:
        metadata = _reveal_json_value(raw, uid, True) if raw is not None else {}
    except (ValueError, TypeError, json.JSONDecodeError, zlib.error):
        return False
    if not isinstance(metadata, dict):
        return False
    segment_records = metadata.get(segment.get('id'))
    record = segment_records.get(target) if isinstance(segment_records, dict) else None
    stored_translations = segment.get('translations')
    candidates = stored_translations if isinstance(stored_translations, list) else []
    translation = next((item for item in candidates if isinstance(item, dict) and item.get('lang') == target), None)
    source_text = segment.get('text')
    translated_text = translation.get('text') if isinstance(translation, dict) else None
    return bool(
        isinstance(record, dict)
        and isinstance(source_text, str)
        and isinstance(translated_text, str)
        and record.get('source') == hashlib.sha256(source_text.encode('utf-8')).hexdigest()
        and record.get('translation') == hashlib.sha256(translated_text.encode('utf-8')).hexdigest()
        and record.get('policy') == policy_version
        and record.get('source_hint') == (source_hint.strip().lower() or 'detect-v1')
    )


def materialize_translation(
    uid: str,
    conversation_id: str,
    segment_id: str,
    source_text: str,
    target: str,
    translated_text: str,
    *,
    source_hint: str = '',
    policy_version: str = 'legacy',
    admission_kind: str = 'live',
    reservation: TranslationReservation | None = None,
    firestore_client: Any = None,
) -> Optional[Dict[str, Any]]:
    """Fence a display translation against the current source and merge one target."""
    if not segment_id or not source_text or not target or not translated_text:
        return None
    config = resolve_ondemand_config()
    if policy_version != 'legacy' and not (config.gate_enabled if admission_kind == 'live' else config.onopen_enabled):
        return None
    client = firestore_client if firestore_client is not None else get_firestore_client()
    doc_ref = client.collection('users').document(uid).collection(conversations_collection).document(conversation_id)
    source_digest = hashlib.sha256(source_text.encode('utf-8')).hexdigest()
    value_digest = hashlib.sha256(translated_text.encode('utf-8')).hexdigest()

    @firestore.transactional
    def _write(transaction):
        # Kill-switch recheck at COMMIT time (Luna R3-4): a transaction retry
        # must not land a viewed result after the gate flipped off mid-flight.
        commit_config = resolve_ondemand_config()
        if policy_version != 'legacy' and not (
            commit_config.gate_enabled if admission_kind == 'live' else commit_config.onopen_enabled
        ):
            return None
        snapshot = doc_ref.get(transaction=transaction)
        if not getattr(snapshot, 'exists', False):
            return None
        current = snapshot.to_dict() or {}
        if is_soft_deleted(current) or current.get('is_locked'):
            return None
        segments = _decode_transcript_segments_strict(
            uid, current.get('transcript_segments', []), bool(current.get('transcript_segments_compressed'))
        )
        selected = next(
            (
                segment
                for index, segment in enumerate(segments)
                if (segment.get('id') or legacy_conversation_segment_id(conversation_id, index)) == segment_id
            ),
            None,
        )
        projected = segments
        if current.get('has_transcript_corrections'):
            from utils.agent_capabilities.transcripts import apply_entries, load_entries

            projected = apply_entries(
                segments, load_entries(uid, conversation_id, firestore_client=client, transaction=transaction)
            )
        visible = projected[segments.index(selected)] if selected is not None else None
        if visible is None or visible.get('text') != source_text:
            return None
        raw_metadata = current.get('translation_materializations')
        try:
            metadata = _reveal_json_value(raw_metadata, uid, True) if raw_metadata is not None else {}
        except (ValueError, TypeError, json.JSONDecodeError, zlib.error):
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        by_target = metadata.get(segment_id)
        if not isinstance(by_target, dict):
            by_target = {}
        prior = by_target.get(target)
        existing = next(
            (value for value in selected.get('translations', []) or [] if value.get('lang') == target), None
        )
        if (
            policy_version == 'legacy'
            and isinstance(prior, dict)
            and prior.get('policy') == 'viewed_v1'
            and prior.get('source') == source_digest
            and isinstance(existing, dict)
            and prior.get('translation') == hashlib.sha256(existing.get('text', '').encode('utf-8')).hexdigest()
        ):
            return selected
        selected['translations'] = [
            value for value in selected.get('translations', []) or [] if value.get('lang') != target
        ] + [{'lang': target, 'text': translated_text}]
        by_target[target] = {
            'source': source_digest,
            'translation': value_digest,
            'source_hint': source_hint.strip().lower() or 'detect-v1',
            'policy': policy_version,
            # Policy model identity; provider usage records the actual route, including BYOK.
            'model': LUNA_MODEL if policy_version == 'viewed_v1' else 'legacy-configured',
            'prompt': 'v1' if policy_version == 'viewed_v1' else 'legacy',
        }
        metadata[segment_id] = by_target
        level = current.get('data_protection_level', 'standard')
        payload = _prepare_conversation_for_write(
            {'transcript_segments': segments},
            uid,
            level,
            preserve_transcript_identity=bool(current.get('has_transcript_corrections')),
        )
        payload['translation_materializations'] = _protect_json_value(metadata, uid, 'enhanced')
        payload['translation_materializations_compressed'] = True
        if reservation is not None and not reservation_is_current(reservation):
            return None
        guard_match_score_size(payload, current, getattr(doc_ref, 'path', None))
        transaction.update(doc_ref, payload)
        return {
            **selected,
            'text': source_text,
            **({'original_text': selected['text']} if current.get('has_transcript_corrections') else {}),
        }

    return run_transactional(client, _write)


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


def _visibility_patch(uid: str, visibility: str) -> dict:
    return {
        'visibility': visibility,
        'owner_uid': uid if visibility in ('shared', 'public') else firestore.DELETE_FIELD,
    }


def set_conversation_visibility(uid: str, conversation_id: str, visibility: str):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.update(_visibility_patch(uid, visibility))


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
                _visibility_patch(uid, 'shared'),
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
            _visibility_patch(uid, visibility),
            option=db.write_option(last_update_time=last_update_time),
        )
        return True
    except gcloud_exceptions.FailedPrecondition:
        return False


def set_conversation_starred(uid: str, conversation_id: str, starred: bool):
    user_ref = db.collection('users').document(uid)
    conversation_ref = user_ref.collection(conversations_collection).document(conversation_id)
    conversation_ref.update({'starred': starred})


def unlock_all_conversations(uid: str, *, limit: Optional[int] = None) -> int:
    """Unlock all locked rows, or one bounded page when limit is supplied."""
    conversations_ref = db.collection('users').document(uid).collection(conversations_collection)
    locked_conversations_query = conversations_ref.where(filter=FieldFilter('is_locked', '==', True))

    from database.locked_content import unlock_query_rows
    from database.legal_holds import external_write_fence

    with external_write_fence(uid):
        total = unlock_query_rows(
            db,
            locked_conversations_query,
            {'is_locked': False},
            limit=limit,
            on_commit=lambda: invalidate_people_stats_cache(uid),
        )
        logger.info(f"Unlocked all conversations for user {uid}")
        return total


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
    count = 0
    for segment in segments:
        segment_id = str(uuid.uuid4())
        segment_ref = segments_ref.document(segment_id)
        batch.set(segment_ref, segment.model_dump())
        count += 1
        if count >= 400:
            batch.commit()
            batch = db.batch()
            count = 0
    if count > 0:
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
    if count > 0:
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
    results = {
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
    # These are separate diagnostic provider records, with no primary-capture
    # overlay anchors. Their identity projection still exposes captured text.
    return {
        provider: [{**segment, 'original_text': segment.get('text', '')} for segment in segments]
        for provider, segments in results.items()
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

    return run_transactional(client, _store)


# ********************************
# ********** SYNCING *************
# ********************************


@set_data_protection_level(data_arg_name='incoming')
def assign_sync_conversation(
    uid: str,
    incoming: dict,
    *,
    candidate_id=None,
    target_id=None,
    firestore_client=None,
    before_assign: Callable[[Any], None] | None = None,
    validate_plan: Callable[[Any, dict], None] | None = None,
    after_assign: Callable[[Any, tuple], None] | None = None,
    retry_contention: bool = False,
    timing: bool = False,
    defer_index: Callable[[str, str, list[str]], None] | None = None,
):
    """Atomically choose, create or append a sync conversation; ``timing`` logs bounded sub-phases.

    ``defer_index`` takes the post-commit search/people-stats step off this
    call: it receives the canonical and its donor lineage, and the caller
    converges each conversation once later (``index_sync_assignment``).
    """
    from utils.sync.assignment import assign_in_transaction
    from config.sync_lineage import sync_lineage_resolve_enabled
    from utils.sync.intake_completion import log_assignment_observations

    # The coordinator/projection already validated S1 and cohort admission.
    # Rechecking membership here can refresh its Firestore cache on the hot path.
    lineage_eligible = incoming.get('_sync_lineage_eligible') is True and sync_lineage_resolve_enabled()

    clock = SyncAssignmentClock(logger, enabled=timing)
    client = firestore_client if firestore_client is not None else get_firestore_client()
    user_ref = client.collection('users').document(uid)

    discovery = SyncAssignmentDiscovery(lineage_eligible)
    absorbed: list[str] = []

    score_snapshots: dict = {}

    def decode(raw):
        if raw.get('id'):
            score_snapshots[raw['id']] = raw
        # Never turn a corrupt/encrypted transcript into [] and overwrite it.
        result = copy.deepcopy(raw)
        result['transcript_segments'] = _decode_transcript_segments_strict(
            uid, raw.get('transcript_segments', []), bool(raw.get('transcript_segments_compressed'))
        )
        if raw.get('manual_speaker_assignments') is not None:
            result['manual_speaker_assignments'] = decode_manual_speaker_assignments(
                uid, raw.get('manual_speaker_assignments'), bool(raw.get('manual_speaker_assignments_compressed'))
            )
        else:
            result.pop('manual_speaker_assignments', None)
        # Never decode here (every same-chain replay would pay it) and never
        # hand the blob to the logical encoder; the encode seam preserves it.
        result.pop(OPEN_LOOP_EXTRACTIONS_FIELD, None)
        result.pop(OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD, None)
        from utils.sync.size_telemetry import remember_size_payload

        remember_size_payload(result.get('id'), result)
        _reveal_match_scores_for_read(result, uid)
        return result

    attempted: dict[str, str] = {}

    @firestore.transactional
    def assign(transaction, full_ids=frozenset()):
        clock.attempt()
        score_snapshots.clear()
        # Projection guards only read; after_assign only writes in this transaction.
        if before_assign is not None:
            with clock.timed('fence'):
                before_assign(transaction)

        def encode(payload):
            with clock.timed('encode'):
                if validate_plan is not None:
                    validate_plan(transaction, payload)
                return encode_sync_assignment_plan(
                    uid, client, transaction, payload, score_snapshots.get(payload.get('id'))
                )

        with clock.timed('plan'):
            planned = assign_in_transaction(
                transaction,
                user_ref,
                incoming,
                candidate_id=candidate_id,
                target_id=target_id,
                decode=decode,
                encode=encode,
                invalidate=clear_client_processing,
                full_ids=full_ids,
                live_candidate_ids=discovery.candidate_ids,
                absorbed=absorbed,
                **discovery.plan_kwargs(),
            )
        # Remember the candidate before the transaction commits.
        attempted['canonical'] = planned[0]['id']
        if after_assign is not None:
            with clock.timed('persist'):
                after_assign(transaction, planned)
        clock.body_done()
        return planned

    def discover_live_candidates():
        with clock.timed('live_overlap'):
            discovery.discover(user_ref, incoming, find_sync_live_overlap_candidates)

    with clock.call():
        if not target_id and (
            (incoming.get('client_device_id') and live_overlap_enabled()) or shadow_or_serve('CAPTURE_COVERAGE_MODE')
        ):
            discover_live_candidates()
        with clock.timed('transaction'):
            result = discovery.run(
                lambda full_ids: run_sync_assignment(client, assign, full_ids, retry_contention=retry_contention),
                lambda: attempted.get('canonical'),
                discover_live_candidates,
            )
        conversation = result[0]
        log_assignment_observations(conversation, lineage_eligible=lineage_eligible)
        output_ids = [conversation['id'], *(row['id'] for row, _ in conversation.get('_sync_size_rollover_rows', []))]
        for retired_id in sorted({*output_ids, *absorbed}):
            stop_quiet_check_for_conversation(uid, retired_id, firestore_client=client)
        if defer_index is not None:
            # Coalesce the lineage's retryable donor deletes once per flush.
            clock.donors = len(absorbed)
            for output_id in output_ids:
                defer_index(uid, output_id, sorted({*(conversation.get('sync_merged_from') or []), *absorbed}))
        else:
            with clock.timed('index'):
                clock.donors = len(conversation.get('sync_merged_from') or [])
                index_sync_assignment(uid, output_ids, conversation.get('sync_merged_from') or [])
    return result


def index_sync_assignment(uid: str, conversation_ids, donor_ids) -> None:
    """Fail-open search and people-stats convergence after sync assignment commits.

    Donors are redirect tombstones and are deleted directly. Every other id is
    converged from its current durable state, so a late or coalesced call
    cannot index stale content or resurrect a donor.
    """
    invalidate_people_stats_cache(uid)
    donors = list(dict.fromkeys(str(donor_id) for donor_id in donor_ids))
    for donor_id in donors:
        _delete_conversation_search_index(uid, donor_id)
    for conversation_id in dict.fromkeys(conversation_ids):
        if conversation_id not in donors:
            _sync_conversation_search_index(uid, conversation_id)


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


@prepare_for_read(decrypt_func=prepare_conversation_for_read)
@with_photos(get_conversation_photos)
def get_closest_conversation_to_timestamps(
    uid: str,
    start_timestamp: int,
    end_timestamp: int,
    *,
    window_seconds: int = 120,
    eligible: Optional[Callable[[dict], bool]] = None,
) -> Optional[dict]:
    # ``window_seconds``/``eligible`` change bounds and post-filter only; the
    # query shape and its index are identical. Normal sync keeps the ±2 min hint.
    start_threshold = datetime.fromtimestamp(start_timestamp, tz=timezone.utc) - timedelta(seconds=window_seconds)
    end_threshold = datetime.fromtimestamp(end_timestamp, tz=timezone.utc) + timedelta(seconds=window_seconds)

    conversations_ref = db.collection('users').document(uid).collection(conversations_collection)
    query = (
        conversations_ref.where(filter=FieldFilter('finished_at', '>=', start_threshold))
        .where(filter=FieldFilter('started_at', '<=', end_threshold))
        .order_by('created_at', direction=firestore.Query.DESCENDING)
    )

    conversations = [doc.to_dict() for doc in query.stream()]
    logger.debug(f'get_closest_conversation_to_timestamps len(conversations) {len(conversations)}')
    if not conversations:
        return None

    for conversation in conversations:
        logger.debug("- %s %s %s", conversation['id'], conversation['started_at'], conversation['finished_at'])

    if eligible is not None:
        conversations = [conversation for conversation in conversations if eligible(conversation)]
    closest_conversation = select_closest_conversation(conversations, start_timestamp, end_timestamp)
    if closest_conversation is None:
        logger.info('get_closest_conversation_to_timestamps: no eligible merge target (deleted rows excluded)')
        return None

    logger.info(f"get_closest_conversation_to_timestamps closest_conversation: {closest_conversation['id']}")
    return closest_conversation


@prepare_for_read(decrypt_func=prepare_conversation_for_read)
@with_photos(get_conversation_photos)
def get_last_completed_conversation(uid: str) -> Optional[dict]:
    conversations_ref = db.collection('users').document(uid).collection(conversations_collection)
    query = (
        conversations_ref.where(filter=FieldFilter('status', '==', ConversationStatus.completed))
        .order_by('created_at', direction=firestore.Query.DESCENDING)
        .limit(8)
    )
    conversations: List[Dict[str, Any]] = []
    for doc in query.stream():
        data = doc.to_dict()
        if data and not is_soft_deleted(data):
            conversations.append(data)
    conversation = conversations[0] if conversations else None
    return conversation


def promote_final_pass_if_current(
    uid, conversation_id, segments, *, expected_updated_at, clock_offset, firestore_client=None
):
    """Revision-fenced speaker-only promotion preserving the stored transcript."""
    if expected_updated_at is None or not authoritative_for(uid):
        return False
    from utils.conversations.final_pass_remap import remap_final_record

    client = firestore_client if firestore_client is not None else get_firestore_client()
    parent = client.collection('users').document(uid).collection(conversations_collection).document(conversation_id)
    deletion = client.collection('account_deletions').document(uid)

    @firestore.transactional
    def commit(transaction):
        if not authoritative_for(uid):
            return False
        snapshot = parent.get(transaction=transaction)
        deleting = deletion.get(transaction=transaction)
        current = snapshot.to_dict() or {}
        if (
            not snapshot.exists
            or deleting.exists
            or is_soft_deleted(current)
            or current.get('is_locked')
            or current.get('record_lane_owner') in {'batch_live_v1', 'batch_sync_v1'}
            or current.get('discarded')
            or current.get('status') != 'completed'
            or firestore_revision_datetime(snapshot.update_time) != expected_updated_at
        ):
            return False
        old = decode_transcript_segments_verified(
            uid, current.get('transcript_segments', []), bool(current.get('transcript_segments_compressed'))
        )
        receipt = decode_manual_speaker_assignments(
            uid, current.get('manual_speaker_assignments'), bool(current.get('manual_speaker_assignments_compressed'))
        )
        readable = prepare_conversation_for_read(copy.deepcopy(current), uid)
        if readable is None:
            return False
        patch = remap_final_record(
            old, [s.model_dump() for s in segments], receipt, readable.get('structured', {}), clock_offset=clock_offset
        )
        # Derived references/materializations outside structured have their own
        # contracts. Refuse promotion until those consumers support remapping.
        if current.get('translation_materializations') or current.get('apps_results') or current.get('note_claims'):
            return False
        # The owning write boundary reapplies the current, remapped receipt.
        patch['transcript_segments'] = apply_manual_assignments(
            patch['transcript_segments'], patch['manual_speaker_assignments']
        )
        patch['speaker_resolution'] = {
            'status': 'resolved',
            'participant_speaker_ids': sorted(
                {
                    s['speaker_id']
                    for s in patch['transcript_segments']
                    if s.get('speaker_id') is not None and s['speaker_id'] >= 0
                }
            ),
        }
        prepared = _prepare_conversation_for_write(
            patch,
            uid,
            current.get('data_protection_level') or 'standard',
            preserve_transcript_identity=bool(current.get('has_transcript_corrections')),
        )
        guard_match_score_size(prepared, current, getattr(parent, 'path', None))
        transaction.update(parent, prepared)
        return True

    written = run_transactional(client, commit)
    if written:
        invalidate_people_stats_cache(uid)
    return bool(written)
