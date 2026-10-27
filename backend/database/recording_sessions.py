"""Durable listen recording-session bindings and ordered lifecycle envelopes.

The user-scoped resource is the authority for mapping one recording session to
one conversation.  It intentionally stores only routing metadata: never
transcript text, credentials, or WebSocket payloads.  Conversation lifecycle
mutation remains owned by ``utils.conversations.lifecycle``; this adapter only
persists the recording identity and its outbound event sequence.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Mapping, TypedDict

from google.cloud import firestore

from database import conversations as conversations_db
from database._client import get_firestore_client, run_transactional
from database.firestore_transaction_retry import run_with_transaction_contention_retry
from database.people_stats_cache import invalidate_people_stats_cache

logger = logging.getLogger(__name__)

RECORDING_SESSIONS_COLLECTION = 'recording_sessions'
CONVERSATIONS_COLLECTION = 'conversations'
RECORDING_SESSION_SCHEMA_VERSION = 1
LIFECYCLE_ENVELOPE_VERSION = 1
RECORDING_SESSION_LEASE_DURATION = timedelta(minutes=5)
# A renewal commits read-only while the durable fence still has more than this
# much runway, and re-stamps the full duration once it decays to or below it.
# Two minutes is one renewal interval of guaranteed coverage (the next cycle
# re-checks in one minute) plus the redrive budget (three 15s waits), so a
# skipped minute never lets the fence reach a recovery sweep before the next
# renewal can re-arm it.
RECORDING_SESSION_LEASE_RUNWAY_FLOOR = timedelta(minutes=2)
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
    """Atomically bind a session to exactly one canonical conversation ID.

    Runs on the shared bounded transaction contention budget with the
    expired-transaction restart, like the lease renewal it races (and like the
    recovery admission both of them conflict with). Firestore replays a commit
    abort on the same — often already retired — transaction id and never
    retries an abort raised by the body's read, so a bare
    ``firestore.transactional`` call surfaces a mid-open contention burst as a
    permanent rejection; the session's shadow fail-open branch then degrades
    the whole recording to the legacy route (prod backend-listen 2026-10-14:
    ``recording session persistence failed; retaining shadow legacy route``
    plus its ``open_recording_session`` traceback sibling, ×49/30m each).
    """
    if not uid or not recording_session_id or not proposed_conversation_id:
        raise ValueError('uid, recording_session_id, and proposed_conversation_id are required')
    client = _client(firestore_client)
    session_ref = _session_ref(client, uid, recording_session_id)

    def run_once(transaction: Any) -> dict[str, Any]:
        return run_transactional(
            client,
            firestore.transactional(_create_or_get_recording_session_txn),
            session_ref,
            client.collection('users').document(uid).collection(CONVERSATIONS_COLLECTION),
            uid,
            recording_session_id,
            proposed_conversation_id,
            _now(),
            include_conversation_snapshot,
            initial_transaction=transaction,
        )

    return run_with_transaction_contention_retry(
        client.transaction,
        run_once,
        operation_name='recording_session_open',
    )


def _remaining_lease_runway(current: Mapping[str, Any], now: datetime) -> timedelta | None:
    """Runway left on the stored fence, or None when it is missing/malformed.

    Firestore stores naive datetimes; a stored fence is read as UTC exactly
    like the recovery sweep reads it back (see
    ``conversation_finalization_jobs._has_active_recording_session_lease``).
    """
    lease_expires_at = current.get('lease_expires_at')
    if not isinstance(lease_expires_at, datetime):
        return None
    if lease_expires_at.tzinfo is None and now.tzinfo is not None:
        lease_expires_at = lease_expires_at.replace(tzinfo=timezone.utc)
    return lease_expires_at - now


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
    remaining_runway = _remaining_lease_runway(current, now)
    if remaining_runway is not None and remaining_runway > RECORDING_SESSION_LEASE_RUNWAY_FLOOR:
        # The fence the previous renewal stamped still holds: this minute's
        # renewal has nothing to move, so commit the verified read without a
        # write. A write here would take the same document lock every
        # lifecycle event and the recovery sweep need — for four of every
        # five renewals, only to rewrite the value the last one wrote (prod
        # backend-listen 2026-10-27: the renewal ×184/30m and the open
        # ×143/30m, the two boundaries this contention engine feeds). The
        # transactional read above IS the renewal: it re-verifies identity
        # and phase, keeps the whole verification atomic with any competing
        # writer's commit, and reports True because the fence is verified
        # live, not decayed. Skips never consume the fence — it is wall
        # clock — so silence still decays to the floor and the next renewal
        # re-stamps the full duration from that instant.
        logger.info(
            'recording session lease runway verified; nothing written ' 'uid=%s session=%s conversation=%s runway_s=%d',
            uid,
            recording_session_id,
            conversation_id,
            int(remaining_runway.total_seconds()),
        )
        return True
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
    """Renew a live session's lease against its identity and phase fence.

    The renewal races every lifecycle event and the recovery sweep's admission
    transaction on the same session document for the whole life of a live
    recording. Firestore's SDK retries a commit ``Aborted`` by replaying the
    *same* transaction id — the id a read-time abort has already retired — and
    never retries an ``Aborted`` raised by the body's read, so each contention
    burst surfaced as ``recording session lease renewal failed`` ERRORs from
    ``renew_live_recording_session_lease`` and let the five-minute fence run
    down while audio still flowed. Both retry layers the rest of ``database/``
    uses apply here: the shared bounded fresh-transaction contention budget
    replays a read-time abort on a brand-new transaction, and
    ``run_transactional`` restarts an expired-transaction rejection.

    Since 2026-10-27 the renewal commits read-only while the durable fence
    still holds more than ``RECORDING_SESSION_LEASE_RUNWAY_FLOOR`` of runway:
    the transactional read re-verifies identity and phase, reports True, and
    writes nothing, so roughly two of every three renewals stop taking the
    document lock every lifecycle event and the recovery sweep need. The
    floor keeps one renewal interval plus the redrive budget of guaranteed
    coverage; once wall-clock decay reaches it the next renewal re-stamps the
    full duration, preserving blackout immunity exactly as before.
    """
    if not uid or not recording_session_id or not conversation_id:
        return False
    client = _client(firestore_client)
    return run_with_transaction_contention_retry(
        client.transaction,
        lambda transaction: run_transactional(
            client,
            firestore.transactional(_renew_recording_session_lease_txn),
            _session_ref(client, uid, recording_session_id),
            uid,
            recording_session_id,
            conversation_id,
            _now(),
            initial_transaction=transaction,
        ),
        operation_name='recording_session_lease_renewal',
    )


def get_recording_session(
    uid: str,
    recording_session_id: str,
    *,
    firestore_client: Any = None,
) -> RecordingSessionBinding | None:
    """Read the canonical binding without proposing or mutating an identity."""
    if not uid or not recording_session_id:
        raise ValueError('uid and recording_session_id are required')
    snapshot = _session_ref(_client(firestore_client), uid, recording_session_id).get()
    if not getattr(snapshot, 'exists', False):
        return None
    data = snapshot.to_dict() or {}
    if data.get('uid') != uid or data.get('recording_session_id') != recording_session_id:
        raise ValueError('recording session identity does not match its document binding')
    return _binding(data, recording_session_id, mapping_conflict=False)


def tombstone_and_delete_empty_conversation(
    uid: str,
    conversation_id: str,
    recording_session_id: str | None,
    *,
    firestore_client: Any = None,
    deleted_conversation: dict[str, Any] | None = None,
) -> bool:
    """Atomically delete an empty live row and terminalize its bound session.

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
    client = _client(firestore_client)
    conversation_ref = (
        client.collection('users').document(uid).collection(CONVERSATIONS_COLLECTION).document(conversation_id)
    )
    session_ref = _session_ref(client, uid, recording_session_id) if recording_session_id else None

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
            or conversations_db.raw_conversation_has_content(uid, conversation)
        ):
            return False

        if session_ref is not None:
            session_snapshot = session_ref.get(transaction=transaction)
            if getattr(session_snapshot, 'exists', False):
                session = session_snapshot.to_dict() or {}
                if (
                    session.get('uid') == uid
                    and session.get('recording_session_id') == recording_session_id
                    and session.get('conversation_id') == conversation_id
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
            # A contended transaction re-runs this function, so publish the
            # snapshot that belongs to the attempt that actually commits.
            deleted_conversation.clear()
            deleted_conversation.update(conversation)
        transaction.delete(conversation_ref)
        return True

    # The same contention story as the session's other writers: the SDK replays
    # a commit abort on the same — often retired — transaction id and never
    # retries an abort raised by the body's read, so a rollover that races a
    # late segment write or the lease renewal surfaced as a permanent rejection
    # instead of a replay. Every rejection here is atomic — the body either
    # reaches a refusal without writing or commits its delete — so replaying on
    # fresh transactions is safe, and ``run_transactional`` restarts an
    # expired-transaction rejection on a brand-new id. The body is wrapped per
    # attempt: one ``firestore.transactional`` wrapper pins a single
    # ``retry_id`` across every budget attempt, so a commit abort inside the
    # budget replays the very id the read-time abort retired — the exact
    # pinned-replay shape ``run_transactional`` exists to prevent, on the same
    # session document whose adjacent writers produced the window's
    # ``recording session lease renewal failed`` and ``open_recording_session``
    # tracebacks (prod backend-listen 2026-10-21).
    deleted = run_with_transaction_contention_retry(
        client.transaction,
        lambda transaction: run_transactional(
            client,
            firestore.transactional(_delete_empty),
            initial_transaction=transaction,
        ),
        operation_name='recording_session_empty_delete',
    )
    if deleted:
        invalidate_people_stats_cache(uid)
    return deleted


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
    """Append a monotonic lifecycle envelope, rejecting stale or misbound events.

    Like ``create_or_get_recording_session``, this runs on the shared bounded
    contention budget with the expired-transaction restart: a burst may replay
    freely because every rejection here is atomic — the body either reaches a
    classification without writing or commits its single envelope update. The
    session's shadow fail-open branch must see only real write failures, not a
    retried contention burst masquerading as one.
    """
    if phase not in _PHASE_ORDER:
        raise ValueError(f'unsupported recording lifecycle phase: {phase}')
    client = _client(firestore_client)

    def run_once(transaction: Any) -> RecordingSessionEvent:
        return run_transactional(
            client,
            firestore.transactional(_record_lifecycle_event_txn),
            _session_ref(client, uid, recording_session_id),
            recording_session_id,
            conversation_id,
            phase,
            _now(),
            initial_transaction=transaction,
        )

    return run_with_transaction_contention_retry(
        client.transaction,
        run_once,
        operation_name='recording_session_lifecycle_event',
    )
