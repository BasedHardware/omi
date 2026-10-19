"""Independent default-off cuts; existing Train 1 switches retain their meaning."""

import os


def playback_on_demand() -> bool:
    return os.getenv('PLAYBACK_ON_DEMAND_ENABLED', 'false').strip().lower() == 'true'


def revision_reuse() -> bool:
    return os.getenv('REPEAT_WORK_REVISION_ENABLED', 'false').strip().lower() == 'true'


def poll_backoff() -> bool:
    return os.getenv('SYNC_POLL_BACKOFF_ENABLED', 'false').strip().lower() == 'true'
