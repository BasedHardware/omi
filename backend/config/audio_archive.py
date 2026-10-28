"""As-captured audio archive phases.

LIVE and READ are the fleet as-captured dual-write (David's 2026-10-22 ruling):
on by default, flag-only, no percent cohort. The remaining phases stay staged
dark rollouts behind their flag plus a percent cohort.
"""

from config.refactor_switches import default_off as rollout_default_off, default_on as rollout_default_on

import os

from config.policy.batch import cohort_bucket

from config.rollout_cohorts import in_rollout_cohort
import logging

logger = logging.getLogger(__name__)


def _phase_enabled(phase: str) -> bool:
    # LIVE controls legacy admission after AUDIO_DURABLE_OUTBOX_ENABLED=false;
    # the default-on custody path deliberately uses its own sole kill switch.
    # LIVE and READ default on: the raw Opus archive must exist wherever the
    # kill switch is not explicitly disabled. A default-off fleet phase would
    # leave the as-captured ruling unimplemented on every service that has not
    # pinned the env.
    if phase == 'LIVE':
        return rollout_default_on(
            'AUDIO_ARCHIVE_LIVE_ENABLED', os.getenv('AUDIO_ARCHIVE_LIVE_ENABLED', 'true').lower() == 'true'
        )
    if phase == 'READ':
        return rollout_default_on(
            'AUDIO_ARCHIVE_READ_ENABLED', os.getenv('AUDIO_ARCHIVE_READ_ENABLED', 'true').lower() == 'true'
        )
    if phase == 'STOP_PCM':
        return rollout_default_off(
            'AUDIO_ARCHIVE_STOP_PCM_ENABLED', os.getenv('AUDIO_ARCHIVE_STOP_PCM_ENABLED', 'false').lower() == 'true'
        )
    if phase == 'SYNC':
        return rollout_default_off(
            'AUDIO_ARCHIVE_SYNC_ENABLED', os.getenv('AUDIO_ARCHIVE_SYNC_ENABLED', 'false').lower() == 'true'
        )
    if phase == 'REGIONAL_CACHE':
        return rollout_default_off(
            'AUDIO_ARCHIVE_REGIONAL_CACHE_ENABLED',
            os.getenv('AUDIO_ARCHIVE_REGIONAL_CACHE_ENABLED', 'false').lower() == 'true',
        )
    if phase == 'COALESCE':
        return rollout_default_off(
            'AUDIO_ARCHIVE_COALESCE_ENABLED', os.getenv('AUDIO_ARCHIVE_COALESCE_ENABLED', 'false').lower() == 'true'
        )
    if phase == 'SEPARATE_MERGE':
        return rollout_default_off(
            'AUDIO_ARCHIVE_SEPARATE_MERGE_ENABLED',
            os.getenv('AUDIO_ARCHIVE_SEPARATE_MERGE_ENABLED', 'false').lower() == 'true',
        )
    return False


def _cohort_percent(phase: str) -> float | None:
    # STOP_PCM and REGIONAL_CACHE ramp against their own percent:
    # AUDIO_ARCHIVE_PERCENT is pinned at 100 fleet-wide for COALESCE, so a
    # shared knob could not hold either phase back without breaking merge
    # coalescing — and for REGIONAL_CACHE it would make the enable flag an
    # instant 100% cutover with no ramp.
    if phase == 'STOP_PCM':
        raw = os.getenv('AUDIO_ARCHIVE_STOP_PCM_PERCENT', '0')
    elif phase == 'REGIONAL_CACHE':
        raw = os.getenv('AUDIO_ARCHIVE_REGIONAL_CACHE_PERCENT', '0')
    else:
        raw = os.getenv('AUDIO_ARCHIVE_PERCENT', '0')
    try:
        percent = float(raw)
    except ValueError:
        return None
    return percent if 0 <= percent <= 100 else None


def admitted(uid: str, phase: str) -> bool:
    if not _phase_enabled(phase) or not uid:
        return False
    if phase in ('LIVE', 'READ'):
        # Fleet phases: the flag alone admits; a percent cohort here would
        # silently keep LIVE dark wherever AUDIO_ARCHIVE_PERCENT is unset.
        return True
    percent = _cohort_percent(phase)
    if percent is None:
        return False
    bucket = cohort_bucket(uid, 'audio-archive', bits=64)
    return in_rollout_cohort(uid, 'audio-archive') or bucket < percent


def regional_bucket(uid: str, legacy: str | None) -> str | None:
    if admitted(uid, 'REGIONAL_CACHE'):
        configured = os.getenv('BUCKET_AUDIO_DERIVED', '').strip()
        if not configured:
            logger.warning('regional audio cache missing BUCKET_AUDIO_DERIVED; retaining legacy bucket')
            return legacy
        return configured
    return legacy
