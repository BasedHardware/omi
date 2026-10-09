"""Rollout controls for cached-evidence conversation grouping (default dark)."""

# LIFECYCLE: permanent
from __future__ import annotations

import os
from dataclasses import dataclass

from config.jev_decisions import percentage, uid_bucket

VARIANTS = ('provider_strict', 'provider_cannot_link', 'owner_link')


@dataclass(frozen=True)
class GroupingConfig:
    mode: str
    shadow: bool
    detailed: bool
    cross_scope_threshold: float


def configuration(uid: str) -> GroupingConfig:
    mode = os.getenv('SPEAKER_GROUPING_MODE', 'incumbent').strip().lower()
    if mode not in VARIANTS:
        mode = 'incumbent'
    shadow_mode = os.getenv('SPEAKER_GROUPING_SHADOW', 'off').strip().lower()
    allowlist = {s.strip() for s in os.getenv('SPEAKER_GROUPING_SHADOW_UID_ALLOWLIST', '').split(',') if s.strip()}
    detailed = bool(uid and uid in allowlist)
    shadow = shadow_mode in ('owner', 'cohort') and detailed
    if shadow_mode == 'cohort' and uid:
        shadow = shadow or uid_bucket(uid, 'speaker-grouping-shadow-v1') < percentage(
            'SPEAKER_GROUPING_SHADOW_PERCENT', default=10.0
        )
    try:
        threshold = float(os.getenv('SPEAKER_GROUPING_CROSS_SCOPE_THRESHOLD', '0.60'))
        if not 0 < threshold <= 0.70:
            raise ValueError('threshold')
    except ValueError:
        threshold = 0.60
    return GroupingConfig(mode, shadow, detailed and shadow, threshold)
