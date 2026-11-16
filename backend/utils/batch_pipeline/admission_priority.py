"""Per-unit scheduling urgency; request lane and capture trust stay authoritative."""

import math

from config.batch_pipeline import (
    FRESH_CAPTURE_LAG_SECONDS,
    Priority,
    priority_for,
    unit_capture_priority_enabled,
)
from utils.metrics import OMI_BATCH_PIPELINE_PRIORITY_DEMOTIONS_TOTAL


def unit_priority(seed_priority, lane, unit, *, now):
    capture_at = getattr(unit, 'stored_capture_at', None)
    if capture_at is None:
        capture_at = unit.capture_at
    duration = unit.duration_seconds or 0
    if (
        any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            for value in (capture_at, duration)
        )
        or duration < 0
        or getattr(unit, 'recovery_id', None)
    ):
        return seed_priority
    age = max(0.0, now - capture_at - duration)
    effective = seed_priority
    if unit_capture_priority_enabled():
        # Lower enum values are fresher: min can only PROMOTE, never demote a seed.
        # Preserve the request lane, including the unbound_capture_time trust gate.
        effective = min(seed_priority, priority_for(lane, age))
    reasons = []
    if effective != seed_priority:
        reasons.append('seed_effective_divergence')
    if age <= FRESH_CAPTURE_LAG_SECONDS and effective != Priority.FRESH:
        reasons.append('fresh_capture_not_fresh')
    for reason in reasons:
        try:
            OMI_BATCH_PIPELINE_PRIORITY_DEMOTIONS_TOTAL.labels(lane=lane, reason=reason).inc()
        except Exception:
            pass  # Telemetry must never refuse admission.
    return effective
