"""Admission for the mobile Standard batch lane; every switch defaults off."""

import hashlib
import os

from config.rollout_cohorts import in_rollout_cohort


def mobile_standard_batch_rollout_enabled() -> bool:
    return os.getenv('MOBILE_STANDARD_BATCH_ENABLED', '').lower() == 'true'


def mobile_standard_batch_enabled(uid: str) -> bool:
    if not mobile_standard_batch_rollout_enabled() or not uid:
        return False
    if in_rollout_cohort(uid, 'mobile-standard-batch'):
        return True
    try:
        percent = int(os.getenv('MOBILE_STANDARD_BATCH_PERCENT', '0'))
    except ValueError:
        return False
    if not 0 <= percent <= 100:
        return False
    bucket = int(hashlib.sha256(f'mobile-standard-batch:{uid}'.encode()).hexdigest()[:8], 16) % 10000
    return bucket < percent * 100
