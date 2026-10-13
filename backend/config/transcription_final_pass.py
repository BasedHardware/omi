"""Default-off final-pass rollout policy, evaluated at admission and commit."""

import hashlib
import os


def enabled_for(uid: str) -> bool:
    if os.getenv('TRANSCRIPTION_FINAL_PASS_DIARIZER', 'legacy') != 'pyannote_shadow':
        return False
    allowlist = {s.strip() for s in os.getenv('TRANSCRIPTION_FINAL_PASS_UID_ALLOWLIST', '').split(',') if s.strip()}
    percent = max(0.0, min(100.0, float(os.getenv('TRANSCRIPTION_FINAL_PASS_PERCENT', '0'))))
    bucket = int.from_bytes(hashlib.sha256(uid.encode()).digest()[:4], 'big') / 2**32 * 100
    return uid in allowlist or bucket < percent


def authoritative_for(uid: str) -> bool:
    return enabled_for(uid) and os.getenv('TRANSCRIPTION_FINAL_PASS_AUTHORITATIVE', 'false').lower() == 'true'


def sync_enabled_for(uid: str) -> bool:
    return enabled_for(uid) and os.getenv('TRANSCRIPTION_FINAL_PASS_SYNC_ENABLED', 'false').lower() == 'true'
