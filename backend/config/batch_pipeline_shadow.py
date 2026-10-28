"""Independent, fail-closed shadow cohort and spend controls (runtime reads)."""

import math
import os

from config.policy.batch import cohort_bucket

from config.rollout_cohorts import in_rollout_cohort, valid_uid


def shadow_percent() -> float:
    try:
        value = float(os.getenv('BATCH_PIPELINE_SHADOW_PERCENT', '0'))
        return value if math.isfinite(value) and 0 <= value <= 100 else 0.0
    except ValueError:
        return 0.0


def selected(uid: str, policy) -> bool:
    percent = shadow_percent()
    if not percent or not valid_uid(uid) or policy.batch_enabled or in_rollout_cohort(uid, 'batch-pipeline'):
        return False
    bucket = cohort_bucket(uid, 'batch-pipeline-shadow')
    return bucket < percent and in_rollout_cohort(uid, 'batch-pipeline-shadow', legacy_all=True)


def paid_recovery_limit() -> int:
    try:
        value = int(os.getenv('BATCH_PIPELINE_SHADOW_PAID_RECOVERY_PER_HOUR', '200'))
        return max(0, value)
    except ValueError:
        return 0


def language_only_enabled() -> bool:
    """Operator qualification mode: classify one canonical unit; never run the GPU chain."""
    return os.getenv('BATCH_PIPELINE_SHADOW_LANGUAGE_ONLY', 'false').strip().lower() == 'true'


def language_probe_limit() -> int:
    """Fleet-wide hourly attempt cap; malformed settings deny new probes."""
    try:
        return min(500, max(0, int(os.getenv('BATCH_PIPELINE_SHADOW_LANGUAGE_PROBES_PER_HOUR', '500'))))
    except ValueError:
        return 0
