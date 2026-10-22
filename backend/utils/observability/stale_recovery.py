"""Closed-vocabulary reconnect recovery outcomes; never account/content labels."""

from prometheus_client import Counter

OUTCOMES = ('accepted', 'not_admitted', 'error', 'oversized_close_attempted', 'current_session', 'cancelled')
STALE_RECOVERY_OUTCOME_TOTAL = Counter(
    'omi_stale_recovery_outcome_total',
    'Stale reconnect recovery attempts by disposition; accepted means handoff or empty deletion, not completion',
    ['outcome'],
)
for _outcome in OUTCOMES:
    STALE_RECOVERY_OUTCOME_TOTAL.labels(outcome=_outcome)


def record_stale_recovery_outcome(outcome: str) -> None:
    STALE_RECOVERY_OUTCOME_TOTAL.labels(outcome=outcome if outcome in OUTCOMES else 'error').inc()
