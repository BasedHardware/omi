"""Rollout controls for cached-evidence conversation grouping (default dark)."""

# LIFECYCLE: permanent
from __future__ import annotations

import os

from config.rollout_cohorts import in_rollout_cohort
from dataclasses import dataclass

from config.jev_decisions import percentage, uid_bucket

VARIANTS = ('provider_strict', 'provider_cannot_link', 'owner_link')
AUTHORITATIVE_MODES = ('incumbent', 'provider_strict', 'provider_cannot_link')


@dataclass(frozen=True)
class GroupingConfig:
    mode: str
    shadow: bool
    detailed: bool
    cross_scope_threshold: float


def configuration(uid: str) -> GroupingConfig:
    mode = os.getenv('SPEAKER_GROUPING_MODE', 'incumbent').strip().lower()
    if mode not in AUTHORITATIVE_MODES:
        mode = 'incumbent'
    shadow_mode = os.getenv('SPEAKER_GROUPING_SHADOW', 'off').strip().lower()
    detailed = bool(shadow_mode in ('owner', 'cohort') and in_rollout_cohort(uid, 'speaker-grouping-shadow'))
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
