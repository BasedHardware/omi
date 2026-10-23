"""Fixed-cardinality metadata for sync assignment telemetry."""

from datetime import datetime
import math
from typing import Any, Optional


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
