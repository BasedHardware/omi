"""Shared capture-clock policy for sync upload admission.

Phone live-capture files are named after the START of the audio they hold
(app ``Wal.getFileNameByTimeStarts`` and ``MobileBatchBuffer.append``), so a
filename timestamp ahead of the server clock is phone-clock skew, not a
naming-semantics mismatch. Every admission check tolerates that skew through
the one bound owned here; stored/derived capture times clamp to server now so
skew can never break ordering or windows. Clearly broken early/future clocks
use receipt-clock placement with raw identity and explicit untrusted time.
Only the future batch extension uses ``receipt_clock``. Existing early-clock
placement and persisted documents remain unchanged.

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
# syncing. Broken device stamps stay outside that trusted skew window and use
# the separately gated receipt-clock recovery policy below.
from config.recorded_time_tolerances import CLOCK_SKEW_SECONDS as DEFAULT_MAX_FUTURE_SKEW_SECONDS

EARLIEST_CAPTURE_TIME = datetime(2024, 1, 1, tzinfo=timezone.utc)
CAPTURE_TIME_TRUST_FIELD = 'capture_time_trust'

INVALID_CAPTURE_TIME_CODE = 'invalid_capture_time'
INVALID_CAPTURE_TIME_DETAIL = 'Invalid sync file format: invalid timestamp'


def maximum_future_skew_seconds() -> int:
    """How far ahead of the server clock an upload capture time may be."""
    return max(0, int(os.getenv('SYNC_CAPTURE_MAX_FUTURE_SKEW_SECONDS', str(DEFAULT_MAX_FUTURE_SKEW_SECONDS))))


def early_capture_clamp_enabled() -> bool:
    return os.getenv('SYNC_EARLY_CAPTURE_CLAMP_ENABLED', 'true').lower() != 'false'


def is_early_capture_time(capture_time: float) -> bool:
    return capture_time < EARLIEST_CAPTURE_TIME.timestamp()


def future_capture_clamp_enabled() -> bool:
    return os.getenv('SYNC_FUTURE_CAPTURE_CLAMP_ENABLED', 'false').strip().lower() in ('true', '1', 'on', 'yes')


def is_implausible_future_capture_time(capture_time: float, *, now: float | None = None) -> bool:
    effective_now = time.time() if now is None else now
    return capture_time > effective_now + 24 * 60 * 60


def is_receipt_clock_capture_time(capture_time: float, *, now: float | None = None) -> bool:
    """Clock policy for admitted work, independent of admission kill switches.

    Pass the frozen receive time, never worker time: a queued future stamp must
    stay untrusted even if the wall clock catches up before it is processed.
    """
    return is_early_capture_time(capture_time) or is_implausible_future_capture_time(capture_time, now=now)


def early_capture_clock_offsets(
    spans: list[tuple[str, float, float]], *, now: float, source_starts: dict[str, float] | None = None
) -> dict[str, float]:
    """Place admitted reset-clock audio in raw order, ending at receipt time.

    Invalid clocks prove order, not wall-clock gaps (two resets can be years
    apart). Pack their durations together; keep raw keys and normal clocks.
    Already accepted work keeps this policy after admission is switched off.
    Source stamps order files; derivative stamps order pieces within a file.
    """
    # The caller marks source files: a derived segment can cross the 2024
    # boundary and must still inherit its original file's reset clock.
    early = sorted(spans, key=lambda span: ((source_starts or {}).get(span[0], span[1]), span[1], span[0]))
    cursor = now - sum(duration for _, _, duration in early)
    offsets = {}
    for key, capture, duration in early:
        offsets[key] = capture - cursor
        cursor += duration
    return offsets


def capture_time_rejection(
    capture_time: datetime,
    *,
    now: Optional[datetime] = None,
    future_skew_seconds: Optional[int] = None,
    allow_early_clamp: bool = True,
) -> Optional[SyncCaptureTimeReason]:
    """The closed rejection reason for an implausible capture time, else ``None``.

    Pre-2024 and beyond-tolerance future stamps use receipt-clock recovery under
    their respective admission switches. Within-tolerance times retain skew
    normalization. Explicit ``future_skew_seconds`` callers never recover a
    future clock: their downstream paths cannot consume a receipt anchor.
    ``future_skew_seconds`` overrides the shared tolerance for callers that
    keep a stricter pre-skew-admission contract (v1 staging rejects any
    future time because nothing downstream of it normalizes skew).
    """
    effective_now = datetime.now(timezone.utc) if now is None else now
    tolerance = maximum_future_skew_seconds() if future_skew_seconds is None else max(0, int(future_skew_seconds))
    if capture_time < EARLIEST_CAPTURE_TIME and not (allow_early_clamp and early_capture_clamp_enabled()):
        return SyncCaptureTimeReason.REJECTED_EARLY
    if capture_time > effective_now + timedelta(seconds=tolerance):
        if (
            future_skew_seconds is None
            and future_capture_clamp_enabled()
            and is_implausible_future_capture_time(capture_time.timestamp(), now=effective_now.timestamp())
        ):
            return None
        return SyncCaptureTimeReason.REJECTED_FUTURE
    return None


def clamp_capture_time(capture_time: float, *, now: Optional[float] = None, allow_early_clamp: bool = True) -> float:
    """Clamp an untrustworthy early or within-tolerance future stored time.

    Identity callers retain raw times. Multi-file callers shift early spans
    together with ``early_capture_clock_offsets`` to preserve duration/order.
    Callers that already applied that admission offset can future-bound only
    with ``allow_early_clamp=False``; unadmitted legacy clock scopes stay intact.
    """
    effective_now = time.time() if now is None else now
    if allow_early_clamp and is_early_capture_time(capture_time) and early_capture_clamp_enabled():
        return effective_now
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
    """Filename capture-window violation, carrying the closed reason."""

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
