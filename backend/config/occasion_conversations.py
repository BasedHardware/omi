"""Occasion conversations: for episodes beta users, a live conversation is the occasion.

Product ruling (David, 2026-10-22, from four blind labeling rounds on his own week): real content up
to ~45 min apart is almost always one occasion, and noise should be dropped, not stitched in. So
instead of splitting on two minutes of silence and stitching fragments back together afterwards, the
live conversation itself stays open across lulls and reconnects for the occasion window, gets one
notes pass at its end, and never needs a merge. Noise that stands apart becomes its own short
conversation and is discarded by relevance as today.

- ``OCCASION_CONVERSATIONS_ENABLED`` (env): the one operator lever, a kill switch that is on unless
  set off (``0``/``false``/``off``/``no``), like the other ship-on-by-default switches.
- ``LIVE_CONVERSATION_SIZE_ROLLOVER_ENABLED`` (env): kill switch (on unless set off) for live
  conversation rollover at ~768 KiB / 1,500 segments so long meetings split before Firestore's 1 MiB ceiling.
- Admission: the episodes cohort plus a capable client (``utils.episodes.client_gate``), and only for
  the mobile app's own capture: desktop listen sockets keep today's behavior even for the cohort.
- ``OCCASION_GAP_SECONDS`` (constant, not env): the silence window. A user's own longer timeout
  setting still wins.
- ``OCCASION_MAX_SPAN_SECONDS`` (constant, not env): a hard cap on one conversation's span (smart
  merge's cap), so all-day ambient capture still rolls over and stays under the document size limit.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import os
from typing import Any

OCCASION_CONVERSATIONS_ENABLED_ENV = 'OCCASION_CONVERSATIONS_ENABLED'
LIVE_CONVERSATION_SIZE_ROLLOVER_ENABLED_ENV = 'LIVE_CONVERSATION_SIZE_ROLLOVER_ENABLED'
from config import recorded_time_tolerances as tolerances

OCCASION_GAP_SECONDS = tolerances.CLOSE_GAP_SECONDS
OCCASION_MAX_SPAN_SECONDS = tolerances.MAX_EPISODE_SECONDS
# Keep 256 KiB of headroom below Firestore's 1 MiB (1,048,576-byte) ceiling so
# finalization bindings, summaries, action items, app results, and outbox
# metadata can still commit without hitting InvalidArgument.
OCCASION_MAX_DOCUMENT_BYTES = 1_048_576 - 262_144
OCCASION_MAX_TRANSCRIPT_SEGMENTS = 1_500

_OFF = frozenset({'0', 'false', 'off', 'no'})
# Sources whose clients do not show episodes; their conversations keep today's boundaries.
_NOT_OCCASION_SOURCES = frozenset({'desktop'})


def occasion_conversations_enabled() -> bool:
    return (os.getenv(OCCASION_CONVERSATIONS_ENABLED_ENV) or '').strip().lower() not in _OFF


def live_conversation_size_rollover_enabled() -> bool:
    """Kill switch for live ~768 KiB / 1,500-segment rollover (on unless set off)."""
    return (os.getenv(LIVE_CONVERSATION_SIZE_ROLLOVER_ENABLED_ENV) or '').strip().lower() not in _OFF


def occasion_source(source: object) -> bool:
    """Whether a listen session from this source may be an occasion (mobile app capture only)."""
    value = getattr(source, 'value', source)
    return isinstance(value, str) and value not in _NOT_OCCASION_SOURCES


def occasion_timeout(timeout: int) -> int:
    """The silence window for an admitted session: at least the occasion gap."""
    return max(int(timeout), OCCASION_GAP_SECONDS)


def _segment_marker(segment: Any) -> tuple[Any, int]:
    if isinstance(segment, Mapping):
        text = segment.get('text')
        return (segment.get('id'), len(text) if isinstance(text, str) else 0)
    return (None, 0)


def estimate_live_conversation_bytes_incremental(
    conversation: Mapping[str, Any],
    document_path: str | None = None,
    state: dict[str, Any] | None = None,
) -> int:
    """Estimate a live conversation's Firestore byte size incrementally across ticks.

    Caches non-segment document overhead and the cumulative byte size of settled
    prefix segments in ``state`` so each lifecycle tick only sizes segments
    appended since the previous tick plus the active tail segment.
    """
    from utils.firestore_document_size import estimate_firestore_document_bytes, estimate_firestore_value_bytes

    if state is None:
        return estimate_firestore_document_bytes(conversation, document_path)

    segments = conversation.get('transcript_segments')
    cid = conversation.get('id')
    photos = conversation.get('photos')
    photos_len = len(photos) if isinstance(photos, Sequence) and not isinstance(photos, (str, bytes, bytearray)) else 0
    if state.get('conversation_id') != cid or state.get('document_path') != document_path:
        state.clear()
        state['conversation_id'] = cid
        state['document_path'] = document_path

    if (
        'non_segment_bytes' not in state
        or state.get('top_key_count') != len(conversation)
        or state.get('photos_len') != photos_len
    ):
        without_segments = {k: ([] if k == 'transcript_segments' else v) for k, v in conversation.items()}
        state['non_segment_bytes'] = estimate_firestore_document_bytes(without_segments, document_path)
        state['top_key_count'] = len(conversation)
        state['photos_len'] = photos_len

    if not isinstance(segments, Sequence) or isinstance(segments, (str, bytes, bytearray)) or len(segments) == 0:
        state['prefix_len'] = 0
        state['prefix_bytes'] = 0
        state['first_marker'] = None
        state['last_settled_marker'] = None
        return int(state['non_segment_bytes'])

    first_marker = _segment_marker(segments[0])
    prefix_len = int(state.get('prefix_len', 0))
    prefix_bytes = int(state.get('prefix_bytes', 0))
    if prefix_len > len(segments) - 1 or (
        prefix_len > 0
        and (
            state.get('first_marker') != first_marker
            or state.get('last_settled_marker') != _segment_marker(segments[prefix_len - 1])
        )
    ):
        prefix_len = 0
        prefix_bytes = 0

    new_prefix_len = len(segments) - 1
    if new_prefix_len > prefix_len:
        for seg in segments[prefix_len:new_prefix_len]:
            prefix_bytes += estimate_firestore_value_bytes(seg)
        prefix_len = new_prefix_len

    state['prefix_len'] = prefix_len
    state['prefix_bytes'] = prefix_bytes
    state['first_marker'] = first_marker
    state['last_settled_marker'] = _segment_marker(segments[prefix_len - 1]) if prefix_len > 0 else None
    tail_bytes = estimate_firestore_value_bytes(segments[-1])
    return int(state['non_segment_bytes']) + prefix_bytes + tail_bytes


def occasion_size_exceeded(
    conversation: Mapping[str, Any],
    document_path: str | None = None,
    *,
    state: dict[str, Any] | None = None,
) -> bool:
    """Whether a live conversation has reached the segment-count or byte-size rollover cap."""
    if not live_conversation_size_rollover_enabled():
        return False
    segments = conversation.get('transcript_segments')
    if (
        isinstance(segments, Sequence)
        and not isinstance(segments, (str, bytes, bytearray))
        and len(segments) >= OCCASION_MAX_TRANSCRIPT_SEGMENTS
    ):
        return True
    return (
        estimate_live_conversation_bytes_incremental(conversation, document_path, state) >= OCCASION_MAX_DOCUMENT_BYTES
    )


# Explicit rollout bindings for inventory and operators. The generic parser in
# refactor_modes owns every read, including the two suffixes derived from a mode.
EPISODE_BOUNDARIES_MODE_ENV = 'EPISODE_BOUNDARIES_MODE'
EPISODE_BOUNDARIES_PERCENT_ENV = 'EPISODE_BOUNDARIES_MODE_SERVE_PERCENT'
EPISODE_BOUNDARIES_DIGESTS_ENV = 'EPISODE_BOUNDARIES_MODE_SERVE_UID_SHA256S'
LIFECYCLE_V2_MODE_ENV = 'LIFECYCLE_V2_MODE'
LIFECYCLE_V2_PERCENT_ENV = 'LIFECYCLE_V2_MODE_SERVE_PERCENT'
LIFECYCLE_V2_DIGESTS_ENV = 'LIFECYCLE_V2_MODE_SERVE_UID_SHA256S'
