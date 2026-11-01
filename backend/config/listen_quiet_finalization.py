"""Shared kill switch for disconnect checks and fast orphan recovery."""

from config.refactor_switches import default_off as rollout_default_off

import os


def enabled() -> bool:
    return rollout_default_off(
        'LISTEN_QUIET_FINALIZATION_ENABLED',
        os.getenv('LISTEN_QUIET_FINALIZATION_ENABLED', 'true').strip().lower() in {'true', '1', 'yes', 'on'},
    )
