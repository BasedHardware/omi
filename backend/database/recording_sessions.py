"""Durable listen recording-session bindings and ordered lifecycle envelopes.

The user-scoped resource is the authority for mapping one recording session to
one conversation.  It intentionally stores only routing metadata: never
transcript text, credentials, or WebSocket payloads.  Conversation lifecycle
mutation remains owned by ``utils.conversations.lifecycle``; this adapter only
persists the recording identity and its outbound event sequence.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Mapping, TypedDict

from google.cloud import firestore

from database import conversations as conversations_db
from database._client import get_firestore_client
from database.firestore_transaction_retry import run_with_transaction_contention_retry

RECORDING_SESSIONS_COLLECTION = 'recording_sessions'
CONVERSATIONS_COLLECTION = 'conversations'
RECORDING_SESSION_SCHEMA_VERSION = 1
LIFECYCLE_ENVELOPE_VERSION = 1
RECORDING_SESSION_LEASE_DURATION = timedelta(minutes=5)
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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _client(firestore_client: Any = None) -> Any:
    return firestore_client if firestore_client is not None else get_firestore_client()


def _validate_id(value: Any, name: str) -> str:
    """Validate and sanitize an identifier against non-string, empty, or path-traversal inputs."""
    if not isinstance(value, str):
        raise ValueError(f'{name} must be a string')
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f'{name} cannot be empty')
    if '/' in cleaned or '\\' in cleaned or '..' in cleaned:
        raise ValueError(f'{name} contains invalid path traversal characters')
    return cleaned


def _session_ref(client: Any, uid: str, recording_session_id: str) -> Any:
    valid_uid = _validate_id(uid, 'uid')
    valid_sid = _validate_id(recording_session_id, 'recording_session_id')
    return client.collection('users').document(valid_uid).collection(RECORDING_SESSIONS_COLLECTION).document(valid_sid)


def _binding(data: dict[str, Any], recording_session_id: str, *, mapping_conflict: bool) -> RecordingSessionBinding:
    raw_sequence = data.get('lifecycle_sequence')
    try:
        sequence = int(raw_sequence) if raw_sequence is not None else 0
    except (ValueError, TypeError):
        sequence = 0
    sequence = max(0, sequence)

    raw_version = data.get('lifecycle_version')
    try:
        version = int(raw_version) if raw_version is not None else LIFECYCLE_ENVELOPE_VERSION
    except (ValueError, TypeError):
        version = LIFECYCLE_ENVELOPE_VERSION
    version = max(1, version)

    return {
        'recording_session_id': recording_session_id,
        'conversation_id': str(data.get('conversation_id') or ''),
        'lifecycle_version': version,
        'lifecycle_phase': str(data.get('lifecycle_phase') or 'in_progress'),
        'lifecycle_sequence': sequence,
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

    # Recovery admission discovers the live lease through this marker. Read it
    # before either write, then commit marker + session binding atomically so a
    # sweep can never observe a durable live session whose conversation is
    # still unfenced.
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
    """Atomically bind a session to exactly one canonical conversation ID with contention retry."""
    v_uid = _validate_id(uid, 'uid')
    v_sid = _validate_id(recording_session_id, 'recording_session_id')
    v_cid = _validate_id(proposed_conversation_id, 'proposed_conversation_id')
    client = _client(firestore_client)
    transactional = firestore.transactional(_create_or_get_recording_session_txn)

    def _txn_operation(transaction: Any) -> dict[str, Any]:
        return transactional(
            transaction,
            _session_ref(client, v_uid, v_sid),
            client.collection('users').document(v_uid).collection(CONVERSATIONS_COLLECTION),
            v_uid,
            v_sid,
            v_cid,
            _now(),
            include_conversation_snapshot,
        )

    return run_with_transaction_contention_retry(
        client.transaction,
        _txn_operation,
        operation_name='create_or_get_recording_session',
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
    """Renew a live session's lease against its identity and phase fence with contention retry."""
    try:
        v_uid = _validate_id(uid, 'uid')
        v_sid = _validate_id(recording_session_id, 'recording_session_id')
        v_cid = _validate_id(conversation_id, 'conversation_id')
    except ValueError:
        return False

    client = _client(firestore_client)
    transactional = firestore.transactional(_renew_recording_session_lease_txn)

    def _txn_operation(transaction: Any) -> bool:
        return transactional(
            transaction,
            _session_ref(client, v_uid, v_sid),
            v_uid,
            v_sid,
            v_cid,
            _now(),
        )

    return run_with_transaction_contention_retry(
        client.transaction,
        _txn_operation,
        operation_name='renew_recording_session_lease',
    )


