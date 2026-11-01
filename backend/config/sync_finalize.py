"""Default-on stale-target recovery; explicit off restores strict bridge failures."""

import os

from config.refactor_switches import default_on as rollout_default_on


def sync_finalize_target_recovery_enabled() -> bool:
    raw = os.getenv('SYNC_FINALIZE_TARGET_RECOVERY_ENABLED', '').strip().lower()
    return rollout_default_on(
        'SYNC_FINALIZE_TARGET_RECOVERY_ENABLED', not raw or raw in {'1', 'true', 'on', 'yes', 'enabled'}
    )
