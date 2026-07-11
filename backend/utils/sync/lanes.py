"""Authoritative fresh/backfill classification for Offline Sync uploads."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional

from utils.request_validation import parse_sync_filename_timestamp


class SyncLane(str, Enum):
    FRESH = 'fresh'
    BACKFILL = 'backfill'


class CaptureTimeTrust(str, Enum):
    DEVICE_BOUND = 'device_bound'
    LEGACY = 'legacy'
    UNTRUSTED = 'untrusted'


@dataclass(frozen=True)
class SyncLaneDecision:
    lane: SyncLane
    trust: CaptureTimeTrust
    reason: str
    oldest_capture_at: Optional[float]
    newest_capture_at: Optional[float]
    maximum_age_seconds: Optional[int]
    automatic_recovery_allowed: bool = True


def fresh_cutoff_seconds() -> int:
    return max(60, int(os.getenv('SYNC_FRESH_MAX_AGE_SECONDS', str(6 * 60 * 60))))


def maximum_backfill_age_seconds() -> int:
    return max(fresh_cutoff_seconds(), int(os.getenv('SYNC_BACKFILL_MAX_AGE_SECONDS', str(30 * 24 * 60 * 60))))


def maximum_future_skew_seconds() -> int:
    return max(0, int(os.getenv('SYNC_CAPTURE_MAX_FUTURE_SKEW_SECONDS', '300')))


def capture_times_within_window(filenames: Iterable[str], lower: float, upper: float) -> bool:
    try:
        capture_times = [float(parse_sync_filename_timestamp(filename)) for filename in filenames]
    except (IndexError, ValueError):
        return False
    return bool(capture_times) and all(lower <= capture_time <= upper for capture_time in capture_times)


def classify_sync_lane(
    filenames: Iterable[str],
    *,
    client_device_id: Optional[str],
    now: Optional[float] = None,
) -> SyncLaneDecision:
    """Classify a whole upload batch; mixed batches conservatively become backfill."""
    capture_times: list[float] = []
    for filename in filenames:
        try:
            capture_times.append(float(parse_sync_filename_timestamp(filename)))
        except (IndexError, ValueError):
            return SyncLaneDecision(
                lane=SyncLane.BACKFILL,
                trust=CaptureTimeTrust.UNTRUSTED,
                reason='invalid_capture_time',
                oldest_capture_at=None,
                newest_capture_at=None,
                maximum_age_seconds=None,
            )

    if not capture_times:
        return SyncLaneDecision(
            lane=SyncLane.BACKFILL,
            trust=CaptureTimeTrust.UNTRUSTED,
            reason='missing_capture_time',
            oldest_capture_at=None,
            newest_capture_at=None,
            maximum_age_seconds=None,
        )

    effective_now = time.time() if now is None else now
    oldest = min(capture_times)
    newest = max(capture_times)
    maximum_age = max(0, int(effective_now - oldest))
    trust = CaptureTimeTrust.DEVICE_BOUND if client_device_id else CaptureTimeTrust.LEGACY

    if newest > effective_now + maximum_future_skew_seconds():
        return SyncLaneDecision(
            lane=SyncLane.BACKFILL,
            trust=CaptureTimeTrust.UNTRUSTED,
            reason='future_capture_time',
            oldest_capture_at=oldest,
            newest_capture_at=newest,
            maximum_age_seconds=maximum_age,
        )

    if maximum_age > maximum_backfill_age_seconds():
        return SyncLaneDecision(
            lane=SyncLane.BACKFILL,
            trust=trust,
            reason='lookback_exceeded',
            oldest_capture_at=oldest,
            newest_capture_at=newest,
            maximum_age_seconds=maximum_age,
            automatic_recovery_allowed=False,
        )
    if not client_device_id:
        return SyncLaneDecision(
            lane=SyncLane.BACKFILL,
            trust=CaptureTimeTrust.LEGACY,
            reason='unbound_capture_time',
            oldest_capture_at=oldest,
            newest_capture_at=newest,
            maximum_age_seconds=maximum_age,
        )
    if maximum_age > fresh_cutoff_seconds():
        return SyncLaneDecision(
            lane=SyncLane.BACKFILL,
            trust=trust,
            reason='historical_capture',
            oldest_capture_at=oldest,
            newest_capture_at=newest,
            maximum_age_seconds=maximum_age,
        )
    return SyncLaneDecision(
        lane=SyncLane.FRESH,
        trust=trust,
        reason='recent_capture',
        oldest_capture_at=oldest,
        newest_capture_at=newest,
        maximum_age_seconds=maximum_age,
    )
