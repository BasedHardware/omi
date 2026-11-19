"""Closed-vocabulary v3 recording rotation outcomes; never account labels."""

from prometheus_client import Counter

from utils.observability.reasons import ReasonFamily, RecordingRotationOutcome, reason_label

V3_ROTATION_TOTAL = Counter(
    'omi_listen_v3_rotation_total',
    'Listen v3 recording rotations by outcome; handed_off rows wait for listen stale recovery',
    ['outcome'],
)
for _outcome in RecordingRotationOutcome:
    V3_ROTATION_TOTAL.labels(
        outcome=reason_label(ReasonFamily.RECORDING_ROTATION, _outcome.value, RecordingRotationOutcome)
    )


def record_rotation(outcome: str) -> None:
    V3_ROTATION_TOTAL.labels(
        outcome=reason_label(ReasonFamily.RECORDING_ROTATION, outcome, RecordingRotationOutcome)
    ).inc()
