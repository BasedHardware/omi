"""Bounded, presentation-only wait for a completed server-batch capture's transcript.

The completion CAS stamps the deadline once. Readers never renew it and never
write a lifecycle status. Shared database hydration must remain authoritative
for replace_record and finalization replay; apply project only at API exits.
"""

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from config.episodes import home_transcription_presentation_gate_enabled
from utils.conversations.fragment_visibility import BATCH_RECORD_OWNERS

READ_FIELDS = (
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


def deadline(row: Mapping[str, Any]) -> datetime:
    """The stamped deadline of a row ``applies`` accepted, as an aware datetime."""
    value = row['home_transcription_deadline_at']
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def presentation_state(row: Mapping[str, Any], *, now: datetime | None = None) -> tuple[str, str | None]:
    """User-facing card state; stored failed rows remain subject to visibility."""
    if applies(row):
        if row.get('record_upload_failed'):
            return 'failed', 'record_upload_failed'
        if row.get('finalization_status') == 'dead_letter':
            return 'failed', 'dead_letter'
        if (now or datetime.now(timezone.utc)) >= deadline(row):
            return 'failed', 'transcription_deadline_exceeded'
        return 'transcribing', None
    if getattr(row.get('status'), 'value', row.get('status')) == 'processing':
        return 'pending', None
    return 'done', None


def project(row: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Return a wire copy; expired/error captures stay visible as completed rows."""
    if not applies(row):
        return row
    processing_status, failure_reason = presentation_state(row, now=now)
    failed = processing_status == 'failed'
    return {
        **row,
        'status': 'completed' if failed else 'processing',
        'structured': {**(row.get('structured') or {}), 'title': "Couldn't transcribe" if failed else 'Transcribing…'},
        # Preserve the decision before the projected title/status make applies false.
        'processing_status': processing_status,
        'failure_reason': failure_reason,
    }
