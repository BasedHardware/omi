"""Evidence gating for LLM-proposed speaker identities.

``detect_speaker_from_text`` recognises a person only when they announce
themselves in one of a fixed set of regex shapes. An LLM reading the finalized
transcript can resolve far more ("thanks, Alex" two turns later, a name the
user already has a Person record for), but a model that is merely asked "who is
speaker 2?" will answer confidently from topic and vibe.

That failure mode is not symmetric with a miss. A wrong name shown once is an
annoyance; a wrong name that enrols a voiceprint writes the wrong person's
voice into that Person's ``speaker_embedding`` and mislabels them in every
later conversation, silently, with no path back (see #10453 for how hard a lost
embedding already is to recover). Non-identification is recoverable. Mis-
identification is not.

This module answers only the questions a machine can settle without reading
the language: does the quote exist verbatim in one segment, does it contain the
claimed name, is the speaker real and still undecided, is the name the account
owner's or a stopword, is the speaker/name mapping one-to-one. Whether those
words actually mean that this speaker is that person is a judgement, and a
regex that tried to make it would only be second-guessing a language model
about grammar. So nothing here may assign or enrol: every claim that survives
is a *suggestion*, and a separate, independent model call
(``utils.llm.speaker_verification``) has to fail to refute it before anything
irreversible happens.
"""

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from utils.speaker_names import SPEAKER_NAME_STOPWORDS

MIN_SUGGESTION_CONFIDENCE = 0.5

MIN_NAME_LENGTH = 2

MAX_NAME_LENGTH = 40


class RejectionReason(str, Enum):
    UNKNOWN_SPEAKER = "unknown_speaker"
    SPEAKER_ALREADY_RESOLVED = "speaker_already_resolved"
    INVALID_NAME = "invalid_name"
    NAME_IS_USER = "name_is_user"
    QUOTE_NOT_IN_TRANSCRIPT = "quote_not_in_transcript"
    NAME_NOT_IN_QUOTE = "name_not_in_quote"
    LOW_CONFIDENCE = "low_confidence"
    AMBIGUOUS_SPEAKER = "ambiguous_speaker"
    AMBIGUOUS_NAME = "ambiguous_name"


@dataclass(frozen=True)
class SpeakerClaim:
    """One "speaker N is <name>" proposal, as returned by the model."""

    speaker_id: int
    person_name: str
    evidence_quote: str
    confidence: float


@dataclass(frozen=True)
class ResolvedSpeaker:
    """A claim that survived gating, with the segments it would cover."""

    speaker_id: int
    person_name: str
    evidence_quote: str
    confidence: float
    segment_ids: Tuple[str, ...]


@dataclass(frozen=True)
class RejectedClaim:
    claim: SpeakerClaim
    reason: RejectionReason


