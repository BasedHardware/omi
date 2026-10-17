"""Independent dark rollout; invalid configuration never admits more owners."""

import os


def enabled(uid: str | None = None) -> bool:
    if os.getenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'false').strip().lower() != 'true':
        return False
    owners = {v.strip() for v in os.getenv('FIRST_SUMMARY_UID_ALLOWLIST', '').split(',') if v.strip()}
    return uid is None or not owners or uid in owners


def repair_enabled() -> bool:
    return enabled() and os.getenv('SUMMARY_DEBT_REPAIR_ENABLED', 'false').strip().lower() == 'true'


def deadline_seconds() -> int:
    try:
        return max(60, min(120, int(os.getenv('FIRST_SUMMARY_DEADLINE_SECONDS', '120'))))
    except ValueError:
        return 120


# One global leased scan per interval, irrespective of replica count.
REPAIR_INTERVAL_SECONDS = 120
REPAIR_SCAN_LIMIT = 100
REPAIR_ADMISSION_LIMIT = 10
