"""Durable listen recording-session bindings and ordered lifecycle envelopes.

The user-scoped resource is the authority for mapping one recording session to
one conversation.  It intentionally stores only routing metadata: never
transcript text, credentials, or WebSocket payloads.  Conversation lifecycle
mutation remains owned by ``utils.conversations.lifecycle``; this adapter only
persists the recording identity and its outbound event sequence.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Mapping, TypedDict

from google.cloud import firestore

from database import conversations as conversations_db
from database._client import get_firestore_client

RECORDING_SESSIONS_COLLECTION = 'recording_sessions'
CONVERSATIONS_COLLECTION = 'conversations'
RECORDING_SESSION_SCHEMA_VERSION = 1
LIFECYCLE_ENVELOPE_VERSION = 1
RECORDING_SESSION_LEASE_DURATION = timedelta(minutes=5)
MAX_TRANSACTION_RETRIES = 5
RecordingPhase = Literal['in_progress', 'processing', 'completed', 'failed', 'discarded']

_PHASE_ORDER: dict[str, int] = {
    'in_progress': 0,
    'processing': 1,
    'completed': 2,
    'failed': 2,
    'discarded': 2,
}
_TERMINAL_PHASES = frozenset({'completed', 'failed', 'discarded'})
_IDENTIFIER_PATTERN = re.compile(r'^[a-zA-Z0-9_\-]+$')


def _validate_id(value: Any, name: str = 'id') -> str:
    """Validate and sanitize an identifier, rejecting empty/whitespace, path traversal, null bytes, and length overruns."""
    if not isinstance(value, str):
        raise ValueError(f'{name} must be a non-empty string')
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f'{name} must be a non-empty string')
    if '\x00' in cleaned or any(traversal in cleaned for traversal in ('..', '/', '\\')):
        raise ValueError(f'{name} contains invalid characters')
    if len(cleaned) > 128:
        raise ValueError(f'{name} exceeds maximum length')
    if not _IDENTIFIER_PATTERN.match(cleaned):
        raise ValueError(f'{name} contains invalid characters')
    return cleaned


def _clamp_lifecycle_sequence(seq: Any) -> int:
    """Defensively clamp sequence counter to a non-negative integer."""
    try:
        val = int(seq)
        return max(0, val)
    except (TypeError, ValueError):
        return 0


def _clamp_lifecycle_version(version: Any) -> int:
    """Defensively clamp lifecycle version to at least 1."""
    try:
        val = int(version)
        return max(1, val)
    except (TypeError, ValueError):
        return LIFECYCLE_ENVELOPE_VERSION


class RecordingSessionBinding(TypedDict):
    recording_session_id: str
    conversation_id: str
    lifecycle_version: int
    lifecycle_phase: str
    lifecycle_sequence: int
    mapping_conflict: bool


class RecordingSessionEvent(TypedDict):
    recording_session_id: str
    conversation_id: str
    lifecycle_version: int
    lifecycle_phase: str
    lifecycle_sequence: int
    accepted: bool
    discard_reason: str | None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _client(firestore_client: Any = None) -> Any:
    return firestore_client if firestore_client is not None else get_firestore_client()


def _session_ref(client: Any, uid: str, recording_session_id: str) -> Any:
    clean_uid = _validate_id(uid, name='uid')
    clean_session_id = _validate_id(recording_session_id, name='recording_session_id')
    return (
        client.collection('users')
        .document(clean_uid)
        .collection(RECORDING_SESSIONS_COLLECTION)
        .document(clean_session_id)
    )


def _binding(data: dict[str, Any], recording_session_id: str, *, mapping_conflict: bool) -> RecordingSessionBinding:
    clean_session_id = _validate_id(recording_session_id, name='recording_session_id')
    clean_conversation_id = _validate_id(str(data['conversation_id']), name='conversation_id')
    return {
        'recording_session_id': clean_session_id,
        'conversation_id': clean_conversation_id,
        'lifecycle_version': _clamp_lifecycle_version(data.get('lifecycle_version')),
        'lifecycle_phase': str(data.get('lifecycle_phase') or 'in_progress'),
        'lifecycle_sequence': _clamp_lifecycle_sequence(data.get('lifecycle_sequence')),
        'mapping_conflict': mapping_conflict,
    }


def _create_or_get_recording_session_txn(
    transaction: Any,
    session_ref: Any,
    conversations_collection: Any,
    uid: str,
    recording_session_id: str,
    proposed_conversation_id: str,
    now: datetime,
    include_conversation_snapshot: bool,
) -> dict[str, Any]:
    snapshot = session_ref.get(transaction=transaction)
    session_exists = bool(getattr(snapshot, 'exists', False))
    if session_exists:
        current = snapshot.to_dict() or {}
        if current.get('uid') != uid or current.get('recording_session_id') != recording_session_id:
            raise ValueError('recording session identity does not match its document binding')
        binding = _binding(
            current,
            recording_session_id,
            mapping_conflict=current.get('conversation_id') != proposed_conversation_id,
        )
    else:
        current = {
            'schema_version': RECORDING_SESSION_SCHEMA_VERSION,
            'uid': uid,
            'recording_session_id': recording_session_id,
            'conversation_id': proposed_conversation_id,
            'lifecycle_version': LIFECYCLE_ENVELOPE_VERSION,
            'lifecycle_phase': 'in_progress',
            'lifecycle_sequence': 0,
            'created_at': now,
            'updated_at': now,
            'lease_expires_at': now + RECORDING_SESSION_LEASE_DURATION,
        }
        binding = _binding(current, recording_session_id, mapping_conflict=False)

    conversation_ref = conversations_collection.document(binding['conversation_id'])
    conversation_snapshot = conversation_ref.get(transaction=transaction)
    conversation = conversation_snapshot.to_dict() or {} if getattr(conversation_snapshot, 'exists', False) else None

    if session_exists:
        if (
            current.get('conversation_id') == proposed_conversation_id
            and str(current.get('lifecycle_phase') or 'in_progress') == 'in_progress'
        ):
            transaction.update(
                session_ref,
                {'lease_expires_at': now + RECORDING_SESSION_LEASE_DURATION, 'updated_at': now},
            )
    else:
        transaction.create(session_ref, current)

    if conversation is not None:
        external_data = conversation.get('external_data')
        marker = dict(external_data) if isinstance(external_data, Mapping) else {}
        if marker.get('recording_session_id') != recording_session_id:
            marker['recording_session_id'] = recording_session_id
            transaction.update(conversation_ref, {'external_data': marker})
            conversation['external_data'] = marker
    result: dict[str, Any] = dict(binding)
    if include_conversation_snapshot:
        result['conversation_snapshot'] = conversation
        result['conversation_snapshot_known'] = True
    return result


def create_or_get_recording_session(
    uid: str,
    recording_session_id: str,
    proposed_conversation_id: str,
    *,
    firestore_client: Any = None,
    include_conversation_snapshot: bool = False,
) -> dict[str, Any]:
    """Atomically bind a session to exactly one canonical conversation ID."""
    clean_uid = _validate_id(uid, name='uid')
    clean_session_id = _validate_id(recording_session_id, name='recording_session_id')
    clean_proposed_id = _validate_id(proposed_conversation_id, name='proposed_conversation_id')
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_create_or_get_recording_session_txn)
    return transactional(
        transaction,
        _session_ref(client, clean_uid, clean_session_id),
        client.collection('users').document(clean_uid).collection(CONVERSATIONS_COLLECTION),
        clean_uid,
        clean_session_id,
        clean_proposed_id,
        _now(),
        include_conversation_snapshot,
    )


def _renew_recording_session_lease_txn(
    transaction: Any,
    session_ref: Any,
    uid: str,
    recording_session_id: str,
    conversation_id: str,
    now: datetime,
) -> bool:
    snapshot = session_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    current = snapshot.to_dict() or {}
    if (
        current.get('uid') != uid
        or current.get('recording_session_id') != recording_session_id
        or current.get('conversation_id') != conversation_id
        or str(current.get('lifecycle_phase') or 'in_progress') != 'in_progress'
    ):
        return False
    transaction.update(
        session_ref,
        {'lease_expires_at': now + RECORDING_SESSION_LEASE_DURATION, 'updated_at': now},
    )
    return True


def renew_recording_session_lease(
    uid: str,
    recording_session_id: str,
    conversation_id: str,
    *,
    firestore_client: Any = None,
) -> bool:
    """Renew a live session's lease against its identity and phase fence."""
    try:
        clean_uid = _validate_id(uid, name='uid')
        clean_session_id = _validate_id(recording_session_id, name='recording_session_id')
        clean_conversation_id = _validate_id(conversation_id, name='conversation_id')
    except (ValueError, TypeError):
        return False
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_renew_recording_session_lease_txn)
    return transactional(
        transaction,
        _session_ref(client, clean_uid, clean_session_id),
        clean_uid,
        clean_session_id,
        clean_conversation_id,
        _now(),
    )


