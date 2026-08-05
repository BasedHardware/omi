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


def batch_clock_shift(
    windows: Iterable[tuple[float, float]],
    *,
    now: Optional[float] = None,
) -> float:
    """Shared positive clock skew for a sync batch (#4771).

    Independently shifting each window so its own end equals ``now`` collapses
    successive ~60s offline shards onto the same interval. Later shards then
    miss or dedupe-drop against the conversation created from earlier ones,
    which surfaces as many one-minute conversations dated at sync time.

    Use one shift — ``max(0, newest_end - now)`` — for every window in the
    batch so relative offsets and total duration survive.
    """
    effective_now = time.time() if now is None else float(now)
    newest_end: Optional[float] = None
    for _start, end in windows:
        end_f = float(end)
        if newest_end is None or end_f > newest_end:
            newest_end = end_f
    if newest_end is None:
        return 0.0
    return max(0.0, newest_end - effective_now)


def normalize_capture_window(
    start_ts: float,
    end_ts: float,
    *,
    now: Optional[float] = None,
    clock_shift: Optional[float] = None,
) -> tuple[float, float]:
    """Shift a capture window so it never ends after server now.

    Offline sync filenames embed the client wall clock. Mild positive skew
    (phone a few minutes ahead) previously produced conversations that appear
    in the future in the app (#4770). Preserve duration by shifting the whole
    window backward when the end is past ``now``.

    When ``clock_shift`` is provided (batch shared skew from
    :func:`batch_clock_shift`), apply that shift instead of per-window
    ``end - now`` so successive shards keep their relative spacing (#4771).
    """
    effective_now = time.time() if now is None else float(now)
    start = float(start_ts)
    end = float(end_ts)
    if clock_shift is None:
        if end <= effective_now:
            return start, end
        shift = end - effective_now
    else:
        shift = max(0.0, float(clock_shift))
        if shift == 0.0 and end <= effective_now:
            return start, end
    start -= shift
    end -= shift
    # Last shard can still overshoot ``now`` by its own duration when the shared
    # shift was estimated from starts only; keep a hard end clamp.
    if end > effective_now:
        extra = end - effective_now
        start -= extra
        end -= extra
    return start, end


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
