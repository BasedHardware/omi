"""Independent default-off cuts; existing Train 1 switches retain their meaning.

Revision reuse retired 2026-11-09 after remaining off everywhere.
It adds no LLM skips (those are CONVERSATION_LLM_INPUT_DEDUPE_ENABLED, default-on).
It buys stricter reuse fingerprints (route + version + content revision), an
extra-read-free dedupe probe, a 1h outbox ceiling and the omi_repeat_work_* metrics;
the Firestore read it saves is ~$0.05/day while flipping it on re-processes every
conversation once. Correctness/observability switch, not a margin lever.

"""

import hashlib
import math
import os

from config.refactor_switches import default_off as rollout_default_off


def playback_on_demand() -> bool:
    return rollout_default_off(
        'PLAYBACK_ON_DEMAND_ENABLED', os.getenv('PLAYBACK_ON_DEMAND_ENABLED', 'false').strip().lower() == 'true'
    )


def poll_backoff(uid: str | None = None) -> bool:
    """Serve poll hints to a stable UID cohort while retaining the global kill switch."""
    if not rollout_default_off(
        'SYNC_POLL_BACKOFF_ENABLED', os.getenv('SYNC_POLL_BACKOFF_ENABLED', 'false').strip().lower() == 'true'
    ):
        return False
    return poll_backoff_cohort(uid) == 'in'


def poll_backoff_cohort(uid: str | None) -> str:
    """Return stable cohort membership independent of the serving kill switch."""
    try:
        percent = float(os.getenv('SYNC_POLL_BACKOFF_PERCENT', '0') or 0)
    except ValueError:
        return 'out'
    if not math.isfinite(percent) or not 0 <= percent <= 100 or percent == 0:
        return 'out'
    if percent == 100:
        return 'in'
    if not uid:
        return 'out'
    bucket = int.from_bytes(hashlib.sha256(f'sync-poll-backoff:{uid}'.encode()).digest()[:4], 'big') / 2**32 * 100
    return 'in' if bucket < percent else 'out'
