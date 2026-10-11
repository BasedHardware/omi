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
    try:
        client = firestore_client if firestore_client is not None else get_firestore_client()
        cid = row.get('id')
        if transaction is not None or not isinstance(cid, str) or not cid:
            return _read_calendar_window(uid, row, client, transaction)
        ref = client.collection('users').document(uid).collection('conversations').document(cid)

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
            hydrated = _read_calendar_window(uid, current, client, transaction)
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
    client = firestore_client if firestore_client is not None else get_firestore_client()
    user = client.collection('users').document(uid)
    root = user.collection('recording_sessions').document(origin_id)

    @firestore.transactional
    def resolve(transaction: Any) -> tuple[dict[str, str] | None, dict[str, str] | None]:
        cache_updates: list[tuple[Any, Mapping[str, Any]]] = []

        def hydrate(ref: Any, row: Mapping[str, Any]) -> Mapping[str, Any]:
            hydrated = calendar_continuity_row(uid, row, firestore_client=client, transaction=transaction)
            if hydrated is not row:
                cache_updates.append((ref, hydrated['external_data']))
            return hydrated

        try:
            original = root.get(transaction=transaction).to_dict() or {}
            if original.get('uid') != uid or original.get('recording_session_id') != origin_id:
                # Do not invent a canonical recording binding when dual-write failed.
                return None, None
            pointer = original.get('live_continuation') or {}
            cid, sid = pointer.get('conversation_id'), pointer.get('recording_session_id')
            retired = None
            if isinstance(cid, str) and isinstance(sid, str):
                ref = user.collection('conversations').document(cid)
                row = ref.get(transaction=transaction).to_dict() or {}
                row = hydrate(ref, row)
                if resumable_continuation(row, source=source, device_id=device_id, now=now, timeout=timeout):
                    return {'conversation_id': cid, 'recording_session_id': sid}, None
                finish = row.get('finished_at')
                if (
                    row.get('source') == source
                    and row.get('client_device_id') == device_id
                    and not row.get('is_locked')
                    and isinstance(finish, datetime)
                    and gap_splits((now - finish).total_seconds(), continuation_timeout(row, timeout))
                ):
                    retired = {'conversation_id': cid, 'recording_session_id': sid}
            if proposed is None:
                return None, None
            candidate = (
                user.collection('conversations')
                .document(proposed['conversation_id'])
                .get(transaction=transaction)
                .to_dict()
                or {}
            )
            candidate = hydrate(user.collection('conversations').document(proposed['conversation_id']), candidate)
            if not resumable_continuation(candidate, source=source, device_id=device_id, now=now, timeout=timeout):
                return None, None
            adopted = dict(proposed)
            transaction.update(root, {'live_continuation': adopted})
            return adopted, retired

        finally:
            # Every return has completed its reads, including a rejected pointer
            # followed by a candidate read. Cache only the external metadata.
            for ref, external in cache_updates:
                transaction.update(ref, {'external_data': external})

    return resolve(client.transaction())