def get_recording_session(
    uid: str,
    recording_session_id: str,
    *,
    firestore_client: Any = None,
) -> RecordingSessionBinding | None:
    """Read the canonical binding without proposing or mutating an identity."""
    v_uid = _validate_id(uid, 'uid')
    v_sid = _validate_id(recording_session_id, 'recording_session_id')
    snapshot = _session_ref(_client(firestore_client), v_uid, v_sid).get()
    if not getattr(snapshot, 'exists', False):
        return None
    data = snapshot.to_dict() or {}
    if data.get('uid') != v_uid or data.get('recording_session_id') != v_sid:
        raise ValueError('recording session identity does not match its document binding')
    return _binding(data, v_sid, mapping_conflict=False)


def tombstone_and_delete_empty_conversation(
    uid: str,
    conversation_id: str,
    recording_session_id: str | None,
    *,
    firestore_client: Any = None,
    deleted_conversation: dict[str, Any] | None = None,
) -> bool:
    """Atomically delete an empty live row and terminalize its bound session with contention retry.

    Segment/photo writes set the conversation's durable ``has_content`` marker
    in transactions on this same parent document. Firestore therefore retries
    this transaction when a late content write wins, preventing cleanup from
    deleting user data based on a stale empty read.

    ``deleted_conversation``, when supplied, receives the raw snapshot this
    transaction actually deleted. Physical cleanup that has to reason about the
    row's contents must read them from here rather than fetching the document
    itself: by the time this returns the row is gone, and a fetch beforehand
    would decide against a snapshot a concurrent write can still invalidate.
    """
    v_uid = _validate_id(uid, 'uid')
    v_cid = _validate_id(conversation_id, 'conversation_id')
    v_sid = _validate_id(recording_session_id, 'recording_session_id') if recording_session_id is not None else None

    client = _client(firestore_client)
    conversation_ref = client.collection('users').document(v_uid).collection(CONVERSATIONS_COLLECTION).document(v_cid)
    session_ref = _session_ref(client, v_uid, v_sid) if v_sid else None

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
            or conversations_db.raw_conversation_has_content(v_uid, conversation)
        ):
            return False

        if session_ref is not None:
            session_snapshot = session_ref.get(transaction=transaction)
            if getattr(session_snapshot, 'exists', False):
                session = session_snapshot.to_dict() or {}
                if (
                    session.get('uid') == v_uid
                    and session.get('recording_session_id') == v_sid
                    and session.get('conversation_id') == v_cid
                ):
                    phase = str(session.get('lifecycle_phase') or 'in_progress')
                    if phase not in _TERMINAL_PHASES:
                        raw_seq = session.get('lifecycle_sequence')
                        try:
                            curr_seq = int(raw_seq) if raw_seq is not None else 0
                        except (ValueError, TypeError):
                            curr_seq = 0
                        curr_seq = max(0, curr_seq)
                        transaction.update(
                            session_ref,
                            {
                                'lifecycle_phase': 'discarded',
                                'lifecycle_sequence': curr_seq + 1,
                                'updated_at': _now(),
                            },
                        )
        if deleted_conversation is not None:
            # A contended transaction re-runs this function, so publish the
            # snapshot that belongs to the attempt that actually commits.
            deleted_conversation.clear()
            deleted_conversation.update(conversation)
        transaction.delete(conversation_ref)
        return True

    return run_with_transaction_contention_retry(
        client.transaction,
        _delete_empty,
        operation_name='tombstone_and_delete_empty_conversation',
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

    raw_version = current.get('lifecycle_version')
    try:
        version = int(raw_version) if raw_version is not None else LIFECYCLE_ENVELOPE_VERSION
    except (ValueError, TypeError):
        version = LIFECYCLE_ENVELOPE_VERSION
    version = max(1, version)

    raw_sequence = current.get('lifecycle_sequence')
    try:
        sequence = int(raw_sequence) if raw_sequence is not None else 0
    except (ValueError, TypeError):
        sequence = 0
    sequence = max(0, sequence)

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
    """Append a monotonic lifecycle envelope, rejecting stale, misbound, or invalid events."""
    if phase not in _PHASE_ORDER:
        raise ValueError(f'unsupported recording lifecycle phase: {phase}')
    try:
        v_uid = _validate_id(uid, 'uid')
        v_sid = _validate_id(recording_session_id, 'recording_session_id')
        v_cid = _validate_id(conversation_id, 'conversation_id')
    except ValueError:
        return {
            'recording_session_id': str(recording_session_id or ''),
            'conversation_id': str(conversation_id or ''),
            'lifecycle_version': LIFECYCLE_ENVELOPE_VERSION,
            'lifecycle_phase': phase,
            'lifecycle_sequence': 0,
            'accepted': False,
            'discard_reason': 'invalid_identifier',
        }

    client = _client(firestore_client)
    transactional = firestore.transactional(_record_lifecycle_event_txn)

    def _txn_operation(transaction: Any) -> RecordingSessionEvent:
        return transactional(
            transaction,
            _session_ref(client, v_uid, v_sid),
            v_sid,
            v_cid,
            phase,
            _now(),
        )

    return run_with_transaction_contention_retry(
        client.transaction,
        _txn_operation,
        operation_name='record_lifecycle_event',
    )
