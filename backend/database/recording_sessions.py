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

from database import conversations as conversations_db
from database.store import get_document_store

RECORDING_SESSIONS_COLLECTION = 'recording_sessions'
CONVERSATIONS_COLLECTION = 'conversations'
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
_TERMINAL_PHASES = frozenset({'completed', 'failed', 'discarded'})


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


def _store():
    """The configured document store (``STORAGE_BACKEND`` seam, ADR-0002/0004). Tests patch this."""
    return get_document_store()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _session_path(uid: str, recording_session_id: str) -> str:
    return f'users/{uid}/{RECORDING_SESSIONS_COLLECTION}/{recording_session_id}'


def _conversation_path(uid: str, conversation_id: str) -> str:
    return f'users/{uid}/{CONVERSATIONS_COLLECTION}/{conversation_id}'


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
    tx: Any,
    session_path: str,
    uid: str,
    recording_session_id: str,
    proposed_conversation_id: str,
    now: datetime,
) -> RecordingSessionBinding:
    snapshot = tx.get(session_path)
    if snapshot.exists:
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
    tx.set(session_path, session)
    return _binding(session, recording_session_id, mapping_conflict=False)


def create_or_get_recording_session(
    uid: str,
    recording_session_id: str,
    proposed_conversation_id: str,
) -> RecordingSessionBinding:
    """Atomically bind a session to exactly one canonical conversation ID."""
    if not uid or not recording_session_id or not proposed_conversation_id:
        raise ValueError('uid, recording_session_id, and proposed_conversation_id are required')
    session_path = _session_path(uid, recording_session_id)
    now = _now()
    return _store().run_transaction(
        lambda tx: _create_or_get_recording_session_txn(
            tx,
            session_path,
            uid,
            recording_session_id,
            proposed_conversation_id,
            now,
        )
    )


def get_recording_session(
    uid: str,
    recording_session_id: str,
) -> RecordingSessionBinding | None:
    """Read the canonical binding without proposing or mutating an identity."""
    if not uid or not recording_session_id:
        raise ValueError('uid and recording_session_id are required')
    snapshot = _store().get(_session_path(uid, recording_session_id))
    if not snapshot.exists:
        return None
    data = snapshot.to_dict() or {}
    if data.get('uid') != uid or data.get('recording_session_id') != recording_session_id:
        raise ValueError('recording session identity does not match its document binding')
    return _binding(data, recording_session_id, mapping_conflict=False)


def tombstone_and_delete_empty_conversation(
    uid: str,
    conversation_id: str,
    recording_session_id: str | None,
) -> bool:
    """Atomically delete an empty live row and terminalize its bound session.

    Segment/photo writes set the conversation's durable ``has_content`` marker
    in transactions on this same parent document. Firestore therefore retries
    this transaction when a late content write wins, preventing cleanup from
    deleting user data based on a stale empty read.
    """
    conversation_path = _conversation_path(uid, conversation_id)
    session_path = _session_path(uid, recording_session_id) if recording_session_id else None

    def _delete_empty(tx: Any) -> bool:
        snapshot = tx.get(conversation_path)
        if not snapshot.exists:
            return False
        conversation = snapshot.to_dict() or {}
        if (
            conversation.get('status') != 'in_progress'
            or conversation.get('discarded')
            or conversations_db.raw_conversation_has_content(uid, conversation)
        ):
            return False

        # All reads precede any write: read the bound session before deleting.
        if session_path is not None:
            session_snapshot = tx.get(session_path)
            if session_snapshot.exists:
                session = session_snapshot.to_dict() or {}
                if (
                    session.get('uid') == uid
                    and session.get('recording_session_id') == recording_session_id
                    and session.get('conversation_id') == conversation_id
                ):
                    phase = str(session.get('lifecycle_phase') or 'in_progress')
                    if phase not in _TERMINAL_PHASES:
                        tx.update(
                            session_path,
                            {
                                'lifecycle_phase': 'discarded',
                                'lifecycle_sequence': int(session.get('lifecycle_sequence') or 0) + 1,
                                'updated_at': _now(),
                            },
                        )
        tx.delete(conversation_path)
        return True

    return _store().run_transaction(_delete_empty)


def _record_lifecycle_event_txn(
    tx: Any,
    session_path: str,
    recording_session_id: str,
    conversation_id: str,
    phase: RecordingPhase,
    now: datetime,
) -> RecordingSessionEvent:
    snapshot = tx.get(session_path)
    if not snapshot.exists:
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
    tx.update(
        session_path,
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
) -> RecordingSessionEvent:
    """Append a monotonic lifecycle envelope, rejecting stale or misbound events."""
    if phase not in _PHASE_ORDER:
        raise ValueError(f'unsupported recording lifecycle phase: {phase}')
    session_path = _session_path(uid, recording_session_id)
    now = _now()
    return _store().run_transaction(
        lambda tx: _record_lifecycle_event_txn(
            tx,
            session_path,
            recording_session_id,
            conversation_id,
            phase,
            now,
        )
    )
