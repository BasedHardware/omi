"""Default-off batch admission cohort. Existing lane classification stays upstream."""

from enum import IntEnum
import hashlib
import math
import os
from typing import Callable, TypeVar


class Priority(IntEnum):
    FRESH = 0
    RECENT = 1
    DEEP = 2


T = TypeVar('T')


def enabled_for(owner_id: str) -> bool:
    if os.getenv('BATCH_PIPELINE_ENABLED', 'false').lower() != 'true':
        return False
    try:
        percent = float(os.getenv('BATCH_PIPELINE_PERCENT', '0'))
    except ValueError:
        return False
    if not math.isfinite(percent) or not 0 <= percent <= 100:
        return False
    owners = {value.strip() for value in os.getenv('BATCH_PIPELINE_UID_ALLOWLIST', '').split(',') if value.strip()}
    bucket = int.from_bytes(hashlib.sha256(owner_id.encode()).digest()[:4], 'big') / 2**32 * 100
    return owner_id in owners or bucket < percent


def priority_for(lane: str, recording_age_seconds: float | None) -> Priority:
    if lane == 'fresh':
        return Priority.FRESH
    if lane != 'backfill':
        raise ValueError('unclassified sync lane')
    if (
        recording_age_seconds is not None
        and math.isfinite(recording_age_seconds)
        and 0 <= recording_age_seconds <= 604800
    ):
        return Priority.RECENT
    return Priority.DEEP


def admit_or_legacy(owner_id: str, admit: Callable[..., T], legacy: Callable[..., T], *args, **kwargs) -> T:
    """Explicit integration seam; disabled path does not evaluate admission/store."""
    return (admit if enabled_for(owner_id) else legacy)(*args, **kwargs)


def shared_live_enabled() -> bool:
    return os.getenv('BATCH_PIPELINE_SHARED_LIVE_ENABLED', 'false').lower() == 'true'


SCHEDULER_SHARDS = 64


def scheduler_control_key(hashed_owner: str) -> str:
    """Pure shard identity shared by scheduling and privacy cleanup."""
    return f'scheduler_{int(hashed_owner[:8], 16) % SCHEDULER_SHARDS:02d}'


def max_worker_attempts() -> int:
    """Bound charged worker failures; malformed configuration keeps the safe default."""
    try:
        value = int(os.getenv('BATCH_PIPELINE_MAX_ATTEMPTS', '5'))
    except ValueError:
        return 5
    return value if 1 <= value <= 20 else 5


def recovery_owners() -> tuple[str, ...]:
    """Recovery is independent of admission; empty allowlist always denies."""
    if os.getenv('BATCH_PIPELINE_RECOVERY_MODE', 'off').strip().lower() != 'on':
        return ()
    return tuple(
        sorted(
            {
                value.strip()
                for value in os.getenv('BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST', '').split(',')
                if value.strip() and '/' not in value.strip() and len(value.strip().encode()) <= 256
            }
        )
    )
