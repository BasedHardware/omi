"""Fleet safety-WAL suppression; explicit off (or invalid value) restores legacy intake."""

from config.refactor_switches import default_off as rollout_default_off

import os


def sync_safety_wal_enabled() -> bool:
    # Unconfigured environments retain legacy intake; deployments opt in explicitly.
    return rollout_default_off(
        'SYNC_SAFETY_WAL_DEDUPE_ENABLED',
        os.getenv('SYNC_SAFETY_WAL_DEDUPE_ENABLED', 'false').strip().lower() in {'1', 'true', 'on', 'yes', 'enabled'},
    )
