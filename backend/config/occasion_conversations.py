"""Occasion conversations: for episodes beta users, a live conversation is the occasion.

Product ruling (David, 2026-10-22, from four blind labeling rounds on his own week): real content up
to ~45 min apart is almost always one occasion, and noise should be dropped, not stitched in. So
instead of splitting on two minutes of silence and stitching fragments back together afterwards, the
live conversation itself stays open across lulls and reconnects for the occasion window, gets one
notes pass at its end, and never needs a merge. Noise that stands apart becomes its own short
conversation and is discarded by relevance as today.

- ``OCCASION_CONVERSATIONS_ENABLED`` (env): the one operator lever, a kill switch that is on unless
  set off (``0``/``false``/``off``/``no``), like the other ship-on-by-default switches.
- Admission: the episodes cohort plus a capable client (``utils.episodes.client_gate``), and only for
  the mobile app's own capture: desktop listen sockets keep today's behavior even for the cohort.
- ``OCCASION_GAP_SECONDS`` (constant, not env): the silence window. A user's own longer timeout
  setting still wins.
- ``OCCASION_MAX_SPAN_SECONDS`` (constant, not env): a hard cap on one conversation's span (smart
  merge's cap), so all-day ambient capture still rolls over and stays under the document size limit.
"""

from __future__ import annotations

import os

OCCASION_CONVERSATIONS_ENABLED_ENV = 'OCCASION_CONVERSATIONS_ENABLED'
OCCASION_GAP_SECONDS = 15 * 60
OCCASION_MAX_SPAN_SECONDS = 3 * 60 * 60

_OFF = frozenset({'0', 'false', 'off', 'no'})
# Sources whose clients do not show episodes; their conversations keep today's boundaries.
_NOT_OCCASION_SOURCES = frozenset({'desktop'})


def occasion_conversations_enabled() -> bool:
    return (os.getenv(OCCASION_CONVERSATIONS_ENABLED_ENV) or '').strip().lower() not in _OFF


def occasion_source(source: object) -> bool:
    """Whether a listen session from this source may be an occasion (mobile app capture only)."""
    value = getattr(source, 'value', source)
    return isinstance(value, str) and value not in _NOT_OCCASION_SOURCES


def occasion_timeout(timeout: int) -> int:
    """The silence window for an admitted session: at least the occasion gap."""
    return max(int(timeout), OCCASION_GAP_SECONDS)


# Explicit rollout bindings for inventory and operators. The generic parser in
# refactor_modes owns every read, including the two suffixes derived from a mode.
EPISODE_BOUNDARIES_MODE_ENV = 'EPISODE_BOUNDARIES_MODE'
EPISODE_BOUNDARIES_PERCENT_ENV = 'EPISODE_BOUNDARIES_MODE_SERVE_PERCENT'
EPISODE_BOUNDARIES_DIGESTS_ENV = 'EPISODE_BOUNDARIES_MODE_SERVE_UID_SHA256S'
LIFECYCLE_V2_MODE_ENV = 'LIFECYCLE_V2_MODE'
LIFECYCLE_V2_PERCENT_ENV = 'LIFECYCLE_V2_MODE_SERVE_PERCENT'
LIFECYCLE_V2_DIGESTS_ENV = 'LIFECYCLE_V2_MODE_SERVE_UID_SHA256S'
