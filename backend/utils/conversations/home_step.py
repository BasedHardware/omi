"""The Home row contract: what each listed conversation is to the Home screen.

David's ruling (2026-11-05): noise never shows on Home; anything still being
processed shows as Processing with its current step, and a run of them is one
row. The server knows which rows are which; this projection says so on the
list wire as ``home_step`` so clients stop inferring it from titles.

- ``ready``: finished; may show as its own row.
- ``transcribing`` / ``writing_notes``: still being processed, at that step.
- ``failed``: processing gave up; the client folds these into one row.
- ``noise``: finished with nothing worth a Home row: no speech, below floor,
  or a stand-in title (first sentence / "Recording · time") that no summary
  will ever replace.

Presentation only: nothing is stored, search and direct links are unaffected,
and a curated row (user title, star, folder, photos) is always ``ready``.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from config.episodes import home_step_projection_enabled
from utils.conversations import transcribing_hold
from utils.conversations.fragment_visibility import is_completed_below_floor, is_user_curated
from utils.conversations.home_titles import summary_owed
from utils.conversations.summary_delivery import EMPTY_BLOCKED_REASONS

READY = 'ready'
TRANSCRIBING = 'transcribing'
WRITING_NOTES = 'writing_notes'
FAILED = 'failed'
NOISE = 'noise'

# Matches the stamped HOME_TRANSCRIPTION_DEADLINE_SECONDS default and the batch SLA.
LEGACY_TRANSCRIPTION_SECONDS = 2 * 60 * 60


def _value(value: Any) -> Any:
    return getattr(value, 'value', value)


def classify(row: Mapping[str, Any]) -> str | None:
    """The row's Home step, or None for live rows and when the projection is off.

    Call on the stored read copy, before ``transcribing_hold.project`` rewrites
    status and title for the wire.
    """
    if not home_step_projection_enabled():
        return None
    status = _value(row.get('status'))
    structured = row.get('structured') or {}
    title = str(structured.get('title') or '').strip()
    if status in ('processing', 'merging'):
        return TRANSCRIBING if not title else WRITING_NOTES
    if status == 'failed':
        return FAILED
    if status != 'completed':
        return None
    if str(row.get('user_title') or '').strip() or is_user_curated(row):
        return READY
    if transcribing_hold.applies(row):
        _, presented = transcribing_hold.transcription_presentation(
            transcribing_hold.deadline(row),
            failed=bool(row.get('record_upload_failed') or row.get('finalization_status') == 'dead_letter'),
        )
        return FAILED if presented == 'failed' else TRANSCRIBING
    if (
        row.get('finalization_status') == 'dead_letter'
        or row.get('summary_retryable')
        or row.get('record_upload_failed')
    ):
        return FAILED
    provisional = structured.get('title_provenance') == 'server_minimum'
    if is_completed_below_floor(row) or (provisional and row.get('summary_blocked_reason') in EMPTY_BLOCKED_REASONS):
        return NOISE
    if provisional:
        if summary_owed(row):
            return WRITING_NOTES
        if row.get('summary_output_present') or row.get('summary_completed_at'):
            # A real summary landed; read projections may still re-stamp an echo title.
            return READY
        # The stand-in title is final: nothing will ever summarize this row.
        return NOISE
    if not title and not str(structured.get('overview') or '').strip() and not row.get('transcript_segments'):
        # A capture whose speech has not landed. Unstamped legacy rows get the same
        # bound the stamped ones have, so none can stay Processing forever.
        return FAILED if _older_than(row.get('finished_at'), LEGACY_TRANSCRIPTION_SECONDS) else TRANSCRIBING
    return READY


def _older_than(moment: Any, seconds: float) -> bool:
    if not isinstance(moment, datetime):
        return False
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - moment).total_seconds() >= seconds


def project(row: dict[str, Any]) -> dict[str, Any]:
    """Return a wire copy carrying ``home_step`` (unchanged when there is none)."""
    step = classify(row)
    return row if step is None else {**row, 'home_step': step}
