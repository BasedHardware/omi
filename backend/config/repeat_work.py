"""Independent default-off cuts; existing Train 1 switches retain their meaning.

REPEAT_WORK_REVISION_ENABLED state resolved 2026-11-01: off everywhere, deliberately.
It adds no LLM skips (those are CONVERSATION_LLM_INPUT_DEDUPE_ENABLED, default-on).
It buys stricter reuse fingerprints (route + version + content revision), an
extra-read-free dedupe probe, a 1h outbox ceiling and the omi_repeat_work_* metrics;
the Firestore read it saves is ~$0.05/day while flipping it on re-processes every
conversation once. Correctness/observability switch, not a margin lever.

"""

from config.refactor_switches import default_off as rollout_default_off

import os


def playback_on_demand() -> bool:
    return rollout_default_off(
        'PLAYBACK_ON_DEMAND_ENABLED', os.getenv('PLAYBACK_ON_DEMAND_ENABLED', 'false').strip().lower() == 'true'
    )


def revision_reuse() -> bool:
    return rollout_default_off(
        'REPEAT_WORK_REVISION_ENABLED', os.getenv('REPEAT_WORK_REVISION_ENABLED', 'false').strip().lower() == 'true'
    )


def poll_backoff() -> bool:
    return rollout_default_off(
        'SYNC_POLL_BACKOFF_ENABLED', os.getenv('SYNC_POLL_BACKOFF_ENABLED', 'false').strip().lower() == 'true'
    )
