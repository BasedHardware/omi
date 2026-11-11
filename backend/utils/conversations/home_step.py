"""The Home row contract: what each listed conversation is to the Home screen.

David's ruling (2026-11-05): noise never shows on Home; anything still being
processed shows as Processing with its current step, and a run of them is one
row. The server knows which rows are which; this projection says so on the
list wire as ``home_step`` so clients stop inferring it from titles.

- ``ready``: finished; may show as its own row.
- ``transcribing`` / ``writing_notes``: still being processed, at that step.
- ``failed``: processing gave up or exceeded the Home wait; default Home hides it.
- ``noise``: finished with nothing worth a Home row: no speech, below floor,
  a stand-in title (first sentence / "Recording · time") that no summary will
  ever replace, or a terminal empty-output block (``empty_output_exhausted`` /
  ``empty_output_lifetime_exhausted``) with no overview or section body and no
  banked receipt or open debt. ``HOME_EMPTY_OUTPUT_NOISE=false`` restores the
  legacy stand-in-title-only rule.

Presentation only: nothing is stored, search and direct links are unaffected,
and a completed curated row (user title, star, folder, photos) is always ``ready``.
Processing rows, including curated ones, have a bounded presentation wait.
The step is independent of the viewer's day: clients show processing on Home
only on the current local day and place older work in Activity instead.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from prometheus_client import Counter

from config.episodes import (
    DEFAULT_HOME_PROCESSING_MAX_AGE_SECONDS,
    home_empty_output_noise_enabled,
    home_processing_max_age_seconds,
    home_step_projection_enabled,
)
from utils.conversations import transcribing_hold
from utils.conversations.fragment_visibility import is_completed_below_floor, is_user_curated
from utils.conversations.home_titles import summary_owed
from utils.conversations.summary_delivery import EMPTY_BLOCKED_REASONS, present

READY = 'ready'
TRANSCRIBING = 'transcribing'
WRITING_NOTES = 'writing_notes'
FAILED = 'failed'
NOISE = 'noise'

# Matches the stamped HOME_TRANSCRIPTION_DEADLINE_SECONDS default and the batch SLA.
LEGACY_TRANSCRIPTION_SECONDS = 2 * 60 * 60


class HomeProcessingAgeReason(StrEnum):
    UNKNOWN = 'unknown'
    INVALID_CONFIG = 'invalid_config'
    MISSING_TIMESTAMP = 'missing_timestamp'
    EXPIRED = 'expired'


PROCESSING_AGE_TOTAL = Counter(
    'omi_home_processing_age_total',
    'Home processing age decisions per classification, not unique conversations',
    ['reason'],
)


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
        seconds = home_processing_max_age_seconds()
        if seconds is None:
            PROCESSING_AGE_TOTAL.labels(reason=HomeProcessingAgeReason.INVALID_CONFIG).inc()
            seconds = DEFAULT_HOME_PROCESSING_MAX_AGE_SECONDS
        # processing_admitted_at is a renewable lease, not an entry clock.
        # There is no stored processing_started. Capture end is the best stable
        # fallback; created_at covers legacy rows. Never use updated_at or the
        # recording start (started_at) to measure a processing wait.
        anchor = next((row[key] for key in ('finished_at', 'created_at') if isinstance(row.get(key), datetime)), None)
        if anchor is None:
            PROCESSING_AGE_TOTAL.labels(reason=HomeProcessingAgeReason.MISSING_TIMESTAMP).inc()
        elif _older_than(anchor, seconds):
            PROCESSING_AGE_TOTAL.labels(reason=HomeProcessingAgeReason.EXPIRED).inc()
            return FAILED
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
    # The projection stamp records provenance on the row, not in structured, so
    # it does not suppress derived effects through is_server_minimum. Home still
    # needs to see the same provisional row the repair sees.
    provisional = (
        structured.get('title_provenance') == 'server_minimum'
        or row.get('summary_title_provenance') == 'server_minimum'
    )
    empty_output = (
        home_empty_output_noise_enabled()
        and row.get('summary_blocked_reason') in EMPTY_BLOCKED_REASONS
        and not present(structured)
        # A banked receipt or live debt outranks a stale terminal reason: the
        # row recovered, or a late revision re-opened it.
        and not row.get('summary_output_present')
        and not row.get('summary_completed_at')
        and not summary_owed(row)
    )
    if is_completed_below_floor(row) or empty_output:
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