def get_recording_session(
    uid: str,
    recording_session_id: str,
    *,
    firestore_client: Any = None,
) -> RecordingSessionBinding | None:
    """Read the canonical binding without proposing or mutating an identity."""
    clean_uid = _validate_id(uid, name='uid')
    clean_session_id = _validate_id(recording_session_id, name='recording_session_id')
    snapshot = _session_ref(_client(firestore_client), clean_uid, clean_session_id).get()
    if not getattr(snapshot, 'exists', False):
        return None
    data = snapshot.to_dict() or {}
    if data.get('uid') != clean_uid or data.get('recording_session_id') != clean_session_id:
        raise ValueError('recording session identity does not match its document binding')
    return _binding(data, clean_session_id, mapping_conflict=False)


def tombstone_and_delete_empty_conversation(
    uid: str,
    conversation_id: str,
    recording_session_id: str | None,
    *,
    firestore_client: Any = None,
    deleted_conversation: dict[str, Any] | None = None,
) -> bool:
    """Atomically delete an empty live row and terminalize its bound session."""
    clean_uid = _validate_id(uid, name='uid')
    clean_conversation_id = _validate_id(conversation_id, name='conversation_id')
    clean_session_id = _validate_id(recording_session_id, name='recording_session_id') if recording_session_id else None

    client = _client(firestore_client)
    conversation_ref = (
        client.collection('users').document(clean_uid).collection(CONVERSATIONS_COLLECTION).document(clean_conversation_id)
    )
    session_ref = _session_ref(client, clean_uid, clean_session_id) if clean_session_id else None
    transaction = client.transaction()

    @firestore.transactional
    def _delete_empty(transaction: Any) -> bool:
        snapshot = conversation_ref.get(transaction=transaction)
        if not getattr(snapshot, 'exists', False):
            return False
        conversation = snapshot.to_dict() or {}
        if (
            conversation.get('status') != 'in_progress'
            or conversation.get('discarded')
            or conversation.get('deleted')
            or conversation.get('is_locked')
            or conversation.get('sync_content_revision')
            or conversations_db.raw_conversation_has_content(clean_uid, conversation)
        ):
            return False

        if session_ref is not None:
            session_snapshot = session_ref.get(transaction=transaction)
            if getattr(session_snapshot, 'exists', False):
                session = session_snapshot.to_dict() or {}
                if (
                    session.get('uid') == clean_uid
                    and session.get('recording_session_id') == clean_session_id
                    and session.get('conversation_id') == clean_conversation_id
                ):
                    phase = str(session.get('lifecycle_phase') or 'in_progress')
                    if phase not in _TERMINAL_PHASES:
                        transaction.update(
                            session_ref,
                            {
                                'lifecycle_phase': 'discarded',
                                'lifecycle_sequence': int(session.get('lifecycle_sequence') or 0) + 1,
                                'updated_at': _now(),
                            },
                        )
        if deleted_conversation is not None:
            deleted_conversation.clear()
            deleted_conversation.update(conversation)
        transaction.delete(conversation_ref)
        return True

    return _delete_empty(transaction)


