"""Default-on kill switches for pre-recorded vendor resilience."""

from config.refactor_switches import default_on as rollout_default_on

import os


def vendor_fail_fast_enabled() -> bool:
    # Only the explicit kill value restores the old retry behaviour; malformed values stay safe.
    return rollout_default_on(
        'STT_PRERECORDED_VENDOR_FAIL_FAST',
        os.getenv('STT_PRERECORDED_VENDOR_FAIL_FAST', 'true').strip().lower() != 'false',
    )


def soniox_failover_enabled() -> bool:
    """Unset stays on; only literal false restores Modulate-only pre-recorded STT."""
    return rollout_default_on(
        'PRERECORDED_SONIOX_FAILOVER_ENABLED',
        os.getenv('PRERECORDED_SONIOX_FAILOVER_ENABLED', 'true').strip().lower() != 'false',
    )


def soniox_multilingual_enabled() -> bool:
    """Ship-on kill switch: legacy sync's multilingual audio goes to Soniox first, Velma on any Soniox failure.

    Only literal false restores Velma-first for every pre-recorded caller (SCA-4917)."""
    return rollout_default_on(
        'STT_PRERECORDED_SONIOX_MULTILINGUAL_ENABLED',
        os.getenv('STT_PRERECORDED_SONIOX_MULTILINGUAL_ENABLED', 'true').strip().lower() != 'false',
    )
