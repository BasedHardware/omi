"""Closed episodes never wait for a capture that is still open."""

import math
from datetime import datetime, timezone
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


def capture_start(row: Mapping[str, Any]) -> datetime | None:
    value = row.get('server_batch_audio_start')
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        try:
            return datetime.fromtimestamp(value, timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    value = row.get('started_at')
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return None
