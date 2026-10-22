"""Dark-by-default phase-4 live demand cohort; invalid settings retain vendors."""

import math
import os

from config.refactor_switches import default_off

from config.policy.batch import cohort_bucket

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
    admitted: bool | None = None

    def admits(self, uid: str, *, explicit=False) -> bool:
        if self.admitted is not None:
            return self.admitted
        if not self.enabled or not uid:
            return False
        bucket = cohort_bucket(uid, 'live-demand', bits=64)
        return (
            (uid in self.uids)
            if explicit
            else in_rollout_cohort(uid, 'stt-live-demand', legacy_members=tuple(self.uids))
        ) or bucket < self.percent


def resolve_live_demand(*, flags=None) -> LiveDemandConfig:
    from config.policy.listen import current_listen_policy

    policy = current_listen_policy.get() if flags is None else None
    if policy is not None:
        return LiveDemandConfig(
            policy.demand_enabled,
            policy.demand_percent,
            frozenset(),
            policy.demand_dwell_seconds,
            policy.demand_admitted,
        )
    env = os.environ if flags is None else flags
    try:
        percent = float(env.get('STT_LIVE_DEMAND_PERCENT', '0'))
        dwell = float(env.get('STT_LIVE_DEMAND_MIN_DWELL_SECONDS', '15'))
        if not math.isfinite(percent) or not 0 <= percent <= 100 or not math.isfinite(dwell) or not 5 <= dwell <= 300:
            return LiveDemandConfig()
        return LiveDemandConfig(
            default_off(
                'STT_LIVE_DEMAND_ENABLED', env.get('STT_LIVE_DEMAND_ENABLED', 'false').lower() == 'true', environ=env
            ),
            percent,
            frozenset(filter(None, (uid.strip() for uid in env.get('STT_LIVE_DEMAND_UID_ALLOWLIST', '').split(',')))),
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
