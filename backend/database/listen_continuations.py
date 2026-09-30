"""Metadata-only continuation pointers; the original recording binding is immutable."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Mapping

from google.cloud import firestore

from database._client import get_firestore_client
from utils.conversation_continuity import gap_splits, resumable_continuation

logger = logging.getLogger(__name__)

MAX_ID_LENGTH = 128
DEFAULT_TIMEOUT_SECONDS = 120


def _clean_str(value: Any, max_len: int = MAX_ID_LENGTH) -> str:
    """Normalize and validate general string parameters."""
    if not isinstance(value, str):
        return ""
    cleaned = value.strip()
    if not cleaned or len(cleaned) > max_len:
        return ""
    return cleaned


def _clean_id(value: Any, max_len: int = MAX_ID_LENGTH) -> str:
    """Normalize and validate document / user identifiers."""
    if not isinstance(value, str):
        return ""
    cleaned = value.strip()
    if not cleaned or len(cleaned) > max_len or any(c in cleaned for c in ("/", "\\", "\0", "..")):
        return ""
    return cleaned


def _clean_timeout(timeout: Any, default: int = DEFAULT_TIMEOUT_SECONDS) -> int:
    """Sanitize timeout ensuring positive integer."""
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        return default
    return timeout


def _normalize_datetime(dt: Any) -> datetime:
    """Ensure datetime is timezone-aware in UTC to prevent offset subtraction errors."""
    if not isinstance(dt, datetime):
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _align_datetime_tz(dt: datetime, reference: datetime) -> datetime:
    """Align datetime timezone awareness with reference datetime."""
    if reference.tzinfo is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    if reference.tzinfo is None and dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _resolve_client(firestore_client: Any = None) -> Any:
    """Resolve Firestore client with caller dependency injection support."""
    if firestore_client is not None:
        return firestore_client
    try:
        c = get_firestore_client()
        if c is not None:
            return c
    except Exception:
        pass
    try:
        from database._client import db

        return db
    except Exception:
        return None


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
    clean_uid = _clean_id(uid)
    clean_origin_id = _clean_id(origin_id)
    clean_source = _clean_str(source)
    if not clean_uid or not clean_origin_id or not clean_source:
        return None, None

    clean_device_id = _clean_id(device_id) if device_id is not None else None
    valid_timeout = _clean_timeout(timeout)
    valid_now = _normalize_datetime(now)

    clean_proposed: dict[str, str] | None = None
    if proposed is not None:
        try:
            prop_cid = _clean_id(proposed.get('conversation_id'))
            prop_sid = _clean_id(proposed.get('recording_session_id'))
            if not prop_cid or not prop_sid:
                return None, None
            clean_proposed = {'conversation_id': prop_cid, 'recording_session_id': prop_sid}
        except (AttributeError, TypeError):
            return None, None

    try:
        client = _resolve_client(firestore_client)
        if client is None:
            logger.warning("No firestore client available for resolve_live_continuation")
            return None, None

        user = client.collection('users').document(clean_uid)
        root = user.collection('recording_sessions').document(clean_origin_id)

        def _resolve_core(transaction: Any) -> tuple[dict[str, str] | None, dict[str, str] | None]:
            orig_snap = root.get(transaction=transaction)
            if not orig_snap or getattr(orig_snap, 'exists', None) is False:
                return None, None
            original = orig_snap.to_dict() or {}
            if original.get('uid') != clean_uid or original.get('recording_session_id') != clean_origin_id:
                # Do not invent a canonical recording binding when dual-write failed.
                return None, None
            pointer = original.get('live_continuation') or {}
            cid = _clean_id(pointer.get('conversation_id'))
            sid = _clean_id(pointer.get('recording_session_id'))
            retired = None
            if cid and sid:
                row_snap = user.collection('conversations').document(cid).get(transaction=transaction)
                row = (row_snap.to_dict() or {}) if getattr(row_snap, 'exists', None) is not False else {}
                if 'finished_at' in row and isinstance(row['finished_at'], datetime):
                    row['finished_at'] = _align_datetime_tz(row['finished_at'], valid_now)
                if resumable_continuation(
                    row, source=clean_source, device_id=clean_device_id, now=valid_now, timeout=valid_timeout
                ):
                    return {'conversation_id': cid, 'recording_session_id': sid}, None
                finish = row.get('finished_at')
                if (
                    row.get('source') == clean_source
                    and row.get('client_device_id') == clean_device_id
                    and not row.get('is_locked')
                    and isinstance(finish, datetime)
                ):
                    if gap_splits((valid_now - finish).total_seconds(), valid_timeout):
                        retired = {'conversation_id': cid, 'recording_session_id': sid}
            if clean_proposed is None:
                return None, None
            candidate_snap = (
                user.collection('conversations')
                .document(clean_proposed['conversation_id'])
                .get(transaction=transaction)
            )
            candidate = (candidate_snap.to_dict() or {}) if getattr(candidate_snap, 'exists', None) is not False else {}
            if 'finished_at' in candidate and isinstance(candidate['finished_at'], datetime):
                candidate['finished_at'] = _align_datetime_tz(candidate['finished_at'], valid_now)
            if not resumable_continuation(
                candidate, source=clean_source, device_id=clean_device_id, now=valid_now, timeout=valid_timeout
            ):
                return None, None
            adopted = dict(clean_proposed)
            transaction.update(root, {'live_continuation': adopted})
            return adopted, retired

        txn = client.transaction() if callable(getattr(client, 'transaction', None)) else None
        if txn is not None:
            try:
                return firestore.transactional(_resolve_core)(txn)
            except (AttributeError, TypeError):
                return _resolve_core(txn)
        return _resolve_core(None)
    except Exception as e:
        logger.warning("Error in resolve_live_continuation for uid %s, origin %s: %s", clean_uid, clean_origin_id, e)
        return None, None
