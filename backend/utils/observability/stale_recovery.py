"""Closed-vocabulary reconnect recovery outcomes; never account/content labels."""

from prometheus_client import Counter

from utils.observability.reasons import ReasonFamily, StaleRecoveryOutcome, reason_label

OUTCOMES = tuple(outcome.value for outcome in StaleRecoveryOutcome)
STALE_RECOVERY_OUTCOME_TOTAL = Counter(
    'omi_stale_recovery_outcome_total',
    'Stale reconnect recovery attempts by disposition; accepted means handoff or empty deletion, not completion',
    ['outcome'],
)
for _outcome in OUTCOMES:
    STALE_RECOVERY_OUTCOME_TOTAL.labels(
        outcome=reason_label(ReasonFamily.STALE_RECOVERY, _outcome, StaleRecoveryOutcome)
    )


def record_stale_recovery_outcome(outcome: str) -> None:
    STALE_RECOVERY_OUTCOME_TOTAL.labels(
        outcome=reason_label(ReasonFamily.STALE_RECOVERY, outcome, StaleRecoveryOutcome)
    ).inc()
