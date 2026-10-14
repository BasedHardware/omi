"""Independent, dark-by-default capture and cache rollout stages."""

import hashlib
import os
import logging

logger = logging.getLogger(__name__)


def _phase_enabled(phase: str) -> bool:
    if phase == 'LIVE':
        return os.getenv('AUDIO_ARCHIVE_LIVE_ENABLED', 'false').lower() == 'true'
    if phase == 'READ':
        return os.getenv('AUDIO_ARCHIVE_READ_ENABLED', 'false').lower() == 'true'
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


def admitted(uid: str, phase: str) -> bool:
    if not _phase_enabled(phase) or not uid:
        return False
    allowlist = {item.strip() for item in os.getenv('AUDIO_ARCHIVE_UID_ALLOWLIST', '').split(',') if item.strip()}
    try:
        percent = float(os.getenv('AUDIO_ARCHIVE_PERCENT', '0'))
    except ValueError:
        return False
    if not 0 <= percent <= 100:
        return False
    bucket = int.from_bytes(hashlib.sha256(('audio-archive:' + uid).encode()).digest()[:8], 'big') / 2**64
    return uid in allowlist or bucket * 100 < percent


def regional_bucket(uid: str, legacy: str | None) -> str | None:
    if admitted(uid, 'REGIONAL_CACHE'):
        configured = os.getenv('BUCKET_AUDIO_DERIVED', '').strip()
        if not configured:
            logger.warning('regional audio cache missing BUCKET_AUDIO_DERIVED; retaining legacy bucket')
            return legacy
        return configured
    return legacy