@dataclass(frozen=True)
class ResolutionPlan:
    """The gated outcome: what is worth proposing, and what was thrown away.

    There is deliberately no ``assignments`` field. Grounding a quote proves
    the words were said; it does not prove they mean what the model claimed.
    Everything here is a suggestion until refutation fails.
    """

    suggestions: Tuple[ResolvedSpeaker, ...] = ()
    rejected: Tuple[RejectedClaim, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.suggestions


_WHITESPACE = re.compile(r"\s+")

_NON_WORD = re.compile(r"[^\w\s]", re.UNICODE)

_APOSTROPHE = re.compile(r"['’ʼ]")


def normalize_text(value: object) -> str:
    """Casefold, strip accents and punctuation, collapse whitespace.

    Quote grounding has to survive the model reflowing punctuation or dropping
    a comma, without becoming so lossy that an unrelated sentence matches.
    """
    if not isinstance(value, str):
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    contracted = _APOSTROPHE.sub("", stripped)
    without_punctuation = _NON_WORD.sub(" ", contracted)
    return _WHITESPACE.sub(" ", without_punctuation).strip().casefold()


def is_valid_person_name(name: object) -> bool:
    """Reject the pronouns, fillers and bare words that read as names.

    Shares ``SPEAKER_NAME_STOPWORDS`` with the regex detector so a word barred
    there cannot slip in here (#5223).
    """
    if not isinstance(name, str):
        return False
    candidate = name.strip()
    if not (MIN_NAME_LENGTH <= len(candidate) <= MAX_NAME_LENGTH):
        return False
    if not any(ch.isalpha() for ch in candidate):
        return False
    for part in candidate.split():
        if part.casefold() in SPEAKER_NAME_STOPWORDS:
            return False
    return True


def _segment_field(segment: Any, field: str) -> Any:
    if isinstance(segment, Mapping):
        return segment.get(field)
    return getattr(segment, field, None)


@dataclass(frozen=True)
class _SegmentView:
    index: int
    id: str
    speaker_id: Optional[int]
    is_user: bool
    person_id: Optional[str]
    normalized_text: str


def _view_segments(segments: Sequence[Any]) -> List[_SegmentView]:
    views: List[_SegmentView] = []
    for index, segment in enumerate(segments):
        segment_id = _segment_field(segment, "id")
        if not isinstance(segment_id, str) or not segment_id:
            continue
        raw_speaker = _segment_field(segment, "speaker_id")
        speaker_id = raw_speaker if isinstance(raw_speaker, int) and not isinstance(raw_speaker, bool) else None
        person_id = _segment_field(segment, "person_id")
        views.append(
            _SegmentView(
                index=index,
                id=segment_id,
                speaker_id=speaker_id,
                is_user=bool(_segment_field(segment, "is_user")),
                person_id=person_id if isinstance(person_id, str) and person_id else None,
                normalized_text=normalize_text(_segment_field(segment, "text")),
            )
        )
    return views


def _resolved_speaker_ids(views: Sequence[_SegmentView]) -> Set[int]:
    """Speakers the pipeline has already decided, which the model may not overwrite.

    A speaker the user tagged, or that embedding matching already bound to a
    Person, outranks anything inferred from text.
    """
    resolved: Set[int] = set()
    for view in views:
        if view.speaker_id is None:
            continue
        if view.is_user or view.person_id:
            resolved.add(view.speaker_id)
    return resolved


def _quote_segments(views: Sequence[_SegmentView], quote: str) -> List[_SegmentView]:
    normalized_quote = normalize_text(quote)
    if not normalized_quote:
        return []
    return [view for view in views if normalized_quote and normalized_quote in view.normalized_text]


def _name_in_quote(name: str, quote: str) -> bool:
    normalized_quote = normalize_text(quote)
    normalized_name = normalize_text(name)
    if not normalized_quote or not normalized_name:
        return False
    quote_words = normalized_quote.split()
    return all(part in quote_words for part in normalized_name.split())


def _ground_claim(claim: SpeakerClaim, views: Sequence[_SegmentView]) -> Optional[RejectionReason]:
    """Check the quote was really said and really carries the name.

    A single segment must contain the whole quote: allowing it to span two
    would let the model stitch a name from one turn onto a sentence from
    another. ``None`` means it passed.
    """
    if not _quote_segments(views, claim.evidence_quote):
        return RejectionReason.QUOTE_NOT_IN_TRANSCRIPT

    if not _name_in_quote(claim.person_name, claim.evidence_quote):
        return RejectionReason.NAME_NOT_IN_QUOTE

    return None


def _drop_ambiguous(
    accepted: Sequence[Tuple[SpeakerClaim, Tuple[str, ...]]],
) -> Tuple[List[Tuple[SpeakerClaim, Tuple[str, ...]]], List[RejectedClaim]]:
    """Enforce a one-to-one speaker/name mapping.

    Two names on one speaker means at least one is wrong. One name on two
    speakers would merge two people's voices under a single Person, which is
    the exact shape of an unrecoverable voiceprint poisoning. Neither side of
    such a conflict is kept.
    """
    by_speaker: Dict[int, List[Tuple[SpeakerClaim, Tuple[str, ...]]]] = {}
    by_name: Dict[str, List[Tuple[SpeakerClaim, Tuple[str, ...]]]] = {}
    for entry in accepted:
        claim = entry[0]
        by_speaker.setdefault(claim.speaker_id, []).append(entry)
        by_name.setdefault(normalize_text(claim.person_name), []).append(entry)

    rejected: List[RejectedClaim] = []
    blocked: Set[int] = set()

    for speaker_id, entries in by_speaker.items():
        names = {normalize_text(claim.person_name) for claim, _ in entries}
        if len(names) > 1:
            blocked.add(speaker_id)
            rejected.extend(RejectedClaim(claim, RejectionReason.AMBIGUOUS_SPEAKER) for claim, _ in entries)

    for _, entries in by_name.items():
        speakers = {claim.speaker_id for claim, _ in entries}
        if len(speakers) > 1:
            for claim, _ in entries:
                if claim.speaker_id in blocked:
                    continue
                blocked.add(claim.speaker_id)
                rejected.append(RejectedClaim(claim, RejectionReason.AMBIGUOUS_NAME))

    survivors = [entry for entry in accepted if entry[0].speaker_id not in blocked]
    return survivors, rejected


def _best_per_speaker(
    entries: Sequence[Tuple[SpeakerClaim, Tuple[str, ...]]],
) -> List[Tuple[SpeakerClaim, Tuple[str, ...]]]:
    """Keep one claim per speaker: the highest confidence the model reported.

    Confidence is only a tiebreak between claims that already carry the same
    name for the same speaker -- ``_drop_ambiguous`` has removed the cases
    where the choice would matter.
    """
    best: Dict[int, Tuple[SpeakerClaim, Tuple[str, ...]]] = {}
    for claim, segment_ids in entries:
        current = best.get(claim.speaker_id)
        if current is None or claim.confidence > current[0].confidence:
            best[claim.speaker_id] = (claim, segment_ids)
    return [best[speaker_id] for speaker_id in sorted(best)]


def plan_speaker_resolution(
    claims: Iterable[SpeakerClaim],
    segments: Sequence[Any],
    user_name: Optional[str] = None,
    min_suggestion_confidence: float = MIN_SUGGESTION_CONFIDENCE,
) -> ResolutionPlan:
    """Gate model claims into suggestions and rejections.

    Args:
        claims: Proposals from the model, already parsed.
        segments: The conversation's transcript segments, in order.
        user_name: The account owner's display name. A claim naming the owner
            is dropped -- "you" is decided by the speech profile and the mic,
            not by an inference over text.
        min_suggestion_confidence: Below this a claim is not even offered.

    Returns:
        A ``ResolutionPlan``. Nothing in it may be written or enrolled until a
        refutation pass has been run over it.
    """
    views = _view_segments(segments)
    known_speakers = {view.speaker_id for view in views if view.speaker_id is not None}
    already_resolved = _resolved_speaker_ids(views)
    normalized_user_name = normalize_text(user_name)

    rejected: List[RejectedClaim] = []
    accepted: List[Tuple[SpeakerClaim, Tuple[str, ...]]] = []

    for claim in claims:
        if claim.speaker_id not in known_speakers:
            rejected.append(RejectedClaim(claim, RejectionReason.UNKNOWN_SPEAKER))
            continue
        if claim.speaker_id in already_resolved:
            rejected.append(RejectedClaim(claim, RejectionReason.SPEAKER_ALREADY_RESOLVED))
            continue
        if not is_valid_person_name(claim.person_name):
            rejected.append(RejectedClaim(claim, RejectionReason.INVALID_NAME))
            continue
        if normalized_user_name and normalize_text(claim.person_name) == normalized_user_name:
            rejected.append(RejectedClaim(claim, RejectionReason.NAME_IS_USER))
            continue
        if claim.confidence < min_suggestion_confidence:
            rejected.append(RejectedClaim(claim, RejectionReason.LOW_CONFIDENCE))
            continue

        failure = _ground_claim(claim, views)
        if failure is not None:
            rejected.append(RejectedClaim(claim, failure))
            continue

        segment_ids = tuple(view.id for view in views if view.speaker_id == claim.speaker_id)
        accepted.append((claim, segment_ids))

    survivors, ambiguity_rejections = _drop_ambiguous(accepted)
    rejected.extend(ambiguity_rejections)

    suggestions = [
        ResolvedSpeaker(
            speaker_id=claim.speaker_id,
            person_name=claim.person_name.strip(),
            evidence_quote=claim.evidence_quote,
            confidence=claim.confidence,
            segment_ids=segment_ids,
        )
        for claim, segment_ids in _best_per_speaker(survivors)
    ]

    return ResolutionPlan(suggestions=tuple(suggestions), rejected=tuple(rejected))
