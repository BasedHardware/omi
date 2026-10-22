"""As-captured audio archive phases.

LIVE and READ are the fleet as-captured dual-write (David's 2026-10-22 ruling):
on by default, flag-only, no percent cohort. The remaining phases stay staged
dark rollouts behind their flag plus a percent cohort.
"""

import hashlib
import os

from config.rollout_cohorts import in_rollout_cohort
import logging

logger = logging.getLogger(__name__)


def _phase_enabled(phase: str) -> bool:
    # LIVE and READ default on: the raw Opus archive must exist wherever the
    # kill switch is not explicitly disabled. A default-off fleet phase would
    # leave the as-captured ruling unimplemented on every service that has not
    # pinned the env.
    if phase == 'LIVE':
        return os.getenv('AUDIO_ARCHIVE_LIVE_ENABLED', 'true').lower() == 'true'
    if phase == 'READ':
        return os.getenv('AUDIO_ARCHIVE_READ_ENABLED', 'true').lower() == 'true'
    if phase == 'STOP_PCM':
        return os.getenv('AUDIO_ARCHIVE_STOP_PCM_ENABLED', 'false').lower() == 'true'
    if phase == 'SYNC':
        return os.getenv('AUDIO_ARCHIVE_SYNC_ENABLED', 'false').lower() == 'true'
    if phase == 'REGIONAL_CACHE':
        return os.getenv('AUDIO_ARCHIVE_REGIONAL_CACHE_ENABLED', 'false').lower() == 'true'
    if phase == 'COALESCE':
        return os.getenv('AUDIO_ARCHIVE_COALESCE_ENABLED', 'false').lower() == 'true'
    if phase == 'SEPARATE_MERGE':
        return os.getenv('AUDIO_ARCHIVE_SEPARATE_MERGE_ENABLED', 'false').lower() == 'true'
    return False


def _cohort_percent(phase: str) -> float | None:
    # STOP_PCM ramps against its own percent: AUDIO_ARCHIVE_PERCENT is pinned
    # at 100 fleet-wide for COALESCE, so a shared knob could not hold STOP_PCM
    # back without breaking merge coalescing.
    if phase == 'STOP_PCM':
        raw = os.getenv('AUDIO_ARCHIVE_STOP_PCM_PERCENT', '0')
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
    bucket = int.from_bytes(hashlib.sha256(('audio-archive:' + uid).encode()).digest()[:8], 'big') / 2**64
    return in_rollout_cohort(uid, 'audio-archive') or bucket * 100 < percent


def regional_bucket(uid: str, legacy: str | None) -> str | None:
    if admitted(uid, 'REGIONAL_CACHE'):
        configured = os.getenv('BUCKET_AUDIO_DERIVED', '').strip()
        if not configured:
            logger.warning('regional audio cache missing BUCKET_AUDIO_DERIVED; retaining legacy bucket')
            return legacy
        return configured
    return legacy
