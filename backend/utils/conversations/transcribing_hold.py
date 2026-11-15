"""Bounded, presentation-only wait for a completed server-batch capture's transcript.

The completion CAS stamps the server wait once. Readers bound that wait without
using capture age, renewing it, or writing a lifecycle status. Shared database
hydration must remain authoritative for replace_record and finalization replay;
apply project only at API exits.
"""

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

from config.episodes import (
    home_transcription_deadline_seconds,
    home_transcription_max_age_seconds,
    home_transcription_presentation_gate_enabled,
    home_transcription_queue_hold_enabled,
)
from utils.conversations.fragment_visibility import BATCH_RECORD_OWNERS

READ_FIELDS = (
    'created_at',
    'home_transcription_pending_at',
    'home_transcription_deadline_at',
    'record_lane_owner',
    'status',
    'record_projection_revision',
    'record_upload_failed',
    'finalization_status',
    'user_title',
)


def transcription_presentation(deadline: datetime, *, failed: bool = False, now: datetime | None = None):
    """The Episodes Home transcription labels, shared with conversation reads."""
    overdue = (now or datetime.now(timezone.utc)) >= deadline
    return ("Couldn't transcribe", 'failed') if failed or overdue else ('Transcribing…', 'processing')


def applies(row: Mapping[str, Any], *, stored: bool = False) -> bool:
    """Only stamped completed batch captures without a transcript or title qualify.

    Indexed list reads omit transcript data. The batch projection receipt
    prevents an omitted-but-landed transcript from becoming a placeholder.
    has_content is intentionally ignored: closed raw audio sets it before STT.
    Raw storage may encode even an empty transcript as bytes or encrypted text.
    That blob is unknown to visibility, not proof of speech; the batch receipt
    remains authoritative there. API projection runs after transcript hydration.
    """
    segments = row.get('transcript_segments')
    has_transcript = bool(segments) and (not stored or isinstance(segments, (list, tuple)))
    return bool(
        home_transcription_presentation_gate_enabled()
        and getattr(row.get('status'), 'value', row.get('status')) == 'completed'
        and row.get('record_lane_owner') in BATCH_RECORD_OWNERS
        and isinstance(row.get('home_transcription_deadline_at'), datetime)
        and not row.get('record_projection_revision')
        and not has_transcript
        and not str(row.get('user_title') or '').strip()
        and not str((row.get('structured') or {}).get('title') or '').strip()
    )


def _utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def wait_started_at(row: Mapping[str, Any], *, prefix: str = 'home_transcription') -> datetime | None:
    """Server wait start, including old rows that retained only its deadline.

    Capture end can predate offline upload by days. Creation is only a fallback
    when neither pending stamp exists; updated_at and read time never renew it.
    """
    for key in (f'{prefix}_pending_at', f'{prefix}_deadline_at', 'created_at'):
        value = row.get(key)
        if not isinstance(value, (datetime, str)):
            continue
        try:
            anchor = _utc(value)
        except ValueError:
            continue
        return (
            anchor - timedelta(seconds=home_transcription_deadline_seconds())
            if key.endswith('_deadline_at')
            else anchor
        )
    return None


def deadline(row: Mapping[str, Any], *, prefix: str = 'home_transcription') -> datetime:
    """Read-time bound heals old stamps without a write, renewal, or job lookup."""
    if not home_transcription_queue_hold_enabled():
        return _utc(row[f'{prefix}_deadline_at'])
    anchor = wait_started_at(row, prefix=prefix)
    if anchor is None:
        raise ValueError('transcription wait has no server timestamp')
    return anchor + timedelta(seconds=home_transcription_max_age_seconds())


def failed(row: Mapping[str, Any]) -> bool:
    """Explicit row failure receipts win over the queue wait, irrespective of age."""
    return bool(
        getattr(row.get('status'), 'value', row.get('status')) == 'failed'
        or row.get('record_upload_failed')
        or row.get('finalization_status') == 'dead_letter'
    )


def project(row: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Return a wire copy; expired/error captures stay visible as completed rows."""
    if not applies(row):
        return row
    deadline_at = deadline(row)
    title, status = transcription_presentation(
        deadline_at,
        failed=failed(row),
        now=now,
    )
    return {
        **row,
        'status': 'completed' if status == 'failed' else status,
        'structured': {**(row.get('structured') or {}), 'title': title},
        **({'summary_retryable': False} if home_transcription_queue_hold_enabled() and not failed(row) else {}),
    }
