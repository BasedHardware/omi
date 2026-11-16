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
        or (stage == 'beta' and client_gate.client_seen_cached(uid))
        or in_rollout_cohort(uid, 'conversations-v3')
    )


def backfill_enabled() -> bool:
    return os.getenv('CONVERSATIONS_V3_BACKFILL', 'off').strip().lower() == 'on'


def episode_build_bucket(raw: str) -> str:
    boundary = os.getenv('CONVERSATIONS_V3_FIRST_APP_BUILD', '').strip()
    if not boundary.isdecimal() or not raw.isdecimal() or int(boundary) <= 0 or int(raw) <= 0:
        return 'unknown'
    return 'v3_capable' if int(raw) >= int(boundary) else 'pre_v3'
