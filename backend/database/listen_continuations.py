"""Metadata-only continuation pointers; the original recording binding is immutable."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Mapping

from google.cloud import firestore

from database._client import get_firestore_client
from database.document_ids import calendar_meeting_doc_id
from utils.observability.fallback import record_fallback
from utils.conversation_continuity import (
    calendar_continuity_identity,
    calendar_continuity_window,
    continuation_timeout,
    gap_splits,
    resumable_continuation,
)

logger = logging.getLogger(__name__)

# A Firestore document id is a path segment: a '/' (or a NUL) in a caller-supplied
# identifier silently retargets the write, so identifiers are bounded and rejected.
IDENTIFIER_MAX_LENGTH = 256
DEFAULT_CONTINUATION_TIMEOUT = 300
MIN_CONTINUATION_TIMEOUT = 1
MAX_CONTINUATION_TIMEOUT = 24 * 60 * 60


def _clean_identifier(value: Any, field: str) -> str | None:
    """Return a usable Firestore document id, or ``None`` when the value is not one."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > IDENTIFIER_MAX_LENGTH:
        return None
    if any(bad in cleaned for bad in ('/', '\\', '\x00')):
        return None
    return cleaned


def _clean_timeout(value: Any) -> int:
    """Clamp a caller-supplied continuation timeout to a sane window."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return DEFAULT_CONTINUATION_TIMEOUT
    return max(MIN_CONTINUATION_TIMEOUT, min(int(value), MAX_CONTINUATION_TIMEOUT))


def _elapsed_seconds(now: datetime, then: datetime) -> float:
    """Seconds from ``then`` to ``now``, aligning naive and aware values.

    Firestore hands back offset-naive datetimes while callers pass aware ones, and
    subtracting the two raises ``TypeError``. A naive value is read as UTC.
    """
    if now.tzinfo is None and then.tzinfo is not None:
        now = now.replace(tzinfo=then.tzinfo)
    elif now.tzinfo is not None and then.tzinfo is None:
        then = then.replace(tzinfo=now.tzinfo)
    return (now - then).total_seconds()


def _clean_proposal(proposed: Any) -> dict[str, str] | None:
    """Validate a proposed continuation binding before it can be adopted."""
    if not isinstance(proposed, Mapping):
        return None
    conversation_id = _clean_identifier(proposed.get('conversation_id'), 'conversation id')
    recording_session_id = _clean_identifier(proposed.get('recording_session_id'), 'recording session id')
    if conversation_id is None or recording_session_id is None:
        return None
    return {'conversation_id': conversation_id, 'recording_session_id': recording_session_id}


def _read_calendar_window(uid: str, row: Mapping[str, Any], client: Any, transaction: Any = None) -> Mapping[str, Any]:
    identity = calendar_continuity_identity(row)
    if identity is None:
        return row
    event_id, source = identity
    meeting_id = calendar_meeting_doc_id(uid, source, event_id)
    record = (
        client.collection('users')
        .document(uid)
        .collection('meetings')
        .document(meeting_id)
        .get(transaction=transaction)
        .to_dict()
    ) or {}
    if (
        record.get('calendar_event_id') != event_id
        or record.get('calendar_source') != source
        or calendar_continuity_window(record) is None
    ):
        return row
    external = row.get('external_data')
    external = external if isinstance(external, Mapping) else {}
    return {**row, 'external_data': {**external, 'calendar_meeting_context': record}}


def calendar_continuity_row(
    uid: str, row: Mapping[str, Any], *, firestore_client: Any = None, transaction: Any = None
) -> Mapping[str, Any]:
    """Resolve an existing identity and cache its window on the persisted row.

    Transaction callers defer the cache write until every admission read is done.
    Lifecycle polls use their own transaction so caching cannot overwrite newer
    external metadata or stamp a meeting identity that changed since the poll.
    """
    identity = calendar_continuity_identity(row)
    if identity is None:
        return row
    clean_uid = _clean_identifier(uid, 'uid')
    if clean_uid is None:
        return row
    try:
        client = firestore_client if firestore_client is not None else get_firestore_client()
        cid = row.get('id')
        if transaction is not None or not isinstance(cid, str) or not cid:
            return _read_calendar_window(clean_uid, row, client, transaction)
        ref = client.collection('users').document(clean_uid).collection('conversations').document(cid)

        @firestore.transactional
        def cache(transaction: Any) -> Mapping[str, Any]:
            current = ref.get(transaction=transaction).to_dict() or {}
            if not current:
                return row
            current_identity = calendar_continuity_identity(current)
            if current_identity != identity:
                # A previous poll may already have cached this window, or a
                # concurrent owner may have changed the event. Use fresh metadata.
                return {**row, 'external_data': current.get('external_data')}
            hydrated = _read_calendar_window(clean_uid, current, client, transaction)
            if hydrated is not current:
                transaction.update(ref, {'external_data': hydrated['external_data']})
                return {**row, 'external_data': hydrated['external_data']}
            return row

        return cache(client.transaction())
    except Exception as error:
        logger.warning('calendar_continuity_lookup outcome=unavailable exception_type=%s', type(error).__name__)
        record_fallback(
            component='other',
            from_mode='calendar_continuity',
            to_mode='silence_boundary',
            reason='other',
            outcome='degraded',
            log=logger,
        )
        return row


def resolve_live_continuation(
    uid: str,
    origin_id: str,
    *,
    source: str,
    device_id: str | None,
    now: datetime,
    timeout: int,
    proposed: Mapping[str, str] | None = None,
    firestore_client: Any = None,
) -> tuple[dict[str, str] | None, dict[str, str] | None]:
    """Read or atomically adopt a persisted continuation without rebinding its origin.

    A proposal must already have its conversation and recording binding persisted.
    Contending proposals converge on the first still-resumable generation. The
    lifecycle owner cleans up an unexposed losing proposal through fenced deletion.
    No transcript is read, decoded, or rewritten here.
    """
    clean_uid = _clean_identifier(uid, 'uid')
    clean_origin_id = _clean_identifier(origin_id, 'origin_id')
    clean_source = _clean_identifier(source, 'source')
    clean_device_id = _clean_identifier(device_id, 'device_id') if device_id is not None else None
    if clean_uid is None or clean_origin_id is None or clean_source is None:
        return None, None
    bounded_timeout = _clean_timeout(timeout)
    clean_proposal = _clean_proposal(proposed)

    try:
        client = firestore_client if firestore_client is not None else get_firestore_client()
        user = client.collection('users').document(clean_uid)
        root = user.collection('recording_sessions').document(clean_origin_id)

        @firestore.transactional
        def resolve(transaction: Any) -> tuple[dict[str, str] | None, dict[str, str] | None]:
            cache_updates: list[tuple[Any, Mapping[str, Any]]] = []

            def hydrate(ref: Any, row: Mapping[str, Any]) -> Mapping[str, Any]:
                hydrated = calendar_continuity_row(clean_uid, row, firestore_client=client, transaction=transaction)
                if hydrated is not row:
                    cache_updates.append((ref, hydrated['external_data']))
                return hydrated

            try:
                original = root.get(transaction=transaction).to_dict() or {}
                if original.get('uid') != clean_uid or original.get('recording_session_id') != clean_origin_id:
                    # Do not invent a canonical recording binding when dual-write failed.
                    return None, None
                pointer = original.get('live_continuation') or {}
                cid, sid = pointer.get('conversation_id'), pointer.get('recording_session_id')
                retired = None
                if isinstance(cid, str) and isinstance(sid, str):
                    ref = user.collection('conversations').document(cid)
                    row = ref.get(transaction=transaction).to_dict() or {}
                    row = hydrate(ref, row)
                    if resumable_continuation(
                        row, source=clean_source, device_id=clean_device_id, now=now, timeout=bounded_timeout
                    ):
                        return {'conversation_id': cid, 'recording_session_id': sid}, None
                    finish = row.get('finished_at')
                    if (
                        row.get('source') == clean_source
                        and row.get('client_device_id') == clean_device_id
                        and not row.get('is_locked')
                        and isinstance(finish, datetime)
                        and gap_splits(_elapsed_seconds(now, finish), continuation_timeout(row, bounded_timeout))
                    ):
                        retired = {'conversation_id': cid, 'recording_session_id': sid}
                if clean_proposal is None:
                    return None, None
                candidate = (
                    user.collection('conversations')
                    .document(clean_proposal['conversation_id'])
                    .get(transaction=transaction)
                    .to_dict()
                    or {}
                )
                candidate = hydrate(
                    user.collection('conversations').document(clean_proposal['conversation_id']), candidate
                )
                if not resumable_continuation(
                    candidate, source=clean_source, device_id=clean_device_id, now=now, timeout=bounded_timeout
                ):
                    return None, None
                adopted = dict(clean_proposal)
                transaction.update(root, {'live_continuation': adopted})
                return adopted, retired

            finally:
                # Every return has completed its reads, including a rejected pointer
                # followed by a candidate read. Cache only the external metadata.
                for ref, external in cache_updates:
                    transaction.update(ref, {'external_data': external})

        return resolve(client.transaction())
    except Exception as error:
        logger.warning('live_continuation_lookup outcome=unavailable exception_type=%s', type(error).__name__)
        record_fallback(
            component='other',
            from_mode='live_continuation',
            to_mode='silence_boundary',
            reason='other',
            outcome='degraded',
            log=logger,
        )
        return None, None
