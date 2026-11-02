"""Account-deletion grace window bindings.

Pure config module: no client construction, env read at the call boundary so
operators can flip the kill switch or resize the window without a redeploy.
"""

from __future__ import annotations

import os
from datetime import timedelta

DEFAULT_GRACE_WINDOW_DAYS = 14

# A pathological window (huge) would hold data forever; a negative one would
# make the wipe due in the past at admission. Both are operator typos, not
# intent, so the window is clamped instead of rejected.
_MAX_GRACE_WINDOW_DAYS = 365


def account_deletion_grace_enabled() -> bool:
    """Ship-on-by-default kill switch; ``false`` restores immediate deletion."""
    return os.getenv('ACCOUNT_DELETION_GRACE_ENABLED', 'true').strip().lower() != 'false'


def account_deletion_grace_window_days() -> int:
    raw = os.getenv('ACCOUNT_DELETION_GRACE_WINDOW_DAYS', str(DEFAULT_GRACE_WINDOW_DAYS)).strip()
    try:
        days = int(raw)
    except ValueError:
        return DEFAULT_GRACE_WINDOW_DAYS
    return max(0, min(days, _MAX_GRACE_WINDOW_DAYS))


def account_deletion_grace_window() -> timedelta:
    return timedelta(days=account_deletion_grace_window_days())
