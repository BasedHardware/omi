"""Upload filenames for router tests whose capture time must stay inside the recovery lookback."""

import time


def historical_capture_filename(age_days: int = 3) -> str:
    """A WAL filename a few days old: historical, yet always inside the 30-day automatic recovery lookback.

    A fixed epoch expires. ``omi_1792152000.bin`` (2026-10-16 12:00Z) left the window on 2026-11-15 12:00Z,
    and every router test that uploaded it began to receive 422 ``backfill_lookback_exceeded``.
    """
    return f'omi_{int(time.time()) - age_days * 86400}.bin'
