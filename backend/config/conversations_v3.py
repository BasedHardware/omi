"""Per-owner admission. Downstream work follows the stored recording marker."""

import os

from config.rollout_cohorts import in_rollout_cohort
from utils.episodes import client_gate


def conversations_v3_enabled(uid: str) -> bool:
    if not uid or os.getenv('CONVERSATIONS_V3', '').strip().lower() == 'off':
        return False
    stage = os.getenv('CONVERSATIONS_V3_STAGE', 'beta').strip().lower()
    return (
        stage == 'all'
        or (stage == 'beta' and client_gate.client_seen(uid))
        or in_rollout_cohort(uid, 'conversations-v3')
    )


def backfill_enabled() -> bool:
    return os.getenv('CONVERSATIONS_V3_BACKFILL', 'off').strip().lower() == 'on'
