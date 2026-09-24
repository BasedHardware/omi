from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from typing import Any, Dict, Optional, List, Tuple
import uuid
import re
from pydantic import BaseModel, Field, PrivateAttr
from pydantic.json_schema import SkipJsonSchema

from models.other import Person

# Unicode sentence-ending punctuation used across supported locales.
# Conservative set: English (.!?), CJK (。！？), Arabic/Urdu (؟۔), Hindi/Sanskrit (।॥)
SENTENCE_ENDERS = frozenset('.?!。！？؟۔।॥')

# Pre-compiled regex character class built from SENTENCE_ENDERS for use in re.split/re.findall.
SENTENCE_ENDERS_CLASS = '[' + re.escape(''.join(SENTENCE_ENDERS)) + ']'
SENTENCE_SPLIT_RE = re.compile(r'(?<=' + SENTENCE_ENDERS_CLASS + r')\s*')
SENTENCE_FINDALL_RE = re.compile(
    r'[^' + re.escape(''.join(SENTENCE_ENDERS)) + r']+(?:' + SENTENCE_ENDERS_CLASS + r'\s*|\s*$)'
)

# Maximum gap between the end of one segment and the start of the next for the two to still be
# treated as one continuing utterance. Mirrors the window _should_merge_same_speaker uses.
CROSS_SPEAKER_REPAIR_MAX_GAP_SECONDS = 3


