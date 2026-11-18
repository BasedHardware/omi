"""Closed-vocabulary v3 recording rotation outcomes; never account labels."""

from prometheus_client import Counter

OUTCOMES = ('rotated', 'same_row', 'create_failed', 'seal_failed', 'seal_retry', 'handed_off')
V3_ROTATION_TOTAL = Counter(
    'omi_listen_v3_rotation_total',
    'Listen v3 recording rotations by outcome; handed_off rows are left to their armed quiet check',
    ['outcome'],
)
for _outcome in OUTCOMES:
    V3_ROTATION_TOTAL.labels(outcome=_outcome)


def record_rotation(outcome: str) -> None:
    V3_ROTATION_TOTAL.labels(outcome=outcome if outcome in OUTCOMES else 'seal_failed').inc()
