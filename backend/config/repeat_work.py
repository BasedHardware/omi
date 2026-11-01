"""Independent default-off cuts; existing Train 1 switches retain their meaning."""

from config.refactor_switches import default_off as rollout_default_off

import os


def playback_on_demand() -> bool:
    return rollout_default_off(
        'PLAYBACK_ON_DEMAND_ENABLED', os.getenv('PLAYBACK_ON_DEMAND_ENABLED', 'false').strip().lower() == 'true'
    )


def revision_reuse() -> bool:
    return rollout_default_off(
        'REPEAT_WORK_REVISION_ENABLED', os.getenv('REPEAT_WORK_REVISION_ENABLED', 'false').strip().lower() == 'true'
    )


def poll_backoff() -> bool:
    return rollout_default_off(
        'SYNC_POLL_BACKOFF_ENABLED', os.getenv('SYNC_POLL_BACKOFF_ENABLED', 'false').strip().lower() == 'true'
    )
