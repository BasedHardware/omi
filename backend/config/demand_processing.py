"""Default-off demand scheduling. Read controls at each boundary."""

from config.refactor_switches import default_off as rollout_default_off

import os

from config.policy.batch import cohort_bucket


def enabled(uid: str | None = None) -> bool:
    if not rollout_default_off(
        'DEMAND_PROCESSING_ENABLED', not (os.getenv('DEMAND_PROCESSING_ENABLED', 'false').lower() != 'true'), uid=uid
    ):
        return False
    if uid is None:
        return True

    if not uid:
        return False
    allowlist = {item.strip() for item in os.getenv('DEMAND_PROCESSING_UID_ALLOWLIST', '').split(',') if item.strip()}
    try:
        percent = max(0, min(100, int(os.getenv('DEMAND_PROCESSING_PERCENT', '0'))))
    except ValueError:
        percent = 0
    return uid in allowlist or cohort_bucket(uid, '', formula='modulo') < percent


def lazy_enabled(uid: str | None = None) -> bool:
    return enabled(uid) and rollout_default_off(
        'DEMAND_PROCESSING_LAZY_ENABLED',
        os.getenv('DEMAND_PROCESSING_LAZY_ENABLED', 'false').lower() == 'true',
        uid=uid,
    )


def tool_enabled(uid: str | None = None) -> bool:
    return enabled(uid) and rollout_default_off(
        'DEMAND_PROCESSING_TOOL_ENABLED',
        os.getenv('DEMAND_PROCESSING_TOOL_ENABLED', 'false').lower() == 'true',
        uid=uid,
    )


OPEN_LEASE_SECONDS = 90
RECENT_SECONDS = 7 * 86400
# Priority orders contention; idle capacity must never wait for a tier timer.
# Reserve one minute for processing before the hard completion ceiling.
CEILING_HEADROOM_SECONDS = 3540
CEILING_SECONDS = 3600
# A lower tier blocked by ready higher-tier work re-checks on this cadence (one
# Cloud Task per wait), clamped to its ceiling escape (at most 5 s past it,
# inside the one-minute headroom).
BLOCKED_WAIT_SECONDS = 30
# Opening a surface wakes at most this many of the newest indexed obligations;
# older debt keeps its tier and its ceiling, as the process-recent tool does.
OPEN_PROMOTE_LIMIT = 20


def surface_reporting_enabled() -> bool:
    return rollout_default_off(
        'DEMAND_PROCESSING_SURFACE_REPORTING_ENABLED',
        os.getenv('DEMAND_PROCESSING_SURFACE_REPORTING_ENABLED', 'false').lower() == 'true',
    )
