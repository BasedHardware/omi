"""Default-on stale-target recovery; explicit off restores strict bridge failures."""

import os


def sync_finalize_target_recovery_enabled() -> bool:
    raw = os.getenv('SYNC_FINALIZE_TARGET_RECOVERY_ENABLED', '').strip().lower()
    return not raw or raw in {'1', 'true', 'on', 'yes', 'enabled'}
