"""Closed episodes never wait for a capture that is still open."""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Mapping

from config.refactor_modes import default_on

MemberRevision = datetime | Literal['capturing'] | None
CAPTURING_REVISION = 'capturing'

EPISODE_LIVE_MEMBER_CLOSE_ENABLED_ENV = 'EPISODE_LIVE_MEMBER_CLOSE_ENABLED'


def enabled() -> bool:
    return default_on(EPISODE_LIVE_MEMBER_CLOSE_ENABLED_ENV)


def capturing(row: Mapping[str, Any]) -> bool:
    return bool(
        row.get('status') == 'in_progress'
        and (row.get('record_lane_owner') == 'batch_live_v1' or row.get('sync_live_target') is True)
        and not row.get('record_audio_closed')
        and not row.get('server_batch_audio_closed')
        and not any(
            row.get(k)
            for k in ('deleted', 'discarded', 'sync_merged_into', 'dream_duplicate_of', 'is_locked', 'deferred')
        )
    )


# Deliberately tighter than episode grouping gaps. These clocks must corroborate,
# rather than letting an arrival or recovered/estimated device clock move content.
CAPTURE_CLOCK_TOLERANCE_SECONDS = 5
CAPTURE_FUTURE_SKEW_SECONDS = 5


@dataclass(frozen=True)
class CaptureStart:
    lower: datetime | None = None
    upper: datetime | None = None
    refusal: str | None = None


def _utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def capture_start(row: Mapping[str, Any], *, now: datetime) -> CaptureStart:
    """Changing an owner requires all three trusted clocks to corroborate."""
    value = row.get('server_batch_audio_start')
    batch = None
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        try:
            batch = datetime.fromtimestamp(value, timezone.utc)
        except (OverflowError, OSError, ValueError):
            pass
    started, recorded = _utc(row.get('started_at')), _utc(row.get('recorded_start'))
    if started is None or recorded is None or batch is None:
        return CaptureStart(refusal='missing')
    if row.get('capture_time_trust') == 'untrusted' or row.get('clock') not in {'live_capture', 'frame', 'device'}:
        return CaptureStart(refusal='untrusted')
    clocks = [started, recorded, batch]
    lower, upper = min(clocks), max(clocks)
    if upper > now + timedelta(seconds=CAPTURE_FUTURE_SKEW_SECONDS):
        return CaptureStart(refusal='future')
    if (upper - lower).total_seconds() > CAPTURE_CLOCK_TOLERANCE_SECONDS:
        return CaptureStart(refusal='disagreement')
    return CaptureStart(lower=lower, upper=upper)