def _record_lifecycle_event_txn(
    transaction: Any,
    session_ref: Any,
    recording_session_id: str,
    conversation_id: str,
    phase: RecordingPhase,
    now: datetime,
) -> RecordingSessionEvent:
    snapshot = session_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return {
            'recording_session_id': recording_session_id,
            'conversation_id': conversation_id,
            'lifecycle_version': LIFECYCLE_ENVELOPE_VERSION,
            'lifecycle_phase': phase,
            'lifecycle_sequence': 0,
            'accepted': False,
            'discard_reason': 'missing_session',
        }
    current = snapshot.to_dict() or {}
    bound_conversation_id = str(current.get('conversation_id') or '')
    version = _clamp_lifecycle_version(current.get('lifecycle_version'))
    sequence = _clamp_lifecycle_sequence(current.get('lifecycle_sequence'))
    current_phase = str(current.get('lifecycle_phase') or 'in_progress')
    if bound_conversation_id != conversation_id:
        return {
            'recording_session_id': recording_session_id,
            'conversation_id': bound_conversation_id,
            'lifecycle_version': version,
            'lifecycle_phase': current_phase,
            'lifecycle_sequence': sequence,
            'accepted': False,
            'discard_reason': 'mapping_conflict',
        }
    if current_phase in _TERMINAL_PHASES and phase != current_phase:
        return {
            'recording_session_id': recording_session_id,
            'conversation_id': bound_conversation_id,
            'lifecycle_version': version,
            'lifecycle_phase': current_phase,
            'lifecycle_sequence': sequence,
            'accepted': False,
            'discard_reason': 'terminal_immutable',
        }
    if _PHASE_ORDER[phase] < _PHASE_ORDER.get(current_phase, -1):
        return {
            'recording_session_id': recording_session_id,
            'conversation_id': bound_conversation_id,
            'lifecycle_version': version,
            'lifecycle_phase': current_phase,
            'lifecycle_sequence': sequence,
            'accepted': False,
            'discard_reason': 'stale_event',
        }
    if phase == current_phase:
        return {
            'recording_session_id': recording_session_id,
            'conversation_id': bound_conversation_id,
            'lifecycle_version': version,
            'lifecycle_phase': current_phase,
            'lifecycle_sequence': sequence,
            'accepted': True,
            'discard_reason': None,
        }

    next_sequence = sequence + 1
    transaction.update(
        session_ref,
        {'lifecycle_phase': phase, 'lifecycle_sequence': next_sequence, 'updated_at': now},
    )
    return {
        'recording_session_id': recording_session_id,
        'conversation_id': bound_conversation_id,
        'lifecycle_version': version,
        'lifecycle_phase': phase,
        'lifecycle_sequence': next_sequence,
        'accepted': True,
        'discard_reason': None,
    }


def record_lifecycle_event(
    uid: str,
    recording_session_id: str,
    conversation_id: str,
    phase: RecordingPhase,
    *,
    firestore_client: Any = None,
) -> RecordingSessionEvent:
    """Append a monotonic lifecycle envelope, rejecting stale or misbound events."""
    clean_uid = _validate_id(uid, name='uid')
    clean_session_id = _validate_id(recording_session_id, name='recording_session_id')
    clean_conversation_id = _validate_id(conversation_id, name='conversation_id')
    if phase not in _PHASE_ORDER:
        raise ValueError(f'unsupported recording lifecycle phase: {phase}')
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_record_lifecycle_event_txn)
    return transactional(
        transaction,
        _session_ref(client, clean_uid, clean_session_id),
        clean_session_id,
        clean_conversation_id,
        phase,
        _now(),
    )


def run_with_transaction_contention_retry(client: Any, callback: Any, *args: Any, **kwargs: Any) -> Any:
    """Execute a transactional callback with native firestore.transactional contention retry."""
    transaction = client.transaction()
    transactional = firestore.transactional(callback)
    return transactional(transaction, *args, **kwargs)
