"""Per-owner admission. Downstream work follows the stored recording marker."""

import os

from config.rollout_cohorts import in_rollout_cohort
from utils.conversations.v3 import client_capability
from utils.episodes import client_gate


def conversations_v3_enabled(uid: str) -> bool:
    """``beta``: TestFlight-seen owners with a v3-capable app. ``all``: owners with a v3-capable app.

    Neither admits an owner whose apps all predate v3: those builds show the raw recording a capture
    ends with as a blank card that 404s (utils/conversations/v3/client_capability.py). The episodes
    marker alone is not proof: code before #25500 also wrote it for store-channel episode callers.
    """
    if not uid or os.getenv('CONVERSATIONS_V3', '').strip().lower() == 'off':
        return False
    stage = os.getenv('CONVERSATIONS_V3_STAGE', 'beta').strip().lower()
    if stage == 'beta' and client_gate.client_seen_cached(uid) and client_capability.capable_cached(uid):
        return True
    if stage == 'all' and client_capability.capable_cached(uid):
        return True
    return in_rollout_cohort(uid, 'conversations-v3')


def backfill_enabled() -> bool:
    return os.getenv('CONVERSATIONS_V3_BACKFILL', 'off').strip().lower() == 'on'


def episode_build_bucket(raw: str) -> str:
    boundary = os.getenv('CONVERSATIONS_V3_FIRST_APP_BUILD', '').strip()
    if not boundary.isdecimal() or not raw.isdecimal() or int(boundary) <= 0 or int(raw) <= 0:
        return 'unknown'
    return 'v3_capable' if int(raw) >= int(boundary) else 'pre_v3'
