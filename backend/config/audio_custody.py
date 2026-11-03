"""Dark custody rollout; independent of the fleet archive cohort."""

import os

from config.policy.batch import cohort_bucket


def framed_pack(uid: str) -> bool:
    try:
        percent = float(os.getenv('AUDIO_CUSTODY_FRAMED_PERCENT', '0'))
    except ValueError:
        return False
    return bool(uid) and 0 < percent <= 100 and cohort_bucket(uid, 'audio-custody', bits=64) < percent
