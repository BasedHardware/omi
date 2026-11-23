"""Bounded, presentation-only wait for a completed server-batch capture's transcript.

The completion CAS stamps the server wait once. The first seal admission may
advance its presentation anchor once; readers never renew it or write status. Shared database
hydration must remain authoritative for replace_record and finalization replay;
apply project only at API exits.
"""

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any
import math

from config.episodes import (
    home_step_projection_enabled,
    home_transcription_deadline_seconds,
    home_transcription_max_age_seconds,
    home_transcription_presentation_gate_enabled,
    home_transcription_queue_hold_enabled,
)
from utils.conversations.fragment_visibility import BATCH_RECORD_OWNERS
from config.transcription_pending import pending_retry_enabled, seal_wait_enabled
from utils.conversations import empty_capture
from utils.conversations.home_titles import placeholder_title_wire, untitled_pending

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
    'record_admitted_at',
    'home_transcription_queue_observed_at',
    'has_content',
    'episode_transcription_pending_at',
    'episode_transcription_deadline_at',
    'sync_content_revision',
    'is_locked',
    'server_batch_audio_received',
    'server_batch_audio_closed',
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
        and (
            isinstance(row.get('home_transcription_deadline_at'), datetime)
            or seal_wait_enabled()
            and home_transcription_queue_hold_enabled()
            and isinstance(row.get('episode_transcription_deadline_at'), datetime)
        )
        and not row.get('record_projection_revision')
        and not has_transcript
        and not str(row.get('user_title') or '').strip()
        # A placeholder stamped on a capture stub is not a title; a placeholder
        # beside real notes is a finished row and keeps them visible.
        and untitled_pending(row.get('structured') or {})
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
    if (
        prefix == 'home_transcription'
        and not row.get('home_transcription_pending_at')
        and not row.get('home_transcription_deadline_at')
        and seal_wait_enabled()
        and isinstance(row.get('episode_transcription_deadline_at'), datetime)
    ):
        prefix = 'episode_transcription'
    if not home_transcription_queue_hold_enabled():
        return _utc(row[f'{prefix}_deadline_at'])
    anchor = wait_started_at(row, prefix=prefix)
    if anchor is None:
        raise ValueError('transcription wait has no server timestamp')
    # Both native seal and full-proof repair CAS this first-admission clock only
    # when absent. Reconnects, retries, requeues and repeated reads cannot move
    # it. Do not use record_sealed_at: that clock changes on every reseal.
    if seal_wait_enabled():
        for key in ('record_admitted_at', 'home_transcription_queue_observed_at'):
            admitted = row.get(key)
            if (
                isinstance(admitted, (int, float))
                and not isinstance(admitted, bool)
                and math.isfinite(admitted)
                and admitted > 0
            ):
                try:
                    anchor = max(anchor, datetime.fromtimestamp(admitted, timezone.utc))
                except (OverflowError, OSError, ValueError):
                    pass
    return anchor + timedelta(seconds=home_transcription_max_age_seconds())


def failed(row: Mapping[str, Any]) -> bool:
    """Explicit row failure receipts win over the queue wait, irrespective of age."""
    return bool(
        getattr(row.get('status'), 'value', row.get('status')) == 'failed'
        or row.get('record_upload_failed')
        or row.get('finalization_status') == 'dead_letter'
    )


def project(row: dict[str, Any], *, now: datetime | None = None, home_list: bool = False) -> dict[str, Any]:
    """Return a wire copy; expired/error captures stay visible as completed rows."""
    empty = empty_capture.project(row, now=now)
    if empty is not row:
        return empty
    if not applies(row):
        # home_list is set only after the route computed the current wire step.
        return placeholder_title_wire(
            row, label_recording=home_list and home_step_projection_enabled() and row.get('home_step') == 'ready'
        )
    deadline_at = deadline(row)
    receipt_failed = failed(row)
    title, status = transcription_presentation(
        deadline_at,
        failed=receipt_failed,
        now=now,
    )
    return {
        **row,
        'status': 'completed' if status == 'failed' else status,
        'structured': {**(row.get('structured') or {}), 'title': title},
        **({'summary_retryable': False} if home_transcription_queue_hold_enabled() and not receipt_failed else {}),
        # The wait ran out with no failure receipt: the audio is kept and still waiting for
        # transcription (for example held by the free allowance). Clients that know the owner's
        # allowance is spent say so instead of offering a retry; older clients ignore the field.
        **({'transcription_wait': 'overdue'} if status == 'failed' and not receipt_failed else {}),
    }


def retry_pending(row: Mapping[str, Any]) -> bool:
    """Stored capture evidence, independent of titles and display switches.

    A title (including a user title) is not transcript evidence. In particular,
    Couldn't transcribe is synthesized on reads, never required in storage.
    This handler receives the hydrated full row, not a slim list projection.
    """
    return bool(
        pending_retry_enabled()
        and row.get('record_lane_owner') in BATCH_RECORD_OWNERS
        and row.get('status') in {'completed', 'in_progress', 'processing', 'failed'}
        and any(
            isinstance(row.get(key), datetime)
            for key in ('home_transcription_deadline_at', 'episode_transcription_deadline_at')
        )
        and not row.get('record_projection_revision')
        and not row.get('transcript_segments')
    )


def retry_wire(row: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any] | None:
    """No model or job mutation. None asks the API to return a clear non-200.

    There is no owner-click priority promotion in this pipeline. Do not turn
    old audio into fresh audio or overwrite a worker's claim/backoff. A recent
    first seal is enough to return the released client's processing contract.
    """
    empty = empty_capture.project(row, now=now)
    if empty is not row:
        return empty
    prefix = (
        'home_transcription'
        if isinstance(row.get('home_transcription_deadline_at'), datetime)
        else 'episode_transcription'
    )
    title, status = transcription_presentation(deadline(row, prefix=prefix), failed=failed(row), now=now)
    if status == 'failed' or row.get('discarded'):
        return None
    return {
        **row,
        'status': 'processing',
        'home_step': 'transcribing',
        'summary_retryable': False,
        'structured': {**(row.get('structured') or {}), 'title': row.get('user_title') or title},
    }
