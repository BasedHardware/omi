"""Owner-requested cancellation of an uploaded, not-yet-processed sync recording. No IO at import."""

import os

SWITCH = 'SYNC_JOB_OWNER_CANCEL_ENABLED'
_OFF = frozenset({'false', '0', 'off', 'no'})


def enabled() -> bool:
    """Kill switch, on unless explicitly off. Read per request."""
    return os.getenv(SWITCH, 'true').strip().lower() not in _OFF
