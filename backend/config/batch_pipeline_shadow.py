"""Independent, fail-closed shadow cohort and spend controls (runtime reads)."""

import hashlib
import math
import os

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
    bucket = int(hashlib.sha256(('batch-pipeline-shadow:' + uid).encode()).hexdigest()[:8], 16) / 2**32 * 100
    return bucket < percent and in_rollout_cohort(uid, 'batch-pipeline-shadow', legacy_all=True)


def paid_recovery_limit() -> int:
    try:
        value = int(os.getenv('BATCH_PIPELINE_SHADOW_PAID_RECOVERY_PER_HOUR', '200'))
        return max(0, value)
    except ValueError:
        return 0
