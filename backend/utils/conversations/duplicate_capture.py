"""Cross-device duplicate capture detection (#3244).

When an Omi device (paired to the phone app) and the macOS app both hear the
same room, the backend receives two independent ``/v4/listen`` streams. Each
stream owns its own conversation — cross-source sockets must never share one
(#5388), because the two captures can legitimately hold different audio (a
pendant in the room plus a headphone meeting on the laptop). Multi-device
recording therefore stays fully enabled; nothing is toggled off on any client.

What this module decides is narrower: at finalization, whether *this*
conversation's content is already carried by another capture client's
conversation. Only then is it folded away as a discarded duplicate (the
transcript and audio stay on the document, and the primary is recorded under
``external_data[DUPLICATE_CAPTURE_OF_KEY]``). The decision is content-based
and deterministic — it never infers a duplicate from device presence alone:

1. The other conversation belongs to a different capture client.
2. The other conversation's wall window covers at least
   ``MIN_WINDOW_COVERAGE`` of this one's and the overlap lasts at least
   ``MIN_OVERLAP_SECONDS``.
3. At least ``MIN_TRANSCRIPT_CONTAINMENT`` of this conversation's word bigrams
   also occur in the other transcript. Containment (not symmetric similarity)
   is deliberate: a capture that holds speech the other one lacks — the
   pendant hearing the user's side while the laptop only hears remote
   participants — keeps a low containment and survives as its own
   conversation. Bigrams tolerate the word-level disagreement two microphones
   and two STT passes produce while unrelated same-time conversations share
   only generic phrases.
4. Exactly one side yields. A ``completed`` counterpart is always primary; a
   ``processing`` counterpart is primary only when it was created earlier, so
   two sessions that time out on the same silence and finalize concurrently
   cannot both discard themselves or both survive.

Everything here is pure: callers load the candidate rows and persist the
outcome.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional, Sequence, cast

DUPLICATE_CAPTURE_OF_KEY = 'duplicate_capture_of'

# Below this the LLM discard gate owns the verdict; bigram statistics on a
# handful of words say nothing about whether two captures heard the same room.
MIN_CANDIDATE_WORDS = 30
MIN_OVERLAP_SECONDS = 30.0
# Fraction of the candidate's own wall window that the primary must cover. A
# pendant conversation that kept running long after the laptop stopped holds
# speech the laptop never captured and must not be folded into it.
MIN_WINDOW_COVERAGE = 0.8
# Fraction of the candidate's word bigrams (multiset) present in the primary.
MIN_TRANSCRIPT_CONTAINMENT = 0.5
# One bounded page per status. The candidate read is ordered by the activity
# clock from the candidate's start, so the overlapping captures come first;
# anything beyond the page finished long after it and cannot cover it.
CANDIDATE_PAGE_LIMIT = 25

_PRIMARY_ELIGIBLE_STATUSES = frozenset({'completed', 'processing'})
_WORD_RE = re.compile(r'[^\W_]+', re.UNICODE)


@dataclass(frozen=True)
class CaptureRecord:
    """The provenance, window, and words of one capture, independent of storage shape."""

    conversation_id: Optional[str]
    created_at: datetime
    started_at: datetime
    finished_at: datetime
    status: Optional[str]
    words: tuple[str, ...]
    source: Optional[str] = None
    client_device_id: Optional[str] = None
    client_platform: Optional[str] = None
    discarded: bool = False

    @property
    def duration_seconds(self) -> float:
        return max(0.0, (self.finished_at - self.started_at).total_seconds())


@dataclass(frozen=True)
class DuplicateCaptureMatch:
    primary_conversation_id: str
    window_coverage: float
    transcript_containment: float


def transcript_words(segments: Optional[Iterable[Any]]) -> tuple[str, ...]:
    """Lower-cased word tokens across segments (models or persisted dicts), in order."""
    words: list[str] = []
    for segment in segments or ():
        text = _field(segment, 'text')
        if not isinstance(text, str) or not text:
            continue
        words.extend(match.group(0).lower() for match in _WORD_RE.finditer(text))
    return tuple(words)


def _enum_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    value = getattr(value, 'value', value)
    return str(value) if value != '' else None


def _aware(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _field(record: Any, name: str) -> Any:
    if isinstance(record, Mapping):
        return cast(Mapping[str, Any], record).get(name)
    return getattr(record, name, None)


def capture_record(record: Any) -> Optional[CaptureRecord]:
    """Project a conversation (model or Firestore dict) onto a ``CaptureRecord``.

    Returns ``None`` when the record has no usable wall window — such a row can
    neither be judged a duplicate nor serve as a primary.
    """
    started_at = _aware(_field(record, 'started_at'))
    finished_at = _aware(_field(record, 'finished_at'))
    if started_at is None or finished_at is None or finished_at < started_at:
        return None
    created_at = _aware(_field(record, 'created_at')) or started_at
    conversation_id = _field(record, 'id')
    return CaptureRecord(
        conversation_id=str(conversation_id) if conversation_id else None,
        created_at=created_at,
        started_at=started_at,
        finished_at=finished_at,
        status=_enum_value(_field(record, 'status')),
        words=transcript_words(_field(record, 'transcript_segments')),
        source=_enum_value(_field(record, 'source')),
        client_device_id=_enum_value(_field(record, 'client_device_id')),
        client_platform=_enum_value(_field(record, 'client_platform')),
        discarded=bool(_field(record, 'discarded')),
    )


def same_capture_client(a: CaptureRecord, b: CaptureRecord) -> bool:
    """Whether two records were produced by one capture client.

    The device hash is authoritative when both sides carry it. Legacy rows
    without it fall back to the platform/source pair, which errs toward "same"
    for a reconnecting client whose provenance is unknown.
    """
    if a.client_device_id and b.client_device_id:
        return a.client_device_id == b.client_device_id
    return (a.client_platform, a.source) == (b.client_platform, b.source)


def window_coverage(candidate: CaptureRecord, other: CaptureRecord) -> tuple[float, float]:
    """``(overlap_seconds, fraction of the candidate's window that overlap covers)``."""
    overlap = (
        min(candidate.finished_at, other.finished_at) - max(candidate.started_at, other.started_at)
    ).total_seconds()
    if overlap <= 0:
        return 0.0, 0.0
    duration = candidate.duration_seconds
    if duration <= 0:
        return overlap, 0.0
    return overlap, min(1.0, overlap / duration)


def bigram_containment(candidate_words: Sequence[str], other_words: Sequence[str]) -> float:
    """Fraction of the candidate's word bigrams (with multiplicity) present in ``other_words``."""
    if len(candidate_words) < 2 or len(other_words) < 2:
        return 0.0
    candidate_bigrams = Counter(zip(candidate_words, candidate_words[1:]))
    other_bigrams = Counter(zip(other_words, other_words[1:]))
    shared = sum(min(count, other_bigrams[bigram]) for bigram, count in candidate_bigrams.items())
    return shared / sum(candidate_bigrams.values())


def is_primary_eligible(candidate: CaptureRecord, other: CaptureRecord) -> bool:
    """Whether ``other`` may absorb ``candidate`` (rule 4 in the module docstring)."""
    if other.discarded or not other.conversation_id or other.status not in _PRIMARY_ELIGIBLE_STATUSES:
        return False
    if other.conversation_id == candidate.conversation_id:
        return False
    if other.status == 'completed':
        return True
    return (other.created_at, other.conversation_id) < (candidate.created_at, candidate.conversation_id or '')


def mark_duplicate_capture(conversation: Any, match: DuplicateCaptureMatch) -> None:
    """Record the primary on the conversation model that is about to be discarded.

    ``external_data`` rides the same persist as the discard flag (``dict()`` on
    both the live and the ingress-create model), so pointer and verdict land in
    one write.
    """
    external_data = dict(getattr(conversation, 'external_data', None) or {})
    external_data[DUPLICATE_CAPTURE_OF_KEY] = match.primary_conversation_id
    conversation.external_data = external_data


def find_duplicate_capture(
    candidate: CaptureRecord,
    others: Iterable[CaptureRecord],
    *,
    min_candidate_words: int = MIN_CANDIDATE_WORDS,
    min_overlap_seconds: float = MIN_OVERLAP_SECONDS,
    min_window_coverage: float = MIN_WINDOW_COVERAGE,
    min_transcript_containment: float = MIN_TRANSCRIPT_CONTAINMENT,
) -> Optional[DuplicateCaptureMatch]:
    """Return the primary that already carries ``candidate``, or ``None`` to keep it."""
    if candidate.discarded or len(candidate.words) < min_candidate_words:
        return None
    best: Optional[DuplicateCaptureMatch] = None
    for other in others:
        if not is_primary_eligible(candidate, other) or same_capture_client(candidate, other):
            continue
        overlap_seconds, coverage = window_coverage(candidate, other)
        if overlap_seconds < min_overlap_seconds or coverage < min_window_coverage:
            continue
        containment = bigram_containment(candidate.words, other.words)
        if containment < min_transcript_containment:
            continue
        match = DuplicateCaptureMatch(
            primary_conversation_id=other.conversation_id or '',
            window_coverage=coverage,
            transcript_containment=containment,
        )
        if best is None or (match.transcript_containment, match.window_coverage) > (
            best.transcript_containment,
            best.window_coverage,
        ):
            best = match
    return best
