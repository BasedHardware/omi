"""Pure rollout predicates; the application injects membership resolution."""

from __future__ import annotations

import os
from typing import Any, Callable

COLLECTION = 'rollout_cohorts'
# Literal env reads keep the migration fallbacks visible to the flag registry.
COHORT_ENVS = {
    'batch-pipeline': lambda: os.getenv('BATCH_PIPELINE_UID_ALLOWLIST', ''),
    'batch-pipeline-recovery': lambda: os.getenv('BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST', ''),
    'first-summary': lambda: os.getenv('FIRST_SUMMARY_UID_ALLOWLIST', ''),
    'audio-archive': lambda: os.getenv('AUDIO_ARCHIVE_UID_ALLOWLIST', ''),
    'dream-agent': lambda: os.getenv('DREAM_AGENT_UID_ALLOWLIST', ''),
    'speaker-grouping-shadow': lambda: os.getenv('SPEAKER_GROUPING_SHADOW_UID_ALLOWLIST', ''),
    'stt-live-demand': lambda: os.getenv('STT_LIVE_DEMAND_UID_ALLOWLIST', ''),
    'sync-legacy-fresh': lambda: os.getenv('SYNC_LEGACY_FRESH_UID_ALLOWLIST', ''),
    'sync-lineage-resolve': lambda: os.getenv('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST', ''),
    'transcription-final-pass': lambda: os.getenv('TRANSCRIPTION_FINAL_PASS_UID_ALLOWLIST', ''),
    'transcription-shadow': lambda: os.getenv('TRANSCRIPTION_SHADOW_UID_ALLOWLIST', ''),
    'mobile-standard-batch': lambda: os.getenv('MOBILE_STANDARD_BATCH_UIDS', ''),
    'messaging-telegram': lambda: os.getenv('OMI_MESSAGING_CHANNELS_UIDS', ''),
    'messaging-imessage': lambda: os.getenv('OMI_MESSAGING_CHANNELS_UIDS', ''),
}


def rollout_environment() -> str:
    """Existing runtime identity, independent of the shared customer project."""
    stage = os.getenv('OMI_ENV_STAGE', 'local').strip().lower()
    if stage not in {'prod', 'dev', 'local', 'offline'}:
        raise ValueError('invalid rollout environment')
    return stage


def valid_uid(uid: object) -> bool:
    return isinstance(uid, str) and bool(uid) and uid.strip() == uid and '/' not in uid and len(uid.encode()) <= 256


_membership_resolver: Callable[..., bool] | None = None
_members_resolver: Callable[[str], tuple[str, ...]] | None = None
_load_resolver: Callable[[str], Any] | None = None
_warm_resolver: Callable[[str], Any] | None = None


def configured() -> bool:
    return _membership_resolver is not None


def configure_resolvers(membership, members, load, warm) -> None:
    global _membership_resolver, _members_resolver, _load_resolver, _warm_resolver
    _membership_resolver, _members_resolver = membership, members
    _load_resolver, _warm_resolver = load, warm


def legacy_membership(uid, name, *, legacy_members=None, legacy_all=False) -> bool:
    if legacy_members is None:
        legacy_members = tuple(item.strip() for item in COHORT_ENVS[name]().split(',') if item.strip())
    return legacy_all or uid in legacy_members


def in_rollout_cohort(uid: str, name: str, *, legacy_members=None, legacy_all=False) -> bool:
    if not valid_uid(uid) or name not in COHORT_ENVS or _membership_resolver is None:
        return False
    return _membership_resolver(uid, name, legacy_members=legacy_members, legacy_all=legacy_all)


def rollout_cohort_members(name: str) -> tuple[str, ...]:
    if name not in COHORT_ENVS or _members_resolver is None:
        return ()
    return _members_resolver(name)


def load_rollout_cohorts(uid: str) -> None:
    if valid_uid(uid) and _load_resolver is not None:
        _load_resolver(uid)


async def warm_rollout_cohorts(uid: str) -> None:
    if valid_uid(uid) and _warm_resolver is not None:
        await _warm_resolver(uid)
