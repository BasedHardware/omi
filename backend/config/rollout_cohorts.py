"""Pure rollout predicates; the application injects membership resolution."""

from __future__ import annotations

import hashlib
import os
from typing import Any, Callable

COLLECTION = 'rollout_cohorts'
# Literal env reads keep the migration fallbacks visible to the flag registry.
COHORT_ENVS = {
    # The composition root injects scoped policy env readers with the runtime.
    'batch-pipeline': lambda: '',
    'batch-pipeline-recovery': lambda: '',
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
    if not isinstance(uid, str) or not uid or uid.strip() != uid or '/' in uid:
        return False
    try:
        return len(uid.encode()) <= 256
    except UnicodeError:
        return False


_membership_resolver: Callable[..., bool] | None = None
_members_resolver: Callable[[str], tuple[str, ...]] | None = None
_load_resolver: Callable[[str], Any] | None = None
_warm_resolver: Callable[[str], Any] | None = None


def configured() -> bool:
    return _membership_resolver is not None


def configure_resolvers(
    membership, members, load, warm, *, env_readers: dict[str, Callable[[], str]] | None = None
) -> None:
    global _membership_resolver, _members_resolver, _load_resolver, _warm_resolver
    if env_readers is not None:
        COHORT_ENVS.update(env_readers)
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


# The free-tier policy retired in #22238. Retain its pure token grammar and
# stable bucket here for environment-owned rollouts, without its retired remote
# control plane or any database membership reads.
def parse_cohort(raw: str | None) -> tuple[frozenset[str], int] | None:
    """Parse uid:<uid>,pct:<integer 0..100>; explicit all is the sole wildcard.

    Empty or any malformed token denies the entire configuration.
    """
    if raw is None or not raw.strip():
        return None
    if raw.strip().lower() == 'all':
        return frozenset(), 100
    uids: set[str] = set()
    percent: int | None = None
    for token in raw.split(','):
        kind, sep, value = token.strip().partition(':')
        kind, value = kind.strip().lower(), value.strip()
        if not sep or not value:
            return None
        if kind == 'uid' and valid_uid(value):
            uids.add(value)
        elif kind == 'pct' and value.isascii() and value.isdigit():
            normalized = value.lstrip('0') or '0'
            if percent is not None or len(normalized) > 3 or int(normalized) > 100:
                return None
            percent = int(normalized)
        else:
            return None
    return frozenset(uids), percent or 0


def cohort_bucket(uid: str) -> int:
    """Existing free-tier-cohort salt/bucket; stable across hosts and widening."""
    return int(hashlib.sha256(('free-tier-cohort:' + uid).encode()).hexdigest()[:8], 16) % 100


def cohort_admits(uid: str, raw: str | None) -> bool:
    if not valid_uid(uid):
        return False
    parsed = parse_cohort(raw)
    return parsed is not None and (uid in parsed[0] or cohort_bucket(uid) < parsed[1])
