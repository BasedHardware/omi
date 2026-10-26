"""Shared capture-clock policy for sync upload admission.

Phone live-capture files are named after the START of the audio they hold
(app ``Wal.getFileNameByTimeStarts`` and ``MobileBatchBuffer.append``), so a
filename timestamp ahead of the server clock is phone-clock skew, not a
naming-semantics mismatch. Every admission check tolerates that skew through
the one bound owned here; stored/derived capture times clamp to server now so
skew can never break ordering or windows.

Keep this module import-light: ``utils.request_validation`` imports it.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

from utils.observability.reasons import SyncCaptureTimeReason

# Prod (24h to 2026-10-26): real phone live-capture uploads ran a median 171 s
# and max 349 s ahead of the server clock. The default doubles a bit past that
# max — uncalibrated phone clocks drift minutes, so one outlier phone must keep
# syncing — while bogus device stamps (2030+) stay ~years outside and accepted
# times are clamped to now anyway, so the wider bound costs nothing downstream.
DEFAULT_MAX_FUTURE_SKEW_SECONDS = 600

EARLIEST_CAPTURE_TIME = datetime(2024, 1, 1, tzinfo=timezone.utc)

INVALID_CAPTURE_TIME_CODE = 'invalid_capture_time'
INVALID_CAPTURE_TIME_DETAIL = 'Invalid sync file format: invalid timestamp'


def maximum_future_skew_seconds() -> int:
    """How far ahead of the server clock an upload capture time may be."""
    return max(0, int(os.getenv('SYNC_CAPTURE_MAX_FUTURE_SKEW_SECONDS', str(DEFAULT_MAX_FUTURE_SKEW_SECONDS))))


def capture_time_rejection(
    capture_time: datetime, *, now: Optional[datetime] = None, future_skew_seconds: Optional[int] = None
) -> Optional[SyncCaptureTimeReason]:
    """The closed rejection reason for an implausible capture time, else ``None``.

    ``rejected_early`` covers pre-2024 stamps (bogus SD-card markers); times
    further ahead of server now than the shared skew tolerance are
    ``rejected_future``. Within-tolerance future times are admissible skew.
    ``future_skew_seconds`` overrides the shared tolerance for callers that
    keep a stricter pre-skew-admission contract (v1 staging rejects any
    future time because nothing downstream of it normalizes skew).
    """
    effective_now = datetime.now(timezone.utc) if now is None else now
    tolerance = maximum_future_skew_seconds() if future_skew_seconds is None else max(0, int(future_skew_seconds))
    if capture_time < EARLIEST_CAPTURE_TIME:
        return SyncCaptureTimeReason.REJECTED_EARLY
    if capture_time > effective_now + timedelta(seconds=tolerance):
        return SyncCaptureTimeReason.REJECTED_FUTURE
    return None


def clamp_capture_time(capture_time: float, *, now: Optional[float] = None) -> float:
    """Clamp a within-tolerance future capture time to server now.

    Only future times move, so retry identities keyed on past capture times
    stay stable; callers that mint stored/ordered times clamp so a skewed phone
    clock cannot land them in the future.
    """
    effective_now = time.time() if now is None else now
    return min(capture_time, effective_now)


def capture_clock_offset(max_file_end: float, *, now: Optional[float] = None) -> float:
    """The one server-clock normalization offset for an accepted request.

    ``max_file_end`` is the furthest file end the request claims, on the
    capture (phone) clock; subtracting the returned offset moves the whole
    request onto the server clock with its newest audio ending at ``now``.
    Requests whose clock is behind the server (or on time) get 0. Temporal
    comparisons against server-clock rows use shifted times; capture-time
    identity, chunk and lineage keys keep the raw filename times.
    """
    effective_now = time.time() if now is None else now
    return max(0.0, max_file_end - effective_now)


class CaptureTimeWindowError(ValueError):
    """``parse_sync_filename_timestamp`` window violation, carrying the closed reason."""

    def __init__(self, reason: SyncCaptureTimeReason):
        super().__init__('invalid timestamp')
        self.capture_time_reason = reason


class SyncCaptureTimeRejected(HTTPException):
    """Typed v2 400 for an inadmissible capture-time filename.

    Subclasses ``HTTPException`` with the legacy detail so an uncaught raise
    degrades to today's wire body; the v2 route catches it to add ``code``.
    """

    def __init__(self):
        super().__init__(status_code=400, detail=INVALID_CAPTURE_TIME_DETAIL)
