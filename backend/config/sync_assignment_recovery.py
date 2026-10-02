"""Capture recovery switch; read at the assignment boundary, never at import."""

import os


def sync_assignment_recovery_enabled() -> bool:
    """Default on preserves incoming speech; an invalid value disables recovery."""
    return os.getenv('SYNC_ASSIGNMENT_RECOVERY_ENABLED', 'true').strip().lower() in {'true', '1', 'on'}
