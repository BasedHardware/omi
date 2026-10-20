from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional, TypedDict

from database import user_usage as user_usage_db


class _MetadataKwargs(TypedDict, total=False):
    usage_metadata: Mapping[str, Any]


def billable_transcription_seconds(
    last_usage_record_timestamp: Optional[float],
    last_audio_received_time: Optional[float],
    current_time: float,
    last_audio_resume_time: Optional[float] = None,
    held_seconds: Optional[Callable[[float, float], float]] = None,
) -> int:
    """Listening seconds to bill since the last usage record, clamped to the last
    audio byte actually received (#4700).

    Client keepalive pings hold the /v4/listen socket open long after the device
    stops sending audio; counting raw wall-clock time then accrues phantom
    listening minutes for hours. No audio streamed also means no STT vendor cost,
    so idle socket time must not be billed.

    `last_audio_resume_time` floors the window start: flushes that fired while
    no audio was arriving advance `last_usage_record_timestamp` through silence,
    so the first flush after audio resumes would otherwise bill the silent gap
    between that flush and the resume point (#15263).

    `held_seconds(start, end)` returns the wall-clock part of the window whose
    audio the STT cap held instead of transcribing; recovery meters it once.
    """
    if not last_usage_record_timestamp:
        return 0
    billable_from = last_usage_record_timestamp
    if last_audio_resume_time is not None and last_audio_resume_time > billable_from:
        billable_from = last_audio_resume_time
    billable_until = min(current_time, last_audio_received_time or current_time)
    held = held_seconds(billable_from, billable_until) if held_seconds is not None else 0
    return max(0, int(billable_until - billable_from - held))


def record_usage(
    uid: str,
    transcription_seconds: int = 0,
    words_transcribed: int = 0,
    insights_gained: int = 0,
    memories_created: int = 0,
    speech_seconds: int = 0,
    idempotency_key: Optional[str] = None,
    cost_usd: float | None = None,
    cost_status: str = 'missing',
    cost_exclusion: str | None = None,
    usage_metadata: Mapping[str, Any] | None = None,
):
    """Records hourly usage stats for a user."""
    now = datetime.now(timezone.utc)
    effective_cost_exclusion = cost_exclusion or ('provider_cost_not_recorded' if cost_status != 'complete' else None)
    updates = {
        'transcription_seconds': transcription_seconds,
        'words_transcribed': words_transcribed,
        'insights_gained': insights_gained,
        'memories_created': memories_created,
        'speech_seconds': speech_seconds,
    }
    metadata_kwargs: _MetadataKwargs = {'usage_metadata': usage_metadata} if usage_metadata is not None else {}
    if idempotency_key:
        user_usage_db.update_hourly_usage_once(
            uid,
            now,
            updates,
            idempotency_key,
            cost_usd=cost_usd,
            cost_status=cost_status,
            cost_exclusion=effective_cost_exclusion,
            **metadata_kwargs,
        )
    else:
        user_usage_db.update_hourly_usage(
            uid,
            now,
            updates,
            cost_usd=cost_usd,
            cost_status=cost_status,
            cost_exclusion=effective_cost_exclusion,
            **metadata_kwargs,
        )


def record_sync_v1_usage(uid: str, **usage: Any):
    """Sync v1's existing counters plus explicit managed-source provenance.

    Provider acceptance and successful-segment speech are not available here;
    the shadow projection is estimated and keeps that gap visible.
    """
    return record_usage(uid, **usage, usage_metadata={'funding': 'omi', 'provider': 'unknown', 'source': 'sync_v1'})
