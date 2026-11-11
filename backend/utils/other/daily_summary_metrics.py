"""Bounded daily-recap job telemetry, without the API metrics dependency graph."""

from typing import cast

from prometheus_client import Counter, Gauge, REGISTRY, disable_created_metrics

# Match utils.metrics: created timestamps are not application signals.
disable_created_metrics()


def _collector(
    kind: type[Counter] | type[Gauge], name: str, description: str, labels: tuple[str, ...] = ()
) -> Counter | Gauge:
    try:
        return kind(name, description, labels)
    except ValueError:
        # Fresh-module test imports and runtime reloads share the default registry.
        return getattr(REGISTRY, '_names_to_collectors')[name]


RECIPIENTS = cast(
    Counter,
    _collector(
        Counter, 'omi_daily_summary_recipients_total', 'Daily recap recipient outcomes per cohort pass.', ('outcome',)
    ),
)
COHORT_COMPLETE = cast(
    Counter,
    _collector(Counter, 'omi_daily_summary_cohort_complete_total', 'Daily recap cohort pass completion.', ('outcome',)),
)
RESUMED_COHORT_AGE = cast(
    Gauge,
    _collector(
        Gauge,
        'omi_daily_summary_resumed_cohort_age_seconds',
        'Age of the saved cohort observed at the start of this tick, before age-out.',
    ),
)

RECIPIENT_OUTCOMES = (
    'selected',
    'generated',
    'generated_retry',
    'failed',
    'timed_out',
    'skipped_budget',
    'suppressed_existing',
)
for _outcome in RECIPIENT_OUTCOMES:
    RECIPIENTS.labels(outcome=_outcome)
for _outcome in ('complete', 'incomplete'):
    COHORT_COMPLETE.labels(outcome=_outcome)


REFRESH_OUTCOMES = (
    'adopted_fresh',
    'adopted_stale_scheduled',
    'refreshed',
    'refresh_skipped_cap',
    'refresh_skipped_unchanged',
    'refresh_conflict',
)
REFRESH = cast(
    Counter, _collector(Counter, 'omi_daily_summary_late_refresh_total', 'Legacy recap refresh outcomes.', ('outcome',))
)


def bounded_refresh_outcome(outcome: str) -> str:
    """Return one of the six refresh labels; reject identities/free text."""
    if outcome not in REFRESH_OUTCOMES:
        raise ValueError('unknown daily recap refresh outcome')
    return outcome


for _outcome in REFRESH_OUTCOMES:
    REFRESH.labels(outcome=bounded_refresh_outcome(_outcome))


def refresh(outcome: str) -> None:
    REFRESH.labels(outcome=bounded_refresh_outcome(outcome)).inc()
