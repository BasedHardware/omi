"""Independent dark rollout; invalid configuration never admits more owners."""

import math
import os

from config.batch_pipeline import in_percent_cohort


def enabled(uid: str | None = None) -> bool:
    if os.getenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'false').strip().lower() != 'true':
        return False
    owners = {v.strip() for v in os.getenv('FIRST_SUMMARY_UID_ALLOWLIST', '').split(',') if v.strip()}
    if uid is None or uid in owners:
        return True
    try:
        percent = float(os.getenv('FIRST_SUMMARY_DEADLINE_PERCENT', '0'))
    except ValueError:
        return False
    if not math.isfinite(percent) or not 0 <= percent <= 100:
        return False
    # Preserve the existing explicit enable-all contract at zero only.
    if percent == 0:
        return not owners
    return in_percent_cohort(uid, percent)


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
