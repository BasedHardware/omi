"""Default-off final-pass rollout policy, evaluated at admission and commit."""

from config.refactor_switches import default_off as rollout_default_off

import os

from config.policy.batch import cohort_bucket

from config.rollout_cohorts import in_rollout_cohort


def enabled_for(uid: str) -> bool:
    if os.getenv('TRANSCRIPTION_FINAL_PASS_DIARIZER', 'legacy') != 'pyannote_shadow':
        return False
    percent = max(0.0, min(100.0, float(os.getenv('TRANSCRIPTION_FINAL_PASS_PERCENT', '0'))))
    bucket = cohort_bucket(uid, '')
    return in_rollout_cohort(uid, 'transcription-final-pass') or bucket < percent


def authoritative_for(uid: str) -> bool:
    return enabled_for(uid) and rollout_default_off(
        'TRANSCRIPTION_FINAL_PASS_AUTHORITATIVE',
        os.getenv('TRANSCRIPTION_FINAL_PASS_AUTHORITATIVE', 'false').lower() == 'true',
        uid=uid,
    )


def sync_enabled_for(uid: str) -> bool:
    return enabled_for(uid) and rollout_default_off(
        'TRANSCRIPTION_FINAL_PASS_SYNC_ENABLED',
        os.getenv('TRANSCRIPTION_FINAL_PASS_SYNC_ENABLED', 'false').lower() == 'true',
        uid=uid,
    )
