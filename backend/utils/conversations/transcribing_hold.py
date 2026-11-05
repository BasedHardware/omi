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

READ_FIELDS = ('home_transcription_pending_at', 'home_transcription_deadline_at', 'record_lane_owner')


def transcription_presentation(deadline: datetime, *, failed: bool = False, now: datetime | None = None):
    """The Episodes Home transcription labels, shared with conversation reads."""
    overdue = (now or datetime.now(timezone.utc)) >= deadline
    return ("Couldn't transcribe", 'failed') if failed or overdue else ('Transcribing…', 'processing')


def applies(row: Mapping[str, Any]) -> bool:
    """Only stamped completed batch captures without a transcript or title qualify.

    Indexed list reads omit transcript data. The batch projection receipt
    prevents an omitted-but-landed transcript from becoming a placeholder.
    has_content is intentionally ignored: closed raw audio sets it before STT.
    """
    return bool(
        home_transcription_presentation_gate_enabled()
        and getattr(row.get('status'), 'value', row.get('status')) == 'completed'
        and row.get('record_lane_owner') in BATCH_RECORD_OWNERS
        and isinstance(row.get('home_transcription_deadline_at'), datetime)
        and not row.get('record_projection_revision')
        and not row.get('transcript_segments')
        and not str(row.get('user_title') or '').strip()
        and not str((row.get('structured') or {}).get('title') or '').strip()
    )


def project(row: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    """Return a wire copy; expired/error captures stay visible as completed rows."""
    if not applies(row):
        return row
    deadline = row['home_transcription_deadline_at']
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    title, status = transcription_presentation(
        deadline,
        failed=bool(row.get('record_upload_failed') or row.get('finalization_status') == 'dead_letter'),
        now=now,
    )
    return {
        **row,
        'status': 'completed' if status == 'failed' else status,
        'structured': {**(row.get('structured') or {}), 'title': title},
    }
