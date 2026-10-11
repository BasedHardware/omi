"""Whether the summary scheduler can actually serve a reported zone.

Validators and the scheduler disagree when they check different tz
databases: zoneinfo follows the host's /usr/share/zoneinfo while
every consumer (hour-grouped recipient queries, day bounds, recap routes)
runs on pytz. A zone the host knows but the pinned pytz build does not
is accepted, stored, and then silently never scheduled. pytz is the
authority — it is what the schedule runs on.
"""

import pytz


def is_schedulable_time_zone(name: str) -> bool:
    """True when pytz — the scheduler's tz library — can load name."""
    if not name or not isinstance(name, str):
        return False
    try:
        pytz.timezone(name.strip())
        return True
    except Exception:
        return False
