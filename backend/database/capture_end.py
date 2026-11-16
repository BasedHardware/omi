"""Stores the phone's end-of-recording marker on its recording-session document.

Owns one field, ``capture_end``, on ``users/{uid}/recording_sessions/{id}``. The
session document stays the single authority for the recording's identity; this
module never creates one, never changes the binding, and stores only numbers
and closed labels.
Seal proofs read, never write, the capture's ``pipeline_ledger`` document.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

from utils.sync import capture_end as policy
from utils.sync.capture_end import FIELD

logger = logging.getLogger(__name__)

# Import-light on purpose: the frozen legacy sync pipeline imports this module,
# and its tests load that pipeline with the Firestore client stubbed. Storage
# dependencies are imported where they are used. The collection name is pinned
# to ``database.recording_sessions`` by a test.
RECORDING_SESSIONS_COLLECTION = 'recording_sessions'
# ``database.pipeline_ledger.COLLECTION``, pinned by the same test.
PIPELINE_LEDGER_COLLECTION = 'pipeline_ledger'


def _client(firestore_client: Any) -> Any:
    if firestore_client is not None:
        return firestore_client
    from database._client import get_firestore_client

    return get_firestore_client()


def _ref(client: Any, uid: str, recording_session_id: str) -> Any:
    return (
        client.collection('users')
        .document(uid)
        .collection(RECORDING_SESSIONS_COLLECTION)
        .document(recording_session_id)
    )


def store(
    uid: str, recording_session_id: str, marker: Mapping[str, Any], *, firestore_client: Any = None
) -> tuple[str, str | None]:
    """Write ``marker`` unless a later end is already stored.

    Returns ``(outcome, conversation_id)``: ``stored``, ``duplicate`` (the same
    end decision with the same pending count), ``stale`` (an older decision), or
    ``unbound`` when no session document exists for this owner.
    """
    from google.cloud import firestore

    from database._client import run_transactional

    client = _client(firestore_client)
    ref = _ref(client, uid, recording_session_id)

    @firestore.transactional
    def commit(transaction: Any) -> tuple[str, str | None]:
        snapshot = ref.get(transaction=transaction)
        data = snapshot.to_dict() if getattr(snapshot, 'exists', False) else None
        if not data or data.get('uid') != uid:
            return 'unbound', None
        conversation_id = data.get('conversation_id')
        conversation_id = str(conversation_id) if conversation_id else None
        current = data.get(FIELD) or {}
        previous = float(current.get('end_decided_at') or 0)
        if marker['end_decided_at'] < previous:
            return 'stale', conversation_id
        if marker['end_decided_at'] == previous:
            if int(current.get('pending_wals') or 0) <= int(marker['pending_wals']):
                return 'duplicate', conversation_id
            # A resend of the same decision only ever lowers the pending count;
            # the first receipt keeps its observed time and mapped end.
            marker_to_write = {**current, 'pending_wals': marker['pending_wals']}
        else:
            marker_to_write = dict(marker)
        transaction.update(ref, {FIELD: marker_to_write})
        return 'stored', conversation_id

    return run_transactional(client, commit, transient=True)


def load(uid: str, recording_session_id: str, *, firestore_client: Any = None) -> dict[str, Any] | None:
    """One document read; ``None`` when the session or its marker is absent."""
    snapshot = _ref(_client(firestore_client), uid, recording_session_id).get()
    if not getattr(snapshot, 'exists', False):
        return None
    data = snapshot.to_dict() or {}
    marker = data.get(FIELD)
    return dict(marker) if data.get('uid') == uid and isinstance(marker, Mapping) else None


def load_ledger(uid: str, capture_id: str, *, firestore_client: Any = None) -> dict[str, Any] | None:
    """The capture's lifecycle-ledger document, or ``None``. One document read."""
    snapshot = (
        _client(firestore_client)
        .collection('users')
        .document(uid)
        .collection(PIPELINE_LEDGER_COLLECTION)
        .document(capture_id)
        .get()
    )
    return (snapshot.to_dict() or None) if getattr(snapshot, 'exists', False) else None


def sealed(uid: str, conversation_data: Mapping[str, Any], *, firestore_client: Any = None) -> bool:
    """Whether the server's own seal proves this batch-owned live row ended with all its text landed.

    The row decides first with no read (``policy.seal_barrier``); only a row
    that passes reads its ledger document once. A read failure is "not proven".
    """
    capture_id = conversation_data.get('id')
    if not policy.enabled() or policy.seal_barrier(conversation_data) is not None or not isinstance(capture_id, str):
        return False
    try:
        ledger = load_ledger(uid, capture_id, firestore_client=firestore_client)
    except Exception as error:
        logger.warning('event=capture_end_proof outcome=ledger_read_error exception_type=%s', type(error).__name__)
        return False
    if policy.seal_proof(conversation_data, ledger) != 'proven':
        return False
    policy.record_proof('sealed')
    return True


def proven(uid: str, conversation_data: Mapping[str, Any], *, firestore_client: Any = None) -> bool:
    """Whether this row's recording is proven ended with its speech landed.

    Asked by hold admission only when it would otherwise wait, outside any
    transaction. A batch-owned live record is proven by the server's own seal
    once every unit of its transcript has landed (``sealed``). Otherwise the
    phone's marker decides: one session document read, and only for a row that
    carries a recording session id. Any failure is "not proven"; the quiet rule
    is the fallback, never an error.
    """
    if sealed(uid, conversation_data, firestore_client=firestore_client):
        return True
    recording = (conversation_data.get('external_data') or {}).get('recording_session_id')
    if not policy.enabled() or not isinstance(recording, str) or not recording:
        return False
    try:
        marker = load(uid, recording, firestore_client=firestore_client)
    except Exception as error:
        logger.warning('event=capture_end_proof outcome=read_error exception_type=%s', type(error).__name__)
        return False
    result = policy.proof(conversation_data, marker)
    policy.record_proof(result)
    return result == 'proven'
