"""Sticky episode-note admission; invalid configuration always keeps baseline."""

import hashlib
import math
import os


def episode_notes_cohort(uid: object) -> bool:
    if not uid or not isinstance(uid, str):
        return False
    try:
        share = float(os.getenv('MEETING_NOTES_EPISODE_EVIDENCE_PERCENT', '0'))
    except (TypeError, ValueError):
        return False
    if not math.isfinite(share) or not 0 <= share <= 100:
        return False
    try:
        bucket = int.from_bytes(hashlib.sha256(f'episode-notes-v1:{uid}'.encode()).digest()[:8], 'big')
    except UnicodeError:
        return False
    return bucket / 2**64 * 100 < share
