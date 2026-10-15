"""Finalize-attempt accounting; receipt coverage is never inferred from text.

Mapped means positions were mapped, not that an entire meeting was recorded.
Only anchored receipt runs can measure wall coverage. Legacy and sync receipts
without wall anchors remain explicitly unmeasurable. Retries/reprocesses count
as attempts, not unique conversations; no persisted schema is changed.
"""

from datetime import datetime, timezone
from typing import Any
import math
from prometheus_client import Counter
from pydantic import BaseModel

CAPTURE_FINALIZED_TOTAL = Counter(
    'omi_capture_finalized_total',
    'Persisted finalization attempts by receipt coverage and measurability.',
    ['coverage', 'span_measurement'],
)
CAPTURE_FINALIZED_SECONDS = Counter(
    'omi_capture_finalized_seconds_total',
    'Covered and conversation wall-span seconds on finalization attempts.',
    ['coverage', 'span_measurement', 'span'],
)


def _timestamp(value: Any) -> float | None:
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc).timestamp() if value.tzinfo is None else value.timestamp()


def coverage_accounting(conversation: Any) -> tuple[str, float | None, float | None]:
    evidence = getattr(conversation, 'capture_evidence', None)
    if isinstance(evidence, BaseModel):
        evidence = evidence.model_dump()
    evidence = evidence if isinstance(evidence, dict) else {}
    coverage = evidence.get('coverage')
    coverage = coverage if coverage in {'incomplete', 'mapped', 'unknown'} else 'unknown'
    start = _timestamp(getattr(conversation, 'started_at', None))
    end = _timestamp(getattr(conversation, 'finished_at', None))
    if start is None or end is None or end <= start:
        return coverage, None, None
    runs = evidence.get('runs')
    if not isinstance(runs, list) or not runs:
        return coverage, end - start, None
    spans = []
    for run in runs:
        if not isinstance(run, dict):
            return coverage, end - start, None
        low, high = run.get('receipt_wall_start'), run.get('receipt_wall_end')
        low_ok = type(low) in (int, float)
        high_ok = type(high) in (int, float)
        if not low_ok or not high_ok:
            return coverage, end - start, None
        low_f: float = float(low)  # type: ignore[arg-type]
        high_f: float = float(high)  # type: ignore[arg-type]
        if not math.isfinite(low_f) or not math.isfinite(high_f) or high_f <= low_f:
            return coverage, end - start, None
        low, high = max(start, low_f), min(end, high_f)
        if high > low:
            spans.append((low, high))
    covered = 0.0
    cursor = start
    for low, high in sorted(spans):
        covered += max(0.0, high - max(cursor, low))
        cursor = max(cursor, high)
    return coverage, end - start, covered


def record_capture_loss(conversation: Any) -> None:
    """Best-effort metrics, called only after persistence accepted the result."""
    try:
        coverage, span, covered = coverage_accounting(conversation)
        measurement = 'known' if covered is not None else 'unknown'
        CAPTURE_FINALIZED_TOTAL.labels(coverage=coverage, span_measurement=measurement).inc()
        if span is not None:
            CAPTURE_FINALIZED_SECONDS.labels(coverage=coverage, span_measurement=measurement, span='conversation').inc(
                span
            )
        if covered is not None:
            CAPTURE_FINALIZED_SECONDS.labels(coverage=coverage, span_measurement=measurement, span='covered').inc(
                covered
            )
    except Exception:
        # Metrics must not abort finalization or its derived work.
        pass
