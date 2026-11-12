"""Spaces sync API admission; environment is read at call time."""

import os


def enabled() -> bool:
    return os.getenv('SPACES_SYNC_API_ENABLED', 'false').lower() == 'true'
