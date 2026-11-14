"""Stores the phone's end-of-recording marker on its recording-session document.

Owns one field, ``capture_end``, on ``users/{uid}/recording_sessions/{id}``. The
session document stays the single authority for the recording's identity; this
module never creates one, never changes the binding, and stores only numbers
and closed labels.
"""

from __future__ import annotations

from typing import Any, Mapping

from google.cloud import firestore

from database._client import get_firestore_client, run_transactional
from database.recording_sessions import RECORDING_SESSIONS_COLLECTION
from utils.sync.capture_end import FIELD


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
    client = firestore_client if firestore_client is not None else get_firestore_client()
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
    client = firestore_client if firestore_client is not None else get_firestore_client()
    snapshot = _ref(client, uid, recording_session_id).get()
    if not getattr(snapshot, 'exists', False):
        return None
    data = snapshot.to_dict() or {}
    marker = data.get(FIELD)
    return dict(marker) if data.get('uid') == uid and isinstance(marker, Mapping) else None
