"""Process-wide admission bounds for durable pusher recording cleanup."""

import os
from collections import ChainMap

from config.refactor_modes import (
    PUSHER_RECORD_CLOSE_NOTIFY_ENV,
    PUSHER_RECORD_CLOSE_NOTIFY_SERVE_PERCENT_ENV,
    default_off,
    default_on,
    serving_for,
)


def seal_pending_retry_bound_enabled() -> bool:
    return default_on('PUSHER_RECORD_SEAL_PENDING_RETRY_BOUND_ENABLED')


def close_notify_enabled(uid: str | None = None) -> bool:
    # Keep the opt-in boolean as the kill switch. Its companions use the shared
    # shadow-mode cohort parser. An absent percentage preserves the existing
    # true-switch fleet path; explicit zero enables a digest-only cohort.
    return default_off('PUSHER_RECORD_CLOSE_NOTIFY_ENABLED') and serving_for(
        PUSHER_RECORD_CLOSE_NOTIFY_ENV,
        uid,
        'shadow',
        environ=ChainMap(
            {PUSHER_RECORD_CLOSE_NOTIFY_ENV: 'shadow'},
            os.environ,
            {PUSHER_RECORD_CLOSE_NOTIFY_SERVE_PERCENT_ENV: '100'},
        ),
    )


def close_fast_path_enabled() -> bool:
    return default_on('PUSHER_RECORD_CLOSE_FAST_PATH_ENABLED')


def seal_wake_enabled() -> bool:
    return default_on('PUSHER_RECORD_SEAL_WAKE_ENABLED')


def abandon_record_drain_cap() -> int:
    try:
        value = int(os.getenv('PUSHER_MAX_ABANDON_RECORD_DRAINS', '4'))
    except ValueError:
        value = 4
    return max(0, min(16, value))
