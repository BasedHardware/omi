"""Expired zero-content capture placeholders are noise only on the read wire.

Unlike an STT-empty receipt, this is not custody or lifecycle authority. A first
buffered frame sets received=True before any audio span commits, and that frame can
still commit at teardown, so a row whose received audio is not closed waits out the
full transcription age bound. A transcription deadline still in the future is live work. Keep the row and all
audio; any late content or active producer releases this presentation rule immediately.
"""

from datetime import datetime, timezone
from typing import Any, Mapping

from config.episodes import (
    home_step_projection_enabled,
    home_transcription_deadline_seconds,
    home_transcription_max_age_seconds,
)
from config.transcription_pending import stale_empty_noise_enabled
from utils.conversations.fragment_visibility import is_user_curated
from utils.conversations.home_titles import summary_owed
from utils.conversations.summary_delivery import present


def applies(row: Mapping[str, Any], *, now: datetime | None = None) -> bool:
    if not stale_empty_noise_enabled():
        return False
    if (
        row.get('status') != 'in_progress'
        or row.get('record_lane_owner') != 'batch_live_v1'
        or row.get('has_content') is not False
        or is_user_curated(row)
        or present(row.get('structured') or {})
        or str((row.get('structured') or {}).get('title') or '').strip()
        or summary_owed(row)
        or any(
            row.get(key)
            for key in (
                'transcript_segments',
                'record_projection_revision',
                'record_audio_partial',
                'record_upload_failed',
                'record_upload_sessions',
                'record_admitted_at',
                'home_transcription_queue_observed_at',
                'deleted',
                'discarded',
                'is_locked',
                'sync_merged_into',
                'summary_output_present',
                'summary_completed_at',
                'sync_content_revision',
            )
        )
        or any(row.get(key) is not None for key in ('server_batch_audio_start', 'server_batch_audio_end'))
        or row.get('finalization_status') == 'dead_letter'
    ):
        return False
    current = now or datetime.now(timezone.utc)
    for key in ('home_transcription_deadline_at', 'episode_transcription_deadline_at'):
        value = row.get(key)
        if isinstance(value, datetime):
            deadline = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
            if deadline > current:
                return False
    anchors: list[datetime] = []
    for key in ('home_transcription_pending_at', 'episode_transcription_pending_at'):
        value = row.get(key)
        if isinstance(value, datetime):
            anchors.append(value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value)
    if not anchors:
        return False
    # Both pending generations must be expired. A new wait is real work, not a
    # reason to keep hiding an old placeholder. Never use updated_at/read time.
    anchor = max(anchors)
    # Received audio that never closed may still commit at teardown: wait out the
    # full transcription age bound before calling it noise.
    open_audio = row.get('server_batch_audio_received') is True and row.get('server_batch_audio_closed') is not True
    bound = home_transcription_max_age_seconds() if open_audio else home_transcription_deadline_seconds()
    return (current - anchor).total_seconds() >= bound


def project(row: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    if not applies(row, now=now):
        return row
    return {
        **row,
        'status': 'completed',
        **({'home_step': 'noise'} if home_step_projection_enabled() else {}),
        'summary_retryable': False,
        'structured': {**(row.get('structured') or {}), 'title': 'No summary'},
    }
