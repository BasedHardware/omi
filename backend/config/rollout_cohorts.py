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


# Reserved control-document ids in COLLECTION (contract (f)); never a member uid.
RAMP_DOC_PREFIX = '_ramp'


def valid_uid(uid: object) -> bool:
    return (
        isinstance(uid, str)
        and bool(uid)
        and uid.strip() == uid
        and '/' not in uid
        and len(uid.encode()) <= 256
        and not uid.startswith(RAMP_DOC_PREFIX)
    )


_membership_resolver: Callable[..., bool] | None = None
_members_resolver: Callable[[str], tuple[str, ...]] | None = None
_load_resolver: Callable[[str], Any] | None = None
_warm_resolver: Callable[[str], Any] | None = None
_percent_resolver: Callable[[str, float], float] | None = None
_legacy_sync_resolver: Callable[[], str] | None = None


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


def configure_runtime_percent(percent: Callable[[str, float], float], legacy_sync: Callable[[], str]) -> None:
    """Bind the runtime `_ramp` reader (utils.rollout.runtime_percent); unbound processes keep env values."""
    global _percent_resolver, _legacy_sync_resolver
    _percent_resolver, _legacy_sync_resolver = percent, legacy_sync


def runtime_percent(name: str, *, env_default: float) -> float:
    """Percent source for config predicates; the bucket functions stay where they are.

    Unbound (tests, tools, images without the runtime) means today's environment value.
    """
    if _percent_resolver is None:
        return env_default
    return _percent_resolver(name, env_default)


def legacy_sync_mode() -> str:
    """'on' | 'draining' | 'dark' (contract (h)); unbound means 'on', today's behaviour."""
    if _legacy_sync_resolver is None:
        return 'on'
    return _legacy_sync_resolver()
