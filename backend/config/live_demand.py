"""Dark-by-default phase-4 live demand cohort; invalid settings retain vendors."""

import hashlib
import math
import os

from config.rollout_cohorts import in_rollout_cohort
from dataclasses import dataclass
from typing import TypedDict

from config.stt_provider_policy import normalized_stt_language


class DemandSelection(TypedDict, total=False):
    exclude: frozenset[str]


@dataclass(frozen=True)
class LiveDemandConfig:
    enabled: bool = False
    percent: float = 0
    uids: frozenset[str] = frozenset()
    dwell_seconds: float = 15

    def admits(self, uid: str) -> bool:
        if not self.enabled or not uid:
            return False
        bucket = int.from_bytes(hashlib.sha256(('live-demand:' + uid).encode()).digest()[:8], 'big')
        return (
            in_rollout_cohort(uid, 'stt-live-demand', legacy_members=tuple(self.uids))
            or bucket / 2**64 * 100 < self.percent
        )


def resolve_live_demand() -> LiveDemandConfig:
    try:
        percent = float(os.getenv('STT_LIVE_DEMAND_PERCENT', '0'))
        dwell = float(os.getenv('STT_LIVE_DEMAND_MIN_DWELL_SECONDS', '15'))
        if not math.isfinite(percent) or not 0 <= percent <= 100 or not math.isfinite(dwell) or not 5 <= dwell <= 300:
            return LiveDemandConfig()
        return LiveDemandConfig(
            os.getenv('STT_LIVE_DEMAND_ENABLED', 'false').lower() == 'true',
            percent,
            frozenset(filter(None, (uid.strip() for uid in os.getenv('STT_LIVE_DEMAND_UID_ALLOWLIST', '').split(',')))),
            dwell,
        )
    except ValueError:
        return LiveDemandConfig()


def language_qualified(host) -> bool:
    """Never infer eligibility from detected/learned output or a multi-language default."""
    profile = getattr(host, 'language_profile', None)
    return (
        normalized_stt_language(host.request.language) == 'en'
        and normalized_stt_language(host.language) == 'en'
        and not host.multi_lang_enabled
        and profile is not None
        and profile.primary == 'en'
        and profile.expected == ('en',)
        and not profile.multi
    )
