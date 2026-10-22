"""Occasion conversations: for episodes beta users, a live conversation is the occasion.

Product ruling (David, 2026-10-22, from four blind labeling rounds on his own week): real content up
to ~45 min apart is almost always one occasion, and noise should be dropped, not stitched in. So
instead of splitting on two minutes of silence and stitching fragments back together afterwards, the
live conversation itself stays open across lulls and reconnects for the occasion window, gets one
notes pass at its end, and never needs a merge. Noise that stands apart becomes its own short
conversation and is discarded by relevance as today.

- ``OCCASION_CONVERSATIONS_ENABLED``: kill switch, on unless set off (``0``/``false``/``off``/``no``).
- Admission: the episodes cohort plus a capable client (``utils.episodes.client_gate``), so only
  users whose app shows episodes change behavior.
- ``OCCASION_GAP_SECONDS``: the silence window. A user's own longer timeout setting still wins.
- ``OCCASION_MAX_SPAN_SECONDS``: a hard cap on one conversation's span (smart merge's cap), so
  all-day ambient capture still rolls over and stays under the document size limit.
"""

from __future__ import annotations

import os

OCCASION_CONVERSATIONS_ENABLED_ENV = 'OCCASION_CONVERSATIONS_ENABLED'
OCCASION_GAP_SECONDS = 15 * 60
OCCASION_MAX_SPAN_SECONDS = 3 * 60 * 60

_OFF = frozenset({'0', 'false', 'off', 'no'})


def occasion_conversations_enabled() -> bool:
    return (os.getenv(OCCASION_CONVERSATIONS_ENABLED_ENV) or '').strip().lower() not in _OFF


def occasion_timeout(timeout: int) -> int:
    """The silence window for an admitted session: at least the occasion gap."""
    return max(int(timeout), OCCASION_GAP_SECONDS)
