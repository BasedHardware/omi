"""Process-wide admission bounds for durable pusher recording cleanup."""

import os


def abandon_record_drain_cap() -> int:
    try:
        value = int(os.getenv('PUSHER_MAX_ABANDON_RECORD_DRAINS', '4'))
    except ValueError:
        value = 4
    return max(0, min(16, value))
