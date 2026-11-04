"""Read-path fair-use dwell samples and committed decay transitions, with closed labels."""

from prometheus_client import Counter, Gauge

STAGES = ('none', 'warning', 'throttle', 'restrict')
DECAYS = (('restrict', 'throttle'), ('throttle', 'warning'), ('warning', 'none'))
STAGE_DWELL_SECONDS = Gauge(
    'omi_fair_use_stage_dwell_seconds',
    'Dwell of the last authoritative fair-use row read per stage; legacy rows use last violation or update time.',
    ['stage'],
)
STAGE_DECAY_TOTAL = Counter(
    'omi_fair_use_stage_decay_total', 'Persisted fair-use stage expiry transitions.', ['from_stage', 'to_stage']
)
for stage in STAGES:
    STAGE_DWELL_SECONDS.labels(stage=stage)
for from_stage, to_stage in DECAYS:
    STAGE_DECAY_TOTAL.labels(from_stage=from_stage, to_stage=to_stage)


def observe_stage_dwell(stage: str, seconds: float) -> None:
    if stage in STAGES:
        STAGE_DWELL_SECONDS.labels(stage=stage).set(seconds)


def record_decay(from_stage: str, to_stage: str) -> None:
    if (from_stage, to_stage) in DECAYS:
        STAGE_DECAY_TOTAL.labels(from_stage=from_stage, to_stage=to_stage).inc()
