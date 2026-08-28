"""Bounded Firestore readers used only by the entity timeline tool."""

import json
import zlib
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Dict, List, Optional, cast

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from models.conversation_enums import ConversationStatus
from utils import encryption

from .conversations import conversations_collection
from .conversations import (
    _document_data_with_revision as document_data_with_revision,  # pyright: ignore[reportPrivateUsage]
)
from .firestore_index_registry import (
    ENTITY_TIMELINE_CONVERSATIONS_QUERY,
    ENTITY_TIMELINE_MEETINGS_QUERY,
    ENTITY_TIMELINE_SCREEN_ACTIVITY_QUERY,
)
from .screen_activity import SCREEN_ACTIVITY_COLLECTION, USERS_COLLECTION, normalize_screen_activity_timestamp

_MAX_TRANSCRIPT_STORED_BYTES = 256 * 1024
_MAX_TRANSCRIPT_DECODED_BYTES = 512 * 1024
_MAX_TRANSCRIPT_SEGMENTS = 4096


def _bounded_identity_segments(uid: str, data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Decode only bounded speaker identity fields, never transcript text."""

    raw = data.get('transcript_segments')
    if isinstance(raw, list):
        if len(raw) > _MAX_TRANSCRIPT_SEGMENTS:
            return []
        parsed: object = raw
    elif data.get('transcript_segments_compressed') is True:
        try:
            if isinstance(raw, str):
                max_encrypted_chars = (((_MAX_TRANSCRIPT_STORED_BYTES * 2) + 28 + 2) // 3) * 4
                if not raw.isascii() or len(raw) > max_encrypted_chars:
                    return []
                decrypted_hex = encryption.decrypt(raw, uid)
                if len(decrypted_hex) > _MAX_TRANSCRIPT_STORED_BYTES * 2 or len(decrypted_hex) % 2:
                    return []
                compressed = bytes.fromhex(decrypted_hex)
            elif isinstance(raw, (bytes, bytearray, memoryview)):
                compressed = bytes(raw)
            else:
                return []
            if len(compressed) > _MAX_TRANSCRIPT_STORED_BYTES:
                return []
            decompressor = zlib.decompressobj()
            decoded = decompressor.decompress(compressed, _MAX_TRANSCRIPT_DECODED_BYTES + 1)
            if (
                len(decoded) > _MAX_TRANSCRIPT_DECODED_BYTES
                or decompressor.unconsumed_tail
                or not decompressor.eof
                or decompressor.unused_data
            ):
                return []
            parsed = json.loads(decoded.decode('utf-8'))
        except (json.JSONDecodeError, RecursionError, TypeError, UnicodeDecodeError, ValueError, zlib.error):
            return []
        if not isinstance(parsed, list) or len(parsed) > _MAX_TRANSCRIPT_SEGMENTS:
            return []
    else:
        # Legacy encrypted, uncompressed transcript strings have no bounded
        # decode contract. Fail the identity join closed rather than inflate.
        return []

    identities: List[Dict[str, Any]] = []
    for segment in parsed:
        if not isinstance(segment, Mapping):
            continue
        identity: Dict[str, Any] = {}
        if isinstance(segment.get('is_user'), bool):
            identity['is_user'] = segment['is_user']
        if isinstance(segment.get('person_id'), str):
            identity['person_id'] = segment['person_id'][:160]
        identities.append(identity)
    return identities


def list_entity_timeline_conversations(
    uid: str,
    *,
    db_client: Any,
    limit: int,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Read one deterministic, completed-conversation window for a timeline.

    Speaker IDs are required to join a stable person. This boundary decodes at
    most a fixed compressed/expanded byte budget and retains identity fields
    only; transcript text and photos never leave the database boundary.
    """

    if limit < 1 or limit > 501:
        raise ValueError('entity timeline conversation limit must be between 1 and 501')
    collection = db_client.collection('users').document(uid).collection(conversations_collection)
    query = ENTITY_TIMELINE_CONVERSATIONS_QUERY.build(
        collection,
        {
            'discarded': False,
            'status': ConversationStatus.completed.value,
        },
        field_filter_factory=FieldFilter,
    )
    if start_date is not None:
        query = query.where(filter=FieldFilter('created_at', '>=', start_date))
    if end_date is not None:
        query = query.where(filter=FieldFilter('created_at', '<=', end_date))
    query = (
        query.order_by('created_at', direction=firestore.Query.DESCENDING)
        .order_by('__name__', direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    conversations: List[Dict[str, Any]] = []
    for snapshot in query.stream():
        data = document_data_with_revision(snapshot)
        if data is None:
            continue
        data['id'] = snapshot.id
        data['transcript_segments'] = _bounded_identity_segments(uid, data)
        conversations.append(data)
    return conversations


def list_entity_timeline_meetings(
    uid: str,
    *,
    db_client: Any,
    limit: int,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Read a stable, bounded calendar window through an injected authority."""

    if limit < 1 or limit > 501:
        raise ValueError('entity timeline meeting limit must be between 1 and 501')
    collection = db_client.collection('users').document(uid).collection('meetings')
    query = ENTITY_TIMELINE_MEETINGS_QUERY.build(collection, {}, field_filter_factory=FieldFilter)
    if start_date is not None:
        query = query.where('start_time', '>=', start_date)
    if end_date is not None:
        query = query.where('start_time', '<=', end_date)
    query = (
        query.order_by('start_time', direction=firestore.Query.DESCENDING)
        .order_by('__name__', direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    meetings: List[Dict[str, Any]] = []
    for snapshot in query.stream():
        raw: object = snapshot.to_dict()
        if not isinstance(raw, dict):
            continue
        data = dict(cast(Dict[str, Any], raw))
        data['id'] = snapshot.id
        meetings.append(data)
    return meetings


def list_entity_timeline_screen_activity(
    uid: str,
    *,
    db_client: Any,
    limit: int,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Read a deterministic screen-metadata window for exact alias matching."""

    if limit < 1 or limit > 501:
        raise ValueError('entity timeline screen limit must be between 1 and 501')
    collection = db_client.collection(USERS_COLLECTION).document(uid).collection(SCREEN_ACTIVITY_COLLECTION)
    query = ENTITY_TIMELINE_SCREEN_ACTIVITY_QUERY.build(collection, {}, field_filter_factory=FieldFilter)
    if start_date is not None:
        query = query.where(
            filter=firestore.FieldFilter('timestamp', '>=', normalize_screen_activity_timestamp(start_date))
        )
    if end_date is not None:
        query = query.where(
            filter=firestore.FieldFilter(
                'timestamp', '<=', normalize_screen_activity_timestamp(end_date, end_of_second=True)
            )
        )
    query = (
        query.order_by('timestamp', direction=firestore.Query.DESCENDING)
        .order_by('__name__', direction=firestore.Query.DESCENDING)
        .limit(limit)
    )
    rows: List[Dict[str, Any]] = []
    for snapshot in query.stream():
        raw: object = snapshot.to_dict()
        if not isinstance(raw, dict):
            continue
        data = dict(cast(Dict[str, Any], raw))
        data['id'] = snapshot.id
        rows.append(data)
    return rows
