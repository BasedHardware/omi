"""Bind an unbound safety-WAL upload to the live conversation it belongs to.

``/v4/listen`` stamps ``external_data.recording_session_id`` with the client
recording id. Binding also requires source, device, lock state, and full audio
interval containment with bounded edge allowance. A client id can outlive
server-side silence rollover; the bounded interval prevents a spanning WAL
from binding to the earlier generation.
No unique match keeps today's temporal assignment.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence, cast

logger = logging.getLogger(__name__)

_CANDIDATE_LIMIT = 5
# The socket can open after the first buffered frames (or the phone clock can
# differ slightly). finished_at is the last recognized word, while the WAL can
# contain trailing silence. A 60-second tail is less than the 120-second
# silence-rollover gap; larger spans remain unbound.
_START_SKEW_SECONDS = 5
_TRAILING_AUDIO_SECONDS = 60


def _text(value: Any) -> str:
    if not isinstance(value, str):
        return ''
    return value.strip()


def _source_value(source: Any) -> str:
    return _text(getattr(source, 'value', source))


def _unix_seconds(value: Any) -> float | None:
    if isinstance(value, datetime):
        normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return normalized.timestamp()
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def select_recording_session_target(
    rows: Sequence[Mapping[str, Any]],
    recording_session_id: str,
    *,
    source: Any,
    client_device_id: str | None,
    is_locked: bool,
    audio_start_seconds: float | None = None,
    audio_end_seconds: float | None = None,
) -> str | None:
    """Return the one conversation id that is safe to treat as an explicit target.

    Zero matches, an ambiguous id, a provenance mismatch, or an audio interval
    that crosses a generation boundary keeps the existing unbound sync path.
    """
    session_id = _text(recording_session_id)
    device_id = _text(client_device_id)
    source_value = _source_value(source)
    if not session_id or not device_id or not source_value:
        return None
    if (
        audio_start_seconds is None
        or audio_end_seconds is None
        or not math.isfinite(audio_start_seconds)
        or not math.isfinite(audio_end_seconds)
        or audio_end_seconds <= audio_start_seconds
    ):
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
        conversation_start = _unix_seconds(row.get('started_at'))
        conversation_end = _unix_seconds(row.get('finished_at'))
        if (
            conversation_start is None
            or conversation_end is None
            or conversation_end < conversation_start
            or audio_start_seconds > conversation_end
            or audio_end_seconds < conversation_start
            or audio_start_seconds < conversation_start - _START_SKEW_SECONDS
            or audio_end_seconds > conversation_end + _TRAILING_AUDIO_SECONDS
        ):
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
        .limit(_CANDIDATE_LIMIT + 1)
    )
    rows: list[dict[str, Any]] = []
    seen = 0
    for doc in query.stream():
        seen += 1
        data = doc.to_dict()
        if isinstance(data, dict):
            rows.append(cast(dict[str, Any], data))
    # A truncated query cannot establish uniqueness, even if only one of the
    # visible rows passes the provenance and interval checks.
    if seen > _CANDIDATE_LIMIT:
        return []
    return rows


def resolve_recording_session_sync_target(
    uid: str,
    recording_session_id: str | None,
    source: Any,
    client_device_id: str | None,
    is_locked: bool,
    audio_start_seconds: float | None = None,
    audio_end_seconds: float | None = None,
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
        try:
            from utils.sync.backfill_cutover import uid_hash

            log_uid_hash = uid_hash(uid)
        except Exception:
            log_uid_hash = 'unavailable'
        logger.warning(
            'event=sync_recording_session_target outcome=lookup_failed uid_hash=%s exception_type=%s',
            log_uid_hash,
            type(exc).__name__,
        )
        return None
    return select_recording_session_target(
        rows,
        session_id,
        source=source,
        client_device_id=client_device_id,
        is_locked=is_locked,
        audio_start_seconds=audio_start_seconds,
        audio_end_seconds=audio_end_seconds,
    )
