"""A recording row stays on one side of every End (reliability experiment ``end_open_conversation``).

Pure helpers shared by the End code (``manual_cuts.ends_around`` reads the Ends) and the attach step
(``utils/sync/assignment.py`` applies them). No imports beyond the standard library, so the attach step
can use it without pulling in the builder.
"""

from datetime import datetime, timezone

# Private key on an uploaded unit's projection input: the pair ``manual_cuts.ends_around`` returned.
# The attach step pops it; it is never stored.
ATTACH_KEY = '_v3_end_cuts'


def separated_by_end(row_started_at, ends) -> bool:
    """Whether an End lies between a recording row's start and the unit this pair of Ends was read for.

    ``ends`` is (last End at or before the unit's first speech, first End after it), either may be None.
    A row that began before the earlier End, or at or after the later one, is on another side.
    """
    if not ends or not isinstance(row_started_at, datetime):
        return False
    before, after = ends
    start = row_started_at if row_started_at.tzinfo else row_started_at.replace(tzinfo=timezone.utc)
    return (before is not None and start < before) or (after is not None and start >= after)
