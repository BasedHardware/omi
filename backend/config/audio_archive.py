"""Independent, dark-by-default capture and cache rollout stages."""

import hashlib
import os


def admitted(uid: str, phase: str) -> bool:
    if os.getenv(f'AUDIO_ARCHIVE_{phase}_ENABLED', 'false').lower() != 'true' or not uid:
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
            raise RuntimeError('regional audio cache enabled without BUCKET_AUDIO_DERIVED')
        return configured
    return legacy
