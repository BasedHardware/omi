"""Durable listen recording-session bindings and ordered lifecycle envelopes.

The user-scoped resource is the authority for mapping one recording session to
one conversation.  It intentionally stores only routing metadata: never
transcript text, credentials, or WebSocket payloads.  Conversation lifecycle
mutation remains owned by ``utils.conversations.lifecycle``; this adapter only
persists the recording identity and its outbound event sequence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, TypedDict

from google.cloud import firestore

from database._client import get_firestore_client

RECORDING_SESSIONS_COLLECTION = 'recording_sessions'
RECORDING_SESSION_SCHEMA_VERSION = 1
LIFECYCLE_ENVELOPE_VERSION = 1
RecordingPhase = Literal['in_progress', 'processing', 'completed', 'failed', 'discarded']

_PHASE_ORDER: dict[str, int] = {
    'in_progress': 0,
    'processing': 1,
    'completed': 2,
    'failed': 2,
    'discarded': 2,
}


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
    return (
        client.collection('users')
        .document(uid)
        .collection(RECORDING_SESSIONS_COLLECTION)
        .document(recording_session_id)
    )


def _binding(data: dict[str, Any], recording_session_id: str, *, mapping_conflict: bool) -> RecordingSessionBinding:
    return {
        'recording_session_id': recording_session_id,
        'conversation_id': str(data['conversation_id']),
        'lifecycle_version': int(data.get('lifecycle_version') or LIFECYCLE_ENVELOPE_VERSION),
        'lifecycle_phase': str(data.get('lifecycle_phase') or 'in_progress'),
        'lifecycle_sequence': int(data.get('lifecycle_sequence') or 0),
        'mapping_conflict': mapping_conflict,
    }


def _create_or_get_recording_session_txn(
    transaction: Any,
    session_ref: Any,
    uid: str,
    recording_session_id: str,
    proposed_conversation_id: str,
    now: datetime,
) -> RecordingSessionBinding:
    snapshot = session_ref.get(transaction=transaction)
    if getattr(snapshot, 'exists', False):
        current = snapshot.to_dict() or {}
        if current.get('uid') != uid or current.get('recording_session_id') != recording_session_id:
            raise ValueError('recording session identity does not match its document binding')
        return _binding(
            current,
            recording_session_id,
            mapping_conflict=current.get('conversation_id') != proposed_conversation_id,
        )

    session = {
        'schema_version': RECORDING_SESSION_SCHEMA_VERSION,
        'uid': uid,
        'recording_session_id': recording_session_id,
        'conversation_id': proposed_conversation_id,
        'lifecycle_version': LIFECYCLE_ENVELOPE_VERSION,
        'lifecycle_phase': 'in_progress',
        'lifecycle_sequence': 0,
        'created_at': now,
        'updated_at': now,
    }
    transaction.create(session_ref, session)
    return _binding(session, recording_session_id, mapping_conflict=False)


def create_or_get_recording_session(
    uid: str,
    recording_session_id: str,
    proposed_conversation_id: str,
    *,
    firestore_client: Any = None,
) -> RecordingSessionBinding:
    """Atomically bind a session to exactly one canonical conversation ID."""
    if not uid or not recording_session_id or not proposed_conversation_id:
        raise ValueError('uid, recording_session_id, and proposed_conversation_id are required')
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_create_or_get_recording_session_txn)
    return transactional(
        transaction,
        _session_ref(client, uid, recording_session_id),
        uid,
        recording_session_id,
        proposed_conversation_id,
        _now(),
    )


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
    version = int(current.get('lifecycle_version') or LIFECYCLE_ENVELOPE_VERSION)
    sequence = int(current.get('lifecycle_sequence') or 0)
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
    if phase not in _PHASE_ORDER:
        raise ValueError(f'unsupported recording lifecycle phase: {phase}')
    client = _client(firestore_client)
    transaction = client.transaction()
    transactional = firestore.transactional(_record_lifecycle_event_txn)
    return transactional(
        transaction,
        _session_ref(client, uid, recording_session_id),
        recording_session_id,
        conversation_id,
        phase,
        _now(),
    )
