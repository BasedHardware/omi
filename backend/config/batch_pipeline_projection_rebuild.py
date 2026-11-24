"""Runtime kill switch for optional projection-debt handoff and maintenance."""

import os


def enabled() -> bool:
    return os.getenv('PUSHER_PROJECTION_DEBT_DURABLE_ENABLED', '1').strip().lower() not in {'0', 'false', 'off'}
