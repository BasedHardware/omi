"""Default-off demand scheduling. Read controls at each boundary."""

import os


def enabled(uid: str | None = None) -> bool:
    if os.getenv('DEMAND_PROCESSING_ENABLED', 'false').lower() != 'true':
        return False
    if uid is None:
        return True
    import hashlib

    if not uid:
        return False
    allowlist = {item.strip() for item in os.getenv('DEMAND_PROCESSING_UID_ALLOWLIST', '').split(',') if item.strip()}
    try:
        percent = max(0, min(100, int(os.getenv('DEMAND_PROCESSING_PERCENT', '0'))))
    except ValueError:
        percent = 0
    return uid in allowlist or int(hashlib.sha256(uid.encode()).hexdigest()[:8], 16) % 100 < percent


def lazy_enabled(uid: str | None = None) -> bool:
    return enabled(uid) and os.getenv('DEMAND_PROCESSING_LAZY_ENABLED', 'false').lower() == 'true'


def tool_enabled(uid: str | None = None) -> bool:
    return enabled(uid) and os.getenv('DEMAND_PROCESSING_TOOL_ENABLED', 'false').lower() == 'true'


OPEN_LEASE_SECONDS = 90
RECENT_SECONDS = 7 * 86400
# Priority orders contention; idle capacity must never wait for a tier timer.
# Reserve one minute for processing before the hard completion ceiling.
CEILING_HEADROOM_SECONDS = 3540
CEILING_SECONDS = 3600


def surface_reporting_enabled() -> bool:
    return os.getenv('DEMAND_PROCESSING_SURFACE_REPORTING_ENABLED', 'false').lower() == 'true'
