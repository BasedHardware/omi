"""Episode log migration switches. Read config at call time; no IO on import."""

import os

from config.episodes import episodes_enabled_for
from config.jev_decisions import uid_bucket
from config.refactor_modes import default_on

DEBOUNCE_SECONDS = 180
MAX_AGE_SECONDS = 1500
LEASE_SECONDS = 600
BATCH_SIZE = 64
SWEEP_SIZE = 32
SWEEP_REDRIVE_SECONDS = 120
RETRY_SECONDS = 30
WAKE_BUCKET_SECONDS = 30


def enabled(uid: str) -> bool:
    if not episodes_enabled_for(uid):
        return False
    from utils import omi_flags

    resolved = omi_flags.resolve('EPISODES_LOG_ENABLED', uid)
    return resolved.enabled if resolved is not None else default_on('EPISODES_LOG_ENABLED')


def home_enabled() -> bool:
    return default_on('EPISODES_HOME_ROWS_ENABLED')


def read_cohort(uid: str) -> bool:
    try:
        percent = float(os.getenv('EPISODES_LOG_READ_PERCENT', '0'))
    except ValueError:
        return False
    return enabled(uid) and home_enabled() and 0 <= percent <= 100 and uid_bucket(uid, 'episodes-log-v1') < percent
