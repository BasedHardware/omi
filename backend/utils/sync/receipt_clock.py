"""Future-only receipt placement; existing early-clock intake never enters here."""

import hashlib
import json
import math
from time import time

from fastapi import HTTPException

from database.sync_capture_clock import CaptureClockRangeError, account_created_at, frozen_offset
from utils.sync.capture_clock import (
    INVALID_CAPTURE_TIME_CODE,
    INVALID_CAPTURE_TIME_DETAIL,
    is_implausible_future_capture_time,
)
from utils.sync.clock_run import capture_clock_run_from_path
from utils.sync.files import get_timestamp_from_path

POLICY = 'future_device_offset_v1'
ESTIMATED_POLICY = 'estimated_source_isolated_v1'


class FutureCaptureRefused(HTTPException):
    def __init__(self):
        super().__init__(400, detail={'code': INVALID_CAPTURE_TIME_CODE, 'detail': INVALID_CAPTURE_TIME_DETAIL})


class FutureCaptureRetry(HTTPException):
    def __init__(self, code: str = 'capture_clock_anchor_unavailable'):
        super().__init__(
            503, detail={'code': code, 'detail': 'Retain local audio and retry'}, headers={'Retry-After': '30'}
        )


def require_future_upload(paths: list[str], *, received_at: float) -> None:
    # Unmarked files get independent receipt anchors, never an inferred run.
    if not paths or any(
        not is_implausible_future_capture_time(get_timestamp_from_path(path), now=received_at) for path in paths
    ):
        raise FutureCaptureRefused()


def clock_scope(path: str, device_id: str) -> str:
    run = capture_clock_run_from_path(path)
    if not run:
        raise FutureCaptureRefused()
    return hashlib.sha256(json.dumps([device_id, run], separators=(',', ':')).encode()).hexdigest()


def receipt_clock_offsets(
    spans: list[tuple[str, float, float]],
    *,
    uid: str,
    device_id: str | None,
    received_at: float,
    source_ids: dict[str, str] | None = None,
    retained_offsets: dict[str, float] | None = None,
) -> dict[str, float]:
    """Freeze decoded-end offsets before staging or acknowledging any unit."""
    if not uid or not math.isfinite(received_at):
        raise FutureCaptureRetry('capture_clock_identity_required')
    if not spans:
        raise FutureCaptureRefused()
    new_paths = [path for path, _, _ in spans if path not in (retained_offsets or {})]
    if new_paths:
        require_future_upload(new_paths, received_at=received_at)
    groups: dict[str, list[tuple[str, float, float]]] = {}
    for path, start, duration in spans:
        if not all(math.isfinite(value) for value in (start, duration)) or duration <= 0:
            raise FutureCaptureRefused()
        if capture_clock_run_from_path(path):
            if not device_id:
                raise FutureCaptureRetry('capture_clock_identity_required')
            scope = clock_scope(path, device_id)
        else:
            # Existing owner-keyed canonical content identity, independent of
            # request directory, upload order, other files and claimed clock.
            source_id = (source_ids or {}).get(path)
            if not source_id:
                raise FutureCaptureRetry('capture_clock_identity_required')
            scope = hashlib.sha256(f'file:{source_id}'.encode()).hexdigest()
        groups.setdefault(scope, []).append((path, start, duration))
    try:
        lower_bound = account_created_at(uid)
        offsets = {}
        for scope, members in groups.items():
            raw_end = max(start + duration for _, start, duration in members)
            offset = frozen_offset(
                uid,
                scope,
                raw_end,
                received_at,
                raw_start=min(start for _, start, _ in members),
                lower_bound=lower_bound,
            )
            # Never slide an admitted run. A future mapped interval waits for
            # trusted processing time; a reused/discontinuous clock is refused.
            ahead = raw_end - offset - max(received_at, time())
            if ahead > 24 * 60 * 60:
                raise FutureCaptureRefused()
            if ahead > 0.000001:
                raise FutureCaptureRetry('capture_clock_anchor_pending')
            offsets.update({path: offset for path, _, _ in members})
        return offsets
    except CaptureClockRangeError as error:
        raise FutureCaptureRefused() from error
    except HTTPException:
        raise
    except Exception as error:
        # Includes exhausted Firestore transaction retries. No alternate
        # offset or successful acknowledgement can escape a failed anchor.
        raise FutureCaptureRetry() from error


def retained_source_offsets(
    paths: list[str], *, uid: str, device_id: str | None, received_at: float
) -> dict[str, float]:
    """Reclassification can never erase an already admitted owner/source anchor."""
    from database.sync_capture_clock import retained_offsets
    from utils.sync.capture_clock import is_early_capture_time
    from utils.sync.content_id import compute_sync_content_id

    scopes = {}
    for path in paths:
        stamp = get_timestamp_from_path(path)
        if is_early_capture_time(stamp) or is_implausible_future_capture_time(stamp, now=received_at):
            continue
        if capture_clock_run_from_path(path):
            if not device_id:
                continue
            scopes[path] = clock_scope(path, device_id)
        else:
            source_id = compute_sync_content_id(uid, [path])
            scopes[path] = hashlib.sha256(f'file:{source_id}'.encode()).hexdigest()
    from utils.sync.input_limits import MAX_BACKFILL_FILES

    if len(set(scopes.values())) > MAX_BACKFILL_FILES:
        raise FutureCaptureRetry()
    try:
        offsets = retained_offsets(uid, list(scopes.values()))
        return {path: offsets[scope] for path, scope in scopes.items() if scope in offsets}
    except Exception as error:
        # An unavailable provenance read cannot turn accepted unknown time into
        # trusted time or authorize a second conversation in a different bundle.
        raise FutureCaptureRetry() from error
