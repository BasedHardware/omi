"""Content-free, bounded diagnostics for the pre-STT proof matcher."""

from prometheus_client import Counter

COVERAGE = Counter('omi_sync_wal_audio_coverage_total', 'Pre-STT WAL coverage decisions', ['outcome', 'reason'])
REASONS = frozenset({'none', 'unparseable', 'degraded', 'truncated', 'overflow', 'evidence', 'geometry', 'error'})


def bounded_reason(reason: object) -> str:
    return reason if isinstance(reason, str) and reason in REASONS else 'other'


def record_coverage_outcome(status: object, reason: object) -> None:
    COVERAGE.labels(
        outcome=status if isinstance(status, str) and status in {'applied', 'abstained'} else 'other',
        reason=bounded_reason(reason),
    ).inc()
