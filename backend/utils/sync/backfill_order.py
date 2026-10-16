"""Read-only rollout policy shared by durable and direct backfill dispatch."""

import hashlib
import math
import os


def newest_first(uid: str) -> bool:
    if os.getenv('SYNC_BACKFILL_ORDER', 'oldest').strip().lower() != 'newest':
        return False
    allowlist = {value.strip() for value in os.getenv('SYNC_BACKFILL_ORDER_UID_ALLOWLIST', '').split(',')}
    if uid and uid in allowlist:
        return True
    try:
        percent = float(os.getenv('SYNC_BACKFILL_ORDER_PERCENT', '100'))
    except ValueError:
        return False
    if not math.isfinite(percent):
        return False
    bucket = int.from_bytes(hashlib.sha256(uid.encode()).digest()[:4], 'big') / 2**32 * 100
    return bool(uid) and bucket < max(0, min(100, percent))


def direct_schedule_at(payload: dict) -> int | None:
    """Prefer recent direct uploads with at most five minutes of eligibility delay.

    Capture age already exists on the durable payload. Anchor to admission so
    uncertain enqueue retries never push the deadline out. Sequenced tasks have
    already been selected and must run immediately. Cloud Tasks is unordered
    among eligible tasks: this is a bounded preference, not strict priority.
    """
    if (
        payload.get('lane') != 'backfill'
        or payload.get('sequencer_epoch') is not None
        or not newest_first(payload.get('uid', ''))
    ):
        return None
    admitted = payload.get('enqueued_at')
    age = payload.get('recording_age_seconds')
    if not isinstance(admitted, (int, float)) or not math.isfinite(admitted):
        return None
    # Unknown capture time takes the oldest bucket; no untrusted age can
    # request a longer hold or a schedule before admission.
    age = age if isinstance(age, (int, float)) and math.isfinite(age) else 86400
    return math.ceil(admitted + min(86400, max(0, age)) / 288)
