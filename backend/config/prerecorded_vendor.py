"""Kill switch for prerecorded vendor fail-fast (quota errors never retry)."""

from config.refactor_switches import default_on as rollout_default_on

import os


def vendor_fail_fast_enabled() -> bool:
    # Only the explicit kill value restores the old retry behaviour; malformed values stay safe.
    return rollout_default_on(
        'STT_PRERECORDED_VENDOR_FAIL_FAST',
        os.getenv('STT_PRERECORDED_VENDOR_FAIL_FAST', 'true').strip().lower() != 'false',
    )
