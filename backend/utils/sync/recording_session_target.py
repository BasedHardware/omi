"""Bind an unbound safety-WAL upload to the live conversation it already belongs to.

``/v4/listen`` stamps ``external_data.recording_session_id`` with the client-minted
recording id. A phone safety WAL that missed its conversation id can send that
same id. When it matches one conversation for this user, source, and device,
sync intake uses that conversation as an explicit target. No match keeps today's
temporal assignment.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Sequence, cast

logger = logging.getLogger(__name__)

_CANDIDATE_LIMIT = 5


def _text(value: Any) -> str:
    if not isinstance(value, str):
        return ''
    return value.strip()


def _source_value(source: Any) -> str:
    return _text(getattr(source, 'value', source))


def select_recording_session_target(
    rows: Sequence[Mapping[str, Any]],
    recording_session_id: str,
    *,
    source: Any,
    client_device_id: str | None,
    is_locked: bool,
) -> str | None:
    """Return the one conversation id that is safe to treat as an explicit target.

    Zero matches and more than one match both return None. An ambiguous id must
    not pick a conversation, and a provenance mismatch must not be handed to
    intake: the explicit-target path rejects it and fails the upload.
    """
    session_id = _text(recording_session_id)
    device_id = _text(client_device_id)
    source_value = _source_value(source)
    if not session_id or not device_id or not source_value:
        return None
    matches: list[str] = []
    for row in rows:
        if row.get('deleted'):
            continue
        external = row.get('external_data') or {}
        if _text(external.get('recording_session_id') if isinstance(external, Mapping) else None) != session_id:
            continue
        if _source_value(row.get('source')) != source_value:
            continue
        if _text(row.get('client_device_id')) != device_id:
            continue
        if bool(row.get('is_locked')) != bool(is_locked):
            continue
        conversation_id = _text(row.get('id'))
        if conversation_id:
            matches.append(conversation_id)
    if len(matches) != 1:
        return None
    return matches[0]


def _candidate_rows(uid: str, recording_session_id: str, *, firestore_client: Any = None) -> list[dict[str, Any]]:
    # Import on use. pipeline.py loads this module while unit tests have stubbed
    # google.cloud and database._client, and a module-level import fails collection.
    from google.cloud.firestore_v1.base_query import FieldFilter

    from database._client import get_firestore_client
    from database.conversations import conversations_collection

    client = firestore_client or get_firestore_client()
    query = (
        client.collection('users')
        .document(uid)
        .collection(conversations_collection)
        .where(filter=FieldFilter('external_data.recording_session_id', '==', recording_session_id))
        .limit(_CANDIDATE_LIMIT)
    )
    rows: list[dict[str, Any]] = []
    for doc in query.stream():
        data = doc.to_dict()
        if isinstance(data, dict):
            rows.append(cast(dict[str, Any], data))
    return rows


def resolve_recording_session_sync_target(
    uid: str,
    recording_session_id: str | None,
    source: Any,
    client_device_id: str | None,
    is_locked: bool,
    *,
    firestore_client: Any = None,
) -> str | None:
    """Look up the live conversation for this recording, or None to keep unbound sync.

    A lookup failure is unbound sync, not a failed upload. Old clients omit the
    id and never reach the query.
    """
    session_id = _text(recording_session_id)
    if not session_id:
        return None
    try:
        rows = _candidate_rows(uid, session_id, firestore_client=firestore_client)
    except Exception as exc:
        logger.warning(
            'event=sync_recording_session_target outcome=lookup_failed uid=%s exception_type=%s',
            uid,
            type(exc).__name__,
        )
        return None
    return select_recording_session_target(
        rows,
        session_id,
        source=source,
        client_device_id=client_device_id,
        is_locked=is_locked,
    )
