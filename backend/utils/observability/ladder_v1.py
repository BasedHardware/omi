"""Observed coverage gaps, per budget evaluation; never unique usage counters."""

from prometheus_client import REGISTRY, Histogram


def _histogram(name: str, description: str, buckets: tuple) -> Histogram:
    # Auth tests and development reloads can re-import this module while the
    # process-wide registry survives. Keep one collector rather than registering
    # the same series again; do not suppress unrelated registration failures.
    try:
        return Histogram(name, description, buckets=buckets)
    except ValueError:
        return REGISTRY._names_to_collectors[name]  # type: ignore[attr-defined]


UNPROJECTED_SECONDS = _histogram(
    'omi_ladder_unprojected_transcription_seconds',
    'Residual transcription seconds observed per ladder budget snapshot',
    buckets=(0, 1, 60, 600, 3600, 18000, 90000),
)
UNPROJECTED_ATTEMPTS = _histogram(
    'omi_ladder_unprojected_gateway_attempts',
    'Residual or unpriced gateway attempts observed per ladder budget snapshot',
    buckets=(0, 1, 10, 100, 1000, 10000),
)


def record_coverage(completeness: dict) -> None:
    UNPROJECTED_SECONDS.observe(completeness.get('unprojected_transcription_seconds', 0))
    UNPROJECTED_ATTEMPTS.observe(completeness.get('unprojected_gateway_attempts', 0))
