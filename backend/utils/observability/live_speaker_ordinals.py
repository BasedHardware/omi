"""Live per-session unnamed-speaker ordinal churn, observed once when a listen session closes.

#23533 defers a live ordinal until an unnamed voice holds MIN_EVIDENCE_SECONDS of
non-overlapping placed speech; before that floor the voice renders "Unknown
speaker" and mints no ordinal. This metric answers whether that deferral actually
reduced the consecutive "Speaker 4, 5, 6, 7, 8" lines seen live: how many distinct
visible unnamed ordinals one session still mints, and how many speaker scope/epoch
rotations (provider transitions, reconnect epochs) the session spent. Rotations
re-key the same humans and re-mint their ordinals, so the pair separates label
churn from real multi-speaker conversations.

Qualification mirrors ``utils.speakers.display.display_participants`` with
``defer_short_voices=True``: the same voice key ``(speaker_id_scope, speaker_id)``,
the same five-second union of placed speech, and a voice the session named (owner
or person identity) never mints an ordinal. This is display bookkeeping only; it
never feeds speaker decisions.

Labels: none. Never uid, session or conversation identifiers.
"""

from __future__ import annotations

import logging
from math import isfinite
from typing import Any, Mapping, Optional

from prometheus_client import Counter, Histogram

from utils.speakers.policy import MIN_EVIDENCE_SECONDS

logger = logging.getLogger(__name__)

# Voice inventory ceiling, matching routers.listen.speakers.MAX_SPEAKER_VOICES;
# a session minting more unnamed voices than this is already collapsed to "Others"
# by the display layer's MAX_UNNAMED_VOICES guard.
MAX_TRACKED_VOICES = 128
# Per-voice merged placed-speech intervals while a voice is still below the
# evidence floor. Past this many disjoint bursts the tracker stops extending the
# union (under-counting errs toward "Unknown speaker", the same side as deferral).
MAX_VOICE_INTERVALS = 512

OMI_LIVE_SPEAKER_ORDINALS_PER_SESSION = Histogram(
    'omi_live_speaker_ordinals_per_session',
    'Distinct visible unnamed speaker ordinals one live listen session minted, '
    'after the #23533 short-voice deferral floor',
    buckets=(0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 13, 16, 24, 32),
)
OMI_LIVE_SPEAKER_SCOPE_ROTATIONS_TOTAL = Counter(
    'omi_live_speaker_scope_rotations_total',
    'Speaker scope/epoch rotations inside live listen sessions (provider transitions and '
    'reconnects), summed per session at close',
)


def _merge_interval(intervals: list[tuple[float, float]], span: tuple[float, float]) -> None:
    """Insert one span into a sorted, disjoint interval list, merging overlaps in place."""
    if len(intervals) >= MAX_VOICE_INTERVALS:
        return
    start, end = span
    merged: list[tuple[float, float]] = []
    placed = False
    for low, high in intervals:
        if high < start:
            merged.append((low, high))
        elif end < low:
            if not placed:
                merged.append((start, end))
                placed = True
            merged.append((low, high))
        else:
            start = min(start, low)
            end = max(end, high)
    if not placed:
        merged.append((start, end))
    intervals[:] = merged


class LiveSpeakerOrdinalTracker:
    """Per-session ordinal ledger. Event-loop confined, like the collapse monitor.

    Observe every final live segment (post scope-stamp and speaker-id assignment);
    close once at session teardown. Unplaced or malformed spans add no speech
    seconds, exactly like the display deferral's placement gate.
    """

    def __init__(self, min_evidence_seconds: float = MIN_EVIDENCE_SECONDS) -> None:
        self._min_evidence_seconds = min_evidence_seconds
        self._intervals: dict[tuple[str, int], list[tuple[float, float]]] = {}
        self._qualified: set[tuple[str, int]] = set()
        self._named: set[tuple[str, int]] = set()
        self._scopes: set[str] = set()

    def observe(self, segment: Mapping[str, Any]) -> None:
        speaker_id = segment.get('speaker_id')
        if isinstance(speaker_id, bool) or not isinstance(speaker_id, int):
            return
        scope = segment.get('speaker_id_scope')
        scope = scope if isinstance(scope, str) else ''
        if scope:
            self._scopes.add(scope)
        key = (scope, speaker_id)
        if segment.get('is_user') or segment.get('person_id'):
            self._named.add(key)
        if key in self._qualified:
            return
        start, end = segment.get('start'), segment.get('end')
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, (int, float))
            or not isinstance(end, (int, float))
        ):
            return
        start, end = float(start), float(end)
        if not (isfinite(start) and isfinite(end) and 0 <= start < end):
            return
        intervals = self._intervals.get(key)
        if intervals is None:
            if len(self._intervals) >= MAX_TRACKED_VOICES:
                return
            intervals = self._intervals[key] = []
        _merge_interval(intervals, (start, end))
        if sum(high - low for low, high in intervals) >= self._min_evidence_seconds:
            # Qualified: the ordinal is minted unless the voice is named by close.
            self._qualified.add(key)
            del self._intervals[key]

    def note_named_voices(self, matcher: Any) -> None:
        """Fold the matcher's final voice-to-person map into the named set."""
        mappings = getattr(matcher, 'speaker_to_person', None)
        if not isinstance(mappings, Mapping):
            return
        scopes = getattr(matcher, '_voice_scopes', None)
        scopes = scopes if isinstance(scopes, Mapping) else {}
        for voice in mappings:
            if isinstance(voice, int) and not isinstance(voice, bool):
                self._named.add((scopes.get(voice) or '', voice))

    def close(self) -> tuple[int, int]:
        """(minted unnamed ordinals, scope rotations) for the session; resets state."""
        ordinals = len(self._qualified - self._named)
        rotations = max(0, len(self._scopes) - 1)
        self._intervals.clear()
        self._qualified.clear()
        self._named.clear()
        self._scopes.clear()
        return ordinals, rotations


def record_live_speaker_ordinals(tracker: Optional[LiveSpeakerOrdinalTracker], matcher: Any) -> None:
    """Observe one ended listen session. Never raises: telemetry must not fail teardown."""
    try:
        if tracker is None:
            return
        tracker.note_named_voices(matcher)
        ordinals, rotations = tracker.close()
        OMI_LIVE_SPEAKER_ORDINALS_PER_SESSION.observe(ordinals)
        if rotations:
            OMI_LIVE_SPEAKER_SCOPE_ROTATIONS_TOTAL.inc(rotations)
    except Exception as error:
        logger.warning('Live speaker ordinal metric failed type=%s', type(error).__name__)
