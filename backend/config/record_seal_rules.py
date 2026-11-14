"""Independent default-on rollback switches for approved seal proof rules."""

import math
import os

MAX_LIVE_PRODUCER_GRACE_SECONDS = 7 * 86400.0


def overlap_trim_enabled():
    return os.getenv('RECORD_SEAL_OVERLAP_TRIM_ENABLED', 'true').strip().lower() == 'true'


def upload_failed_repair_enabled():
    return os.getenv('RECORD_SEAL_UPLOAD_FAILED_REPAIR_ENABLED', 'true').strip().lower() == 'true'


def live_producer_grace_seconds() -> float:
    """Completed captures older than this no longer wait on their pusher pod's restart.

    `fail_recording` keeps its producer token as a fence, and repair used to wait
    for that long-lived pod to restart before sealing. Past this grace after
    completion no producer may still append audio; the retained-tail proof stays
    the custody gate. 0 restores the pod-restart-only rule.
    """
    try:
        value = float(os.getenv('RECORD_SEAL_LIVE_PRODUCER_GRACE_SECONDS', '3600'))
    except ValueError:
        return 3600.0
    if not math.isfinite(value) or value < 0:
        return 3600.0
    # Clamp long graces to the maximum instead of silently reverting to the
    # default, which would turn the exemption on at one hour.
    return min(value, MAX_LIVE_PRODUCER_GRACE_SECONDS)


def refused_stamp_enabled():
    return os.getenv('RECORD_SEAL_REFUSED_STAMP_ENABLED', 'true').strip().lower() == 'true'
