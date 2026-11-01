"""Required capture ownership and the separately controlled historical ramp."""

import os
from datetime import datetime, timezone

from config.rollout_cohorts import cohort_admits

# Historical submissions require retrospective dedupe before becoming visible.
# This is a data boundary, not the unused maintenance-job deploy window.
BACKLOG_CUTOFF = datetime(2026, 10, 26, 7, 55, tzinfo=timezone.utc)
INLINE_TIMEOUT_SECONDS = 12
RETRY_MIN_AGE_MINUTES = 10
RETRY_ITEMS_PER_OWNER = 5
BACKLOG_ITEMS_PER_PASS = 3


def enabled():
    return os.getenv('MEMORY_REQUIRED_INTAKE_ENABLED', 'true').strip().lower() not in {'false', '0', 'off', 'no'}


def backlog_enabled(uid):
    if not enabled() or os.getenv('DREAM_REQUIRED_INTAKE_BACKLOG_ENABLED', 'false').strip().lower() != 'true':
        return False
    return cohort_admits(uid, os.getenv('DREAM_REQUIRED_INTAKE_BACKLOG_COHORT', ''))