def legacy_conversation_segment_id(conversation_id: str, index: int) -> str:
    """Stable IDs for legacy stored transcripts, shared by reads and manual writes."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f'omi/conversations/{conversation_id}/transcript-segments/{index}'))


@dataclass(frozen=True)
class CombineSegmentsResult:
    """3-tuple unpack for existing callers, plus an explicit absorbed-id map.

    ``list(removed_ids)`` (or JSON / executor copies) must not be how the remap
    travels — pass ``absorbed_into`` as its own value.
    """

    segments: List['TranscriptSegment']
    joined: List['TranscriptSegment']
    removed_ids: List[str]
    absorbed_into: Dict[str, str]

    def __iter__(self):
        yield self.segments
        yield self.joined
        yield self.removed_ids


class Translation(BaseModel):
    lang: str
    text: str


class SpeakerIdentityStatus(str, Enum):
    """Evidence state behind the legacy boolean ``is_user`` projection."""

    unknown = 'unknown'
    user = 'user'
    not_user = 'not_user'
    no_match = 'no_match'


class TranscriptSegment(BaseModel):
    id: Optional[str] = None
    text: str
    speaker: Optional[str] = 'SPEAKER_00'
    speaker_id: Optional[int] = None
    is_user: bool
    person_id: Optional[str] = None
    start: float
    end: float
    translations: Optional[List[Translation]] = Field(default_factory=list)
    speech_profile_processed: bool = True
    stt_provider: Optional[str] = None
    # Persisted for backend identity consumers. SkipJsonSchema keeps these out of
    # the generated OpenAPI/Dart/Swift client schema while validation and
    # model_dump (Firestore persistence, and the pusher transcript frames that
    # document them) stay intact.
    # Cleared atomically on the first manual review; never authorizes teaching.
    speaker_match_source: SkipJsonSchema[Optional[str]] = None
    speaker_id_scope: SkipJsonSchema[Optional[str]] = None
    speaker_identity_status: SkipJsonSchema[str] = SpeakerIdentityStatus.unknown
    # In-memory only: True when neither speaker nor speaker_id was in the
    # construction payload, so speaker_id is the SPEAKER_00 default rather
    # than persisted diarization. Not dumped; a stored synthesized 0 still
    # looks real after a round-trip.
    _speaker_id_synthesized: bool = PrivateAttr(default=False)

    def __init__(self, **data: Any):
        if 'speaker_identity_status' not in data and data.get('is_user') is True:
            data['speaker_identity_status'] = SpeakerIdentityStatus.user
        speaker_in_payload = data.get('speaker') is not None
        speaker_id_in_payload = data.get('speaker_id') is not None
        super().__init__(**data)
        self._speaker_id_synthesized = not speaker_in_payload and not speaker_id_in_payload
        if not self.id:
            self.id = str(uuid.uuid4())

        if self.speaker_id is not None:
            return
        if self.speaker:
            try:
                self.speaker_id = int(self.speaker.split('_', 1)[1])
            except (ValueError, IndexError):
                self.speaker_id = 0
        else:
            self.speaker_id = 0

    def get_timestamp_string(self) -> str:
        start_duration = timedelta(seconds=int(self.start))
        end_duration = timedelta(seconds=int(self.end))
        return f'{str(start_duration).split(".")[0]} - {str(end_duration).split(".")[0]}'

    @staticmethod
    def segments_as_string(
        segments: List['TranscriptSegment'],
        include_timestamps: bool = False,
        user_name: Optional[str] = None,
        people: Optional[List[Person]] = None,
    ) -> str:
        if not user_name:
            user_name = 'User'
        transcript = ''
        people_map = {person.id: person.name for person in people} if people else {}
        include_timestamps = include_timestamps and TranscriptSegment.can_display_seconds(segments)
        for segment in segments:
            segment_text = segment.text.strip()
            timestamp_str = f'[{segment.get_timestamp_string()}] ' if include_timestamps else ''
            speaker_name = user_name
            if not segment.is_user:
                if segment.person_id and segment.person_id in people_map:
                    speaker_name = people_map[segment.person_id]
                else:
                    speaker_name = f'Speaker {segment.speaker_id}'
            transcript += f'{timestamp_str}{speaker_name}: {segment_text}\n\n'

        return transcript.strip()

    @staticmethod
    def can_display_seconds(segments: List['TranscriptSegment']) -> bool:
        for i in range(len(segments)):
            for j in range(i + 1, len(segments)):
                if segments[i].start > segments[j].end or segments[i].end > segments[j].start:
                    return False
        return True

    @staticmethod
    def combine_segments(
        segments: List['TranscriptSegment'],
        new_segments: List['TranscriptSegment'],
        delta_seconds: int = 0,
        *,
        protected_segment_ids: Optional[set[str]] = None,
    ) -> CombineSegmentsResult:
        if not new_segments or len(new_segments) == 0:
            return CombineSegmentsResult(segments, [], [], {})

        def _extract_last_incomplete_sentence(text: str) -> Tuple[Optional[str], str]:
            text = text.strip()
            if not text:
                return None, ""
            parts = [p for p in SENTENCE_SPLIT_RE.split(text) if p]
            if not parts:
                return None, text
            last = parts[-1]
            if last[-1] not in SENTENCE_ENDERS:
                prefix = " ".join(parts[:-1]).strip() if len(parts) > 1 else ""
                return last, prefix
            return None, text

        def _split_first_sentence(text: str) -> Tuple[str, str]:
            text = text.strip()
            if not text:
                return "", ""
            parts = [p for p in SENTENCE_SPLIT_RE.split(text) if p]
            if not parts:
                return "", ""
            first = parts[0]
            rest = " ".join(parts[1:]).strip()
            return first, rest

        def _starts_with_lowercase_cased(text: str) -> bool:
            for ch in text.strip():
                if ch.isalpha():
                    return ch.islower()
            return False

        def _is_sentence_complete(text: str) -> bool:
            text = text.strip()
            return bool(text) and text[-1] in SENTENCE_ENDERS and not _starts_with_lowercase_cased(text)

        def _can_backward_merge_first_sentence(first_sentence: str, rest: str, last_incomplete: str) -> bool:
            if not rest:
                return False
            if not first_sentence:
                return False
            return len(first_sentence) < len(last_incomplete)

        def _can_backward_merge_single_sentence(first_sentence: str, last_incomplete: str) -> bool:
            if not first_sentence:
                return False
            if _is_sentence_complete(first_sentence):
                return False
            return len(first_sentence) < len(last_incomplete)

        def _is_chronological_continuation(a: 'TranscriptSegment', b: 'TranscriptSegment') -> bool:
            # Cross-speaker sentence repair rewrites timestamps and can delete a segment, so it
            # must only run when b really is a's successor. Segments arrive out of order across
            # batches (a late arrival from an earlier batch is appended after a newer tail), and
            # without this guard such a pair is "repaired" into a segment whose end precedes its
            # start, or the older segment is dropped and its words reattributed to the newer
            # speaker. Same-speaker merging already uses the same 3 second continuity window.
            return b.start >= a.start and b.end >= a.end and (b.start - a.end) < CROSS_SPEAKER_REPAIR_MAX_GAP_SECONDS

        def _should_merge_same_speaker(a: 'TranscriptSegment', b: 'TranscriptSegment') -> bool:
            return (
                (a.speaker == b.speaker or (a.is_user and b.is_user))
                and a.speech_profile_processed == b.speech_profile_processed
                and (b.start - a.end < 3)
                and (len(a.text) < 125 or a.text[-1] not in SENTENCE_ENDERS)
            )

        def _should_merge_lowercase_continuation(a: 'TranscriptSegment', b: 'TranscriptSegment') -> bool:
            return (
                bool(a.text)
                and bool(b.text)
                and (a.speaker == b.speaker or (a.is_user and b.is_user))
                and a.text[-1] not in SENTENCE_ENDERS
                and _starts_with_lowercase_cased(b.text)
                and a.speech_profile_processed == b.speech_profile_processed
            )

        absorbed_into: Dict[str, str] = {}
        removed_ids: List[str] = []

        def _absorb(child: Optional['TranscriptSegment'], parent: Optional['TranscriptSegment']) -> None:
            if child is None or not child.id:
                return
            if child.id not in absorbed_into:
                removed_ids.append(child.id)
            if parent is not None and parent.id:
                absorbed_into[child.id] = parent.id

        # Combined
        def _merge(
            a: Optional['TranscriptSegment'], b: Optional['TranscriptSegment']
        ) -> Tuple[Optional['TranscriptSegment'], Optional['TranscriptSegment']]:
            if not a or not b:
                return a, b
            if protected_segment_ids and (a.id in protected_segment_ids or b.id in protected_segment_ids):
                return a, b
            if b.stt_provider != a.stt_provider:
                return a, b
            if b.speaker_match_source != a.speaker_match_source:
                return a, b
            if b.speaker_id_scope != a.speaker_id_scope:
                return a, b

            if (
                a.speaker != b.speaker
                and not (a.is_user and b.is_user)
                and a.text
                and b.text
                and _is_chronological_continuation(a, b)
            ):
                last_incomplete, prefix = _extract_last_incomplete_sentence(a.text)
                if last_incomplete:
                    first_sentence, rest = _split_first_sentence(b.text)
                    if _can_backward_merge_first_sentence(first_sentence, rest, last_incomplete):
                        a.text = f'{a.text} {first_sentence}'.strip()
                        b.text = rest
                        return a, b
                    if _can_backward_merge_single_sentence(first_sentence, last_incomplete):
                        a.text = f'{a.text} {first_sentence}'.strip()
                        _absorb(b, a)
                        return a, None
                if last_incomplete and len(last_incomplete) < len(b.text.strip()):
                    b.text = f'{last_incomplete} {b.text}'.strip()
                    if prefix:
                        a.text = prefix
                        a.end = min(a.end, b.start)
                        return a, b
                    a.text = ""
                    _absorb(a, b)
                    return None, b
            if _should_merge_same_speaker(a, b):
                a.text += f' {b.text}'
                a.end = b.end
                _absorb(b, a)
                return a, None

            if _should_merge_lowercase_continuation(a, b):
                a.text += f' {b.text}'
                a.end = b.end
                _absorb(b, a)
                return a, None

            return a, b

        # Join
        joined_similar_segments: List[TranscriptSegment] = [segments[-1].model_copy(deep=True)] if segments else []
        dropped_existing_tail = False
        for new_segment in new_segments:
            if delta_seconds > 0:
                new_segment.start += delta_seconds
                new_segment.end += delta_seconds

            a, b = _merge(joined_similar_segments[-1] if joined_similar_segments else None, new_segment)
            if a:
                joined_similar_segments[-1] = a
            elif joined_similar_segments and joined_similar_segments[-1].text == "":
                if segments and joined_similar_segments[-1].id == segments[-1].id:
                    dropped_existing_tail = True
                joined_similar_segments.pop()
            if b:
                joined_similar_segments.append(b)

        if dropped_existing_tail and segments:
            segments.pop(-1)
        elif segments and joined_similar_segments and segments[-1].id == joined_similar_segments[0].id:
            segments.pop(-1)

        segments.extend(joined_similar_segments)

        # Normalize punctuation spacing
        for segment in segments:
            segment.text = (
                segment.text.strip().replace('  ', ' ').replace(' ,', ',').replace(' .', '.').replace(' ?', '?')
            )

        return CombineSegmentsResult(segments, joined_similar_segments, removed_ids, absorbed_into)


class ImprovedTranscriptSegment(BaseModel):
    speaker_id: int = Field(..., description='The correctly assigned speaker id')
    text: str = Field(..., description='The corrected text of the segment')


class ImprovedTranscript(BaseModel):
    result: List[ImprovedTranscriptSegment]
