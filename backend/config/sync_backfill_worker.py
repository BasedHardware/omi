"""Backfill pull-worker intake. Percent zero closes claims without closing leases."""

import math
import os

from config.policy.batch import cohort_bucket


def percent() -> float:
    try:
        value = float(os.getenv('SYNC_BACKFILL_WORKER_PERCENT', '0'))
    except ValueError:
        return 0
    return max(0, min(100, value)) if math.isfinite(value) else 0


def selected(uid: str) -> bool:
    return bool(uid) and cohort_bucket(uid, '') < percent()


def eligible_payload(payload: dict) -> bool:
    return payload.get('lane') == 'backfill' and payload.get('ledger_fence_mode') == 'active'
