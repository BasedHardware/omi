"""Shared kill switch for disconnect checks and fast orphan recovery."""

import os


def enabled() -> bool:
    return os.getenv('LISTEN_QUIET_FINALIZATION_ENABLED', 'true').strip().lower() in {'true', '1', 'yes', 'on'}
