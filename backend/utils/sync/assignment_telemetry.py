"""Fixed-cardinality metadata for sync assignment telemetry."""

from datetime import datetime
import math
from typing import Any, Optional

from utils.sync.live_overlap import compatible_capture

CREATED_UNKNOWN_REASONS = (
    'lookup_failed',
    'page_cap',
    'no_device',
    'extent_outside_incoming',
    'candidate_unread',
    'invalid_extent',
    'observation_error',
    'discovery_skipped',
    'not_recorded',
)


def created_sync_row_observation(
    rows: list[dict],
    result: dict,
    incoming: dict,
    *,
    lookup_complete: bool,
    lookup_incomplete_reason: str | None = None,
    candidates_read: bool = True,
) -> dict:
    """Describe a new row using only metadata already read by assignment.

    Empty live stubs count too: lack of transcript content is not proof that a
    row is absent. A positive overlap is a violation even on an incomplete read;
    only a complete lookup covering the committed extent can prove clear.
    """
    checked = 0
    overlap = False
    complete = False
    reasons: set[str] = set()
    try:
        if lookup_incomplete_reason in ('lookup_failed', 'page_cap', 'no_device', 'discovery_skipped'):
            reasons.add(lookup_incomplete_reason)
        has_device = bool(incoming.get('client_device_id'))
        complete = lookup_complete and has_device
        if not has_device:
            reasons.add('no_device')
        if not candidates_read:
            reasons.add('candidate_unread')
        start, end = _row_epoch(result['started_at']), _row_epoch(result['finished_at'])
        lo, hi = _row_epoch(incoming['started_at']), _row_epoch(incoming['finished_at'])
        if not all(map(math.isfinite, (start, end))) or end <= start:
            reasons.add('invalid_extent')
            raise ValueError('invalid new-row extent')
        if not all(map(math.isfinite, (lo, hi))) or not lo <= start < end <= hi:
            complete = False
            reasons.add('extent_outside_incoming')
        for row in rows:
            if (
                not compatible_capture(row, result)
                or row.get('deleted')
                or row.get('sync_merged_into')
                or row.get('status') not in ('completed', 'in_progress')
            ):
                continue
            # Ordinary sync writes always carry a content revision. Live rows
            # retain their identity after sync appends replace capture evidence.
            live = (
                not row.get('sync_content_revision')
                or row.get('sync_live_target')
                or (row.get('capture_evidence') or {}).get('origin') == 'live'
                or (row.get('external_data') or {}).get('recording_origin_id')
                or (row.get('external_data') or {}).get('recording_session_id')
            )
            if not live:
                continue
            checked += 1
            a, b = _row_epoch(row['started_at']), _row_epoch(row['finished_at'])
            if not all(map(math.isfinite, (a, b))) or b <= a:
                complete = False
                reasons.add('invalid_extent')
                continue
            overlap = overlap or min(b, end) > max(a, start)
    except Exception:  # inside the write transaction: telemetry must never abort it
        complete = False
        reasons.add('observation_error')
    bucket = (
        '0'
        if not checked
        else (
            '1'
            if checked == 1
            else '2_5' if checked <= 5 else '6_10' if checked <= 10 else '11_20' if checked <= 20 else 'gt_20'
        )
    )
    observation = {
        'outcome': 'created_overlap' if overlap else 'created_clear' if complete else 'created_unknown',
        'checked_live_candidates_bucket': bucket,
        'lookup_complete': complete,
    }
    if observation['outcome'] == 'created_unknown':
        observation['incomplete_reason'] = next(
            (reason for reason in CREATED_UNKNOWN_REASONS if reason in reasons), 'not_recorded'
        )
    return observation


def _row_epoch(value: Any) -> float:
    return value.timestamp() if isinstance(value, datetime) else float(value)


def lineage_span_delta_bucket(
    stamp_fallback: bool, live_target_id: Optional[str], current: Optional[dict], result: dict
) -> str:
    """Fixed extent-growth bucket for a stamp-fallback append to the explicit live row.

    Growth compares row ``started_at``/``finished_at`` only — never transcript
    sums, ids or text. A rollover elsewhere leaves the live extent unchanged,
    which is a zero growth, not a stretch of the new sync row.
    """
    if not stamp_fallback:
        return 'none'
    if not live_target_id:
        return 'unknown'
    if current is None or result.get('id') != live_target_id:
        return '0'
    try:
        grown_end = _row_epoch(result.get('finished_at'))
        grown_start = _row_epoch(result.get('started_at'))
        prior_end = _row_epoch(current.get('finished_at'))
        prior_start = _row_epoch(current.get('started_at'))
    except Exception:
        return 'unknown'
    endpoints = (grown_end, grown_start, prior_end, prior_start)
    if not all(map(math.isfinite, endpoints)) or grown_end < grown_start or prior_end < prior_start:
        return 'unknown'
    growth = (grown_end - grown_start) - (prior_end - prior_start)
    if growth <= 0:
        return '0'
    if growth <= 60:
        return '0_60'
    if growth <= 300:
        return '60_300'
    return 'gt_300'
