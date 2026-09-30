"""Independent default-off switches for the three PR #14165 basic-plan gates.

Each reader is a fleet-wide rollout flag, read at call time so a process does
not snapshot a stale value. Unset and any value other than ``true``
(case-insensitive) is off: that surface stays byte-identical to main before
#14165 (no authorize call, no new Firestore read, no new marker).

Truthiness matches ``FREE_TIER_LOCAL_PROCESSING`` /
``FREE_TIER_MEMORY_SUPPRESSION``: only ``true`` (any case) lights the gate.
``1`` / ``yes`` / ``on`` stay off.

``FREE_TIER_EMERGENCY_STOP`` (``utils.free_tier_cohort.emergency_stop_engaged``)
revokes every switch without editing the three flags, matching the S0/S5/S6
stop. These gates are not cohort-scoped: a lit flag lights the whole fleet on
that identity. ``cohort_admits`` is not used; an unset cohort would admit
nobody and could not be the default-off / explicit-on contract.

Dev overlays set all three ``true`` (Beta product). Prod overlays set all
three ``false`` so a routine production deploy does not take a free-user
capability away before the local replacement ships.
"""

from __future__ import annotations

import os

from utils.free_tier_cohort import emergency_stop_engaged

BASIC_PLAN_GATE_PROACTIVITY_ENABLED = 'BASIC_PLAN_GATE_PROACTIVITY_ENABLED'
BASIC_PLAN_GATE_PROXY_EMBED_ENABLED = 'BASIC_PLAN_GATE_PROXY_EMBED_ENABLED'
BASIC_PLAN_GATE_EAGER_EXTRACTION_ENABLED = 'BASIC_PLAN_GATE_EAGER_EXTRACTION_ENABLED'


def _env_flag_on(name: str) -> bool:
    """Same truthiness as ``FREE_TIER_LOCAL_PROCESSING`` / ``FREE_TIER_MEMORY_SUPPRESSION``."""
    return os.getenv(name, 'false').lower() == 'true'


def _gate_enabled(name: str) -> bool:
    if not _env_flag_on(name):
        return False
    if emergency_stop_engaged():
        return False
    return True


def basic_plan_gate_proactivity_enabled() -> bool:
    """Is the desktop-proactivity 402 ``plan_gated`` path lit?"""
    return _gate_enabled(BASIC_PLAN_GATE_PROACTIVITY_ENABLED)


def basic_plan_gate_proxy_embed_enabled() -> bool:
    """Are Gemini ``embedContent`` / ``batchEmbedContents`` plan-gated?

    ``generateContent`` / ``streamGenerateContent`` stay gated unconditionally
    (S14 shard, already live in prod).
    """
    return _gate_enabled(BASIC_PLAN_GATE_PROXY_EMBED_ENABLED)


def basic_plan_gate_eager_extraction_enabled() -> bool:
    """Is identified-basic first-open / reprocess landed on the deterministic minimum?"""
    return _gate_enabled(BASIC_PLAN_GATE_EAGER_EXTRACTION_ENABLED)


__all__ = [
    'BASIC_PLAN_GATE_EAGER_EXTRACTION_ENABLED',
    'BASIC_PLAN_GATE_PROACTIVITY_ENABLED',
    'BASIC_PLAN_GATE_PROXY_EMBED_ENABLED',
    'basic_plan_gate_eager_extraction_enabled',
    'basic_plan_gate_proactivity_enabled',
    'basic_plan_gate_proxy_embed_enabled',
]
