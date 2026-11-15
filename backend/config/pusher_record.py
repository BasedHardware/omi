"""Process-wide admission bounds for durable pusher recording cleanup."""

import os

from config.refactor_modes import default_on


def seal_pending_retry_bound_enabled() -> bool:
    return default_on('PUSHER_RECORD_SEAL_PENDING_RETRY_BOUND_ENABLED')


def abandon_record_drain_cap() -> int:
    try:
        value = int(os.getenv('PUSHER_MAX_ABANDON_RECORD_DRAINS', '4'))
    except ValueError:
        value = 4
    return max(0, min(16, value))
