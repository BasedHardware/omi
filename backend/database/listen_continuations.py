"""Metadata-only continuation pointers; the original recording binding is immutable."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from google.cloud import firestore

from database._client import get_firestore_client
from utils.conversation_continuity import gap_splits, resumable_continuation


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
        original = root.get(transaction=transaction).to_dict() or {}
        if original.get('uid') != uid or original.get('recording_session_id') != origin_id:
            # Do not invent a canonical recording binding when dual-write failed.
            return None, None
        pointer = original.get('live_continuation') or {}
        cid, sid = pointer.get('conversation_id'), pointer.get('recording_session_id')
        retired = None
        if isinstance(cid, str) and isinstance(sid, str):
            row = user.collection('conversations').document(cid).get(transaction=transaction).to_dict() or {}
            if resumable_continuation(row, source=source, device_id=device_id, now=now, timeout=timeout):
                return {'conversation_id': cid, 'recording_session_id': sid}, None
            finish = row.get('finished_at')
            if (
                row.get('source') == source
                and row.get('client_device_id') == device_id
                and not row.get('is_locked')
                and isinstance(finish, datetime)
                and gap_splits((now - finish).total_seconds(), timeout)
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
        if not resumable_continuation(candidate, source=source, device_id=device_id, now=now, timeout=timeout):
            return None, None
        adopted = dict(proposed)
        transaction.update(root, {'live_continuation': adopted})
        return adopted, retired

    return resolve(client.transaction())
