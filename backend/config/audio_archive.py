"""Independent, dark-by-default capture and cache rollout stages."""

from config.refactor_switches import default_off as rollout_default_off

import os

from config.policy.batch import cohort_bucket

from config.rollout_cohorts import in_rollout_cohort
import logging

logger = logging.getLogger(__name__)


def _phase_enabled(phase: str) -> bool:
    if phase == 'LIVE':
        return rollout_default_off(
            'AUDIO_ARCHIVE_LIVE_ENABLED', os.getenv('AUDIO_ARCHIVE_LIVE_ENABLED', 'false').lower() == 'true'
        )
    if phase == 'READ':
        return rollout_default_off(
            'AUDIO_ARCHIVE_READ_ENABLED', os.getenv('AUDIO_ARCHIVE_READ_ENABLED', 'false').lower() == 'true'
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


def admitted(uid: str, phase: str) -> bool:
    if not _phase_enabled(phase) or not uid:
        return False
    try:
        percent = float(os.getenv('AUDIO_ARCHIVE_PERCENT', '0'))
    except ValueError:
        return False
    if not 0 <= percent <= 100:
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
