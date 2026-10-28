"""Deterministic capture grouping rollout; no IO or import-time env snapshots."""

import math
import os

from config.policy.batch import cohort_bucket

MODE_ENV = 'CAPTURE_SHARED_SPEECH_MODE'
ALLOWLIST_ENV = 'CAPTURE_SHARED_SPEECH_UID_ALLOWLIST'
PERCENT_ENV = 'CAPTURE_SHARED_SPEECH_PERCENT'
MAX_CAPTURE_SEGMENTS = 4096
MAX_CAPTURE_CHARS = 524288
MAX_CAPTURE_SEGMENT_CHARS = 4096
MAX_STORED_TRANSCRIPT_BYTES = 1048576
MAX_DECODED_TRANSCRIPT_BYTES = 2097152


def shared_speech_mode(uid: str) -> str:
    mode = os.getenv(MODE_ENV, 'off').strip().lower()
    if mode not in {'shadow', 'on'}:
        return 'off'
    allowlist = {value.strip() for value in os.getenv(ALLOWLIST_ENV, '').split(',') if value.strip()}
    if uid in allowlist:
        return mode
    try:
        percent = float(os.getenv(PERCENT_ENV, '0'))
    except ValueError:
        return 'off'
    if not math.isfinite(percent) or not 0 <= percent <= 100:
        return 'off'
    bucket = cohort_bucket(uid, 'capture_shared_speech_v1', bits=64)
    return mode if bucket < percent else 'off'
