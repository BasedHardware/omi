"""Timezone admission, owned by the model layer.

The daily-summary scheduler and the recap readers are all built on ``pytz``:
``_get_timezones_grouped_by_hour`` iterates ``pytz.all_timezones`` to build the
recipient query, and ``local_day_bounds_utc`` / ``_display_date_for_now`` call
``pytz.timezone``. A zone the backend admits via ``zoneinfo.ZoneInfo`` but
``pytz`` rejects (zones added after the pinned ``pytz==2024.1`` tz database such
as ``America/Coyhaique``, plus ``Factory`` and ``localtime``) is stored but never
selected, so the owner silently never receives a recap. Admission must be checked
against ``pytz`` — the reader's authority — not the host tz database.

This lives under ``models`` rather than ``utils`` because ``models/other.py``
imports it: ``utils`` reaches back into ``models`` at module scope across the
backend, so ``models`` must never import ``utils`` — and unit suites stub
``utils`` with an empty ``__path__``, which makes any ``models`` -> ``utils``
import fail at collection. The predicate is pure — ``pytz`` plus ``typing``
only — so it keeps the model layer importable wherever ``utils`` is stubbed.
"""

from typing import Optional

import pytz


def is_schedulable_time_zone(name: Optional[str]) -> bool:
    """True when ``pytz`` accepts ``name`` (the scheduler/reader authority)."""
    if not name:
        return False
    try:
        pytz.timezone(name)
        return True
    except Exception:
        return False
