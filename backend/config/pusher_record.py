"""Process-wide admission bounds for durable pusher recording cleanup and PCM I/O."""

import os


def abandon_record_drain_cap() -> int:
    try:
        value = int(os.getenv('PUSHER_MAX_ABANDON_RECORD_DRAINS', '4'))
    except ValueError:
        value = 4
    return max(0, min(16, value))


def record_storage_workers() -> int:
    try:
        value = int(os.getenv('PUSHER_RECORD_STORAGE_WORKERS', '8'))
    except ValueError:
        value = 8
    return max(1, min(8, value))
