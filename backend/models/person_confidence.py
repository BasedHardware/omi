"""How sure Omi is about a person's voice, from what the user actually did.

Pure: no IO, no imports beyond the standard library (``models`` must stay importable
where ``utils`` is stubbed). The person document keeps a small ``label_evidence``
tally; ``utils.person_evidence`` owns how one assignment changes it. This module owns
the tally's counter names and the single mapping from a tally to a confidence band
and its reasons. Automatic matches nobody confirmed never raise a band: only the
user's answers do.
"""

from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Tuple

# Counter keys stored under ``people/{id}.label_evidence``.
MANUAL_LABELS = 'manual_labels'  # labeled by hand in a transcript (strong)
CARD_CONFIRMS = 'card_confirms'  # "Yes" on a suggestion card that asked about an automatic match (medium)
CARD_PICKS = 'card_picks'  # picked on a suggestion card for an unnamed voice (medium)
AUTO_CONFIRMED = 'auto_confirmed'  # labeled by hand where Omi had already matched them (small)
AUTO_CORRECTED = 'auto_corrected'  # an automatic match to them the user moved elsewhere (negative)
COUNTERS = (MANUAL_LABELS, CARD_CONFIRMS, CARD_PICKS, AUTO_CONFIRMED, AUTO_CORRECTED)

# Where a manual assignment came from.
SOURCE_MANUAL = 'manual'
SOURCE_CARD = 'card'

WEIGHTS = {MANUAL_LABELS: 3, CARD_CONFIRMS: 2, CARD_PICKS: 2, AUTO_CONFIRMED: 1, AUTO_CORRECTED: -2}
VOICE_READY_POINTS = 1
LIKELY_POINTS = 2
CONFIRMED_POINTS = 6
# Each counted event is keyed ``kind:conversation_id`` so a retried or repeated
# assignment in one conversation counts once. Newest last; bounded.
COUNTED_KEYS_LIMIT = 200


class Band:
    unknown = 'unknown'
    confirmed = 'confirmed'
    likely = 'likely'
    unverified = 'unverified'


@dataclass(frozen=True)
class Confidence:
    band: str
    reasons: List[Tuple[str, int]]
    # Hand labels still needed to reach Confirmed (None once Confirmed or when a voice sample is the blocker).
    labels_to_confirm: Optional[int]
    needs_voice: bool


def evidence_count(evidence: Mapping[str, Any], key: str) -> int:
    value = evidence.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def confidence_points(evidence: Mapping[str, Any], voice_ready: bool) -> int:
    points = sum(WEIGHTS[key] * evidence_count(evidence, key) for key in COUNTERS)
    return points + (VOICE_READY_POINTS if voice_ready else 0)


def person_confidence(
    evidence: Optional[Mapping[str, Any]],
    *,
    voice_ready: bool,
    conversation_count: Optional[int] = None,
    auto_conversation_count: Optional[int] = None,
) -> Confidence:
    """The one band + reasons mapping. Stats (conversation counts) only add reasons, never move the band."""
    if not isinstance(evidence, Mapping) or any(
        key in evidence and (type(evidence[key]) is not int or evidence[key] < 0) for key in COUNTERS
    ):
        return Confidence(band=Band.unknown, reasons=[], labels_to_confirm=None, needs_voice=not voice_ready)
    backed = sum(evidence_count(evidence, key) for key in (MANUAL_LABELS, CARD_CONFIRMS, CARD_PICKS, AUTO_CONFIRMED))
    points = confidence_points(evidence, voice_ready)
    if backed and points >= CONFIRMED_POINTS and voice_ready:
        band = Band.confirmed
    elif backed and points >= LIKELY_POINTS:
        band = Band.likely
    else:
        band = Band.unverified

    reasons: List[Tuple[str, int]] = []
    for key in (MANUAL_LABELS, CARD_CONFIRMS, CARD_PICKS, AUTO_CONFIRMED, AUTO_CORRECTED):
        if evidence_count(evidence, key):
            reasons.append((key, evidence_count(evidence, key)))
    reasons.append(('voice_ready', 1) if voice_ready else ('needs_voice', 1))
    if auto_conversation_count:
        reasons.append(('auto_unconfirmed', auto_conversation_count))
    if conversation_count == 0:
        reasons.append(('not_heard', 1))
    if not backed:
        reasons.append(('never_confirmed', 1))

    labels_to_confirm: Optional[int] = None
    if band != Band.confirmed:
        # A voice sample, once ready, adds its point; count only the labels still short.
        missing = CONFIRMED_POINTS - points - (0 if voice_ready else VOICE_READY_POINTS)
        labels = -(-missing // WEIGHTS[MANUAL_LABELS]) if missing > 0 else 0
        if not backed:
            labels = max(labels, 1)
        labels_to_confirm = labels or None
    return Confidence(band=band, reasons=reasons, labels_to_confirm=labels_to_confirm, needs_voice=not voice_ready)
