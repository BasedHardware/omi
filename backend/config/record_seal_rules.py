"""Independent default-on rollback switches for approved seal proof rules."""

import os


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
    return value if value == value and 0 <= value <= 7 * 86400 else 3600.0


def refused_stamp_enabled():
    return os.getenv('RECORD_SEAL_REFUSED_STAMP_ENABLED', 'true').strip().lower() == 'true'
