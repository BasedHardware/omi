"""Content-free, bounded diagnostics for the pre-STT proof matcher."""

from typing import Any

from prometheus_client import REGISTRY, Counter


def _shared_counter(name: str, doc: str, labels: list[str]) -> Any:
    # Import-isolation harnesses re-execute this module against stubbed peers;
    # the default REGISTRY is process-global, so reuse the live collector
    # instead of raising Duplicated timeseries on the second exec.
    try:
        return Counter(name, doc, labels)
    except ValueError:
        return REGISTRY._names_to_collectors[name]  # type: ignore[return-value, index]


COVERAGE: Any = _shared_counter(
    'omi_sync_wal_audio_coverage_total', 'Pre-STT WAL coverage decisions', ['outcome', 'reason']
)
REASONS = frozenset({'none', 'unparseable', 'degraded', 'truncated', 'overflow', 'evidence', 'geometry', 'error'})


def bounded_reason(reason: object) -> str:
    return reason if isinstance(reason, str) and reason in REASONS else 'other'


def record_coverage_outcome(status: object, reason: object) -> None:
    COVERAGE.labels(
        outcome=status if isinstance(status, str) and status in {'applied', 'abstained'} else 'other',
        reason=bounded_reason(reason),
    ).inc()
