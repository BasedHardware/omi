"""Cross-request placement of admitted untrusted audio without changing identity.

A frozen affine offset retains the device clock's order and gaps. It never
slides after a later request; an interval ahead of trusted server time waits.
"""

import hashlib
import json
import math
from time import time

from fastapi import HTTPException

from database.sync_capture_clock import frozen_offset
from utils.sync.capture_clock import is_early_capture_time
from utils.sync.clock_run import capture_clock_run_from_path

POLICY = 'device_offset_v1'


def clock_scope(path: str, origin: float, device_id: str) -> str:
    identity = [device_id, capture_clock_run_from_path(path), 'early' if is_early_capture_time(origin) else 'future']
    return hashlib.sha256(json.dumps(identity, separators=(',', ':')).encode()).hexdigest()


def inherited_offsets(spans, *, scope_offsets, device_id, source_starts=None, source_paths=None):
    """Derived/VAD spans inherit the original decoded file's immutable offset."""
    return {
        key: scope_offsets[
            clock_scope((source_paths or {}).get(key, key), (source_starts or {}).get(key, start), device_id)
        ]
        for key, start, _ in spans
    }


def receipt_clock_offsets(
    spans: list[tuple[str, float, float]],
    *,
    uid: str,
    device_id: str,
    received_at: float,
    source_starts: dict[str, float] | None = None,
    source_paths: dict[str, str] | None = None,
) -> dict[str, float]:
    """Resolve once per original decoded clock run, before coverage/VAD trim."""
    if not uid or not device_id or not math.isfinite(received_at):
        raise HTTPException(status_code=503, detail='capture_clock_identity_required')
    groups: dict[str, list[tuple[str, float, float]]] = {}
    for key, start, duration in spans:
        if not all(math.isfinite(value) for value in (start, duration)) or duration <= 0:
            raise ValueError('invalid decoded capture-clock span')
        origin = (source_starts or {}).get(key, start)
        scope = clock_scope((source_paths or {}).get(key, key), origin, device_id)
        groups.setdefault(scope, []).append((key, start, duration))
    offsets = {}
    # Receipt creates the immutable anchor. Processing time only releases a
    # deferred interval when due; replaying its frozen receipt must not wedge it.
    trusted_now = max(received_at, time())
    for scope, members in groups.items():
        raw_end = max(start + duration for _, start, duration in members)
        offset = frozen_offset(uid, scope, raw_end, received_at)
        if raw_end - offset > trusted_now + 0.000001 or min(start - offset for _, start, _ in members) < 0:
            # Re-clamping one request would reverse/overlap earlier intervals.
            # Keep all custody and retry when the immutable mapping is due.
            raise HTTPException(status_code=503, detail='capture_clock_anchor_pending')
        offsets.update({key: offset for key, _, _ in members})
    return offsets
