from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from typing import Any, Dict, Literal, Mapping, Optional, List, Tuple
import math
import uuid
import re
from pydantic import BaseModel, Field, PrivateAttr, model_serializer
from pydantic.json_schema import SkipJsonSchema

from models.capture_window_proof import CaptureWindowProof
from models.other import Person
from models.speaker_label_provenance import project_source

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

AUDIO_SOURCE_MERGE_TOLERANCE_SECONDS = 0.001


def _sync_source_window(source: Any) -> Optional[Tuple[float, float]]:
    """Absolute ``(start, end)`` of a stored sync provenance marker, or None."""
    if not isinstance(source, dict) or source.get('type') != 'sync':
        return None
    start, end = source.get('start'), source.get('end')
    if (
        isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, (int, float))
        or not isinstance(end, (int, float))
        or not math.isfinite(start)
        or not math.isfinite(end)
        or start >= end
    ):
        return None
    return float(start), float(end)


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
    ambiguous = 'ambiguous'


class TranscriptSegment(BaseModel):
    id: Optional[str] = None
    text: str
    speaker: Optional[str] = 'SPEAKER_00'
    speaker_id: Optional[int] = None
    is_user: bool
    person_id: Optional[str] = None
    speaker_label_source: Optional[Literal['manual', 'auto', 'carried']] = None
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
    # Only present for v2 text whose provider position could not be proven.
    # Absence keeps every v1 serialized segment byte-identical.
    audio_alignment: SkipJsonSchema[Optional[str]] = Field(default=None, exclude=True)
    # V2 accepted-send run start in capture samples. Stops live text merging
    # from turning two valid windows across a VAD skip into one false window.
    audio_capture_run: SkipJsonSchema[Optional[int]] = Field(default=None, exclude=True)
    audio_capture_start: SkipJsonSchema[Optional[float]] = Field(default=None, exclude=True)
    audio_capture_end: SkipJsonSchema[Optional[float]] = Field(default=None, exclude=True)
    audio_source: SkipJsonSchema[Optional[Dict[str, Any]]] = Field(default=None, exclude=True)
    # Pinned-speaker prior only (flag PINNED_SPEAKER_PRIOR_ENABLED): people an unlabeled
    # voice resembles, [{person_id, level, suggest?}], for the suggestion card. Never a label.
    voice_candidates: SkipJsonSchema[Optional[List[Dict[str, Any]]]] = Field(default=None, exclude=True)
    # Transported only in Python-mode internal dumps; the DB folds this into
    # the bounded conversation blob and removes it from stored segments.
    speaker_match_scores: SkipJsonSchema[Optional[Dict[str, Any]]] = Field(default=None, exclude=True)
    # In-memory only: True when neither speaker nor speaker_id was in the
    # construction payload, so speaker_id is the SPEAKER_00 default rather
    # than persisted diarization. Not dumped; a stored synthesized 0 still
    # looks real after a round-trip.
    _speaker_id_synthesized: bool = PrivateAttr(default=False)
    # Transaction-local attribution, never serialized or persisted.
    _audio_capture_reason: str = PrivateAttr(default='missing_window')
    _capture_merge_proof: Optional[CaptureWindowProof] = PrivateAttr(default=None)

    @property
    def capture_merge_proof(self) -> Optional[CaptureWindowProof]:
        return self._capture_merge_proof

    @capture_merge_proof.setter
    def capture_merge_proof(self, proof: Optional[CaptureWindowProof]) -> None:
        self._capture_merge_proof = proof if proof and proof.matches(self.capture_window_bounds()) else None

    @property
    def capture_window_reason(self) -> str:
        return self._audio_capture_reason

    @capture_window_reason.setter
    def capture_window_reason(self, reason: str) -> None:
        self._audio_capture_reason = reason

    @model_serializer(mode='wrap')
    def _serialize_internal_evidence(self, handler, info):
        # A wrap serializer also runs when a parent conversation is dumped. Leave
        # the return type inferred so Pydantic retains the public field schema.
        # Omit absent internal markers to keep ordinary v1 payloads unchanged.
        data = handler(self)
        data['speaker_label_source'] = project_source(data)
        for key in ('audio_alignment', 'audio_capture_run', 'voice_candidates'):
            value = getattr(self, key)
            if value is not None:
                data[key] = value
        excluded = info.exclude if isinstance(getattr(info, 'exclude', None), (dict, set, frozenset)) else frozenset()
        included = getattr(info, 'include', None)
        included = included if isinstance(included, (dict, set, frozenset)) else None
        # Capture windows are storage-only. Python-mode dumps feed Firestore and internal
        # rewrites; JSON-mode dumps are API responses, which must never carry them.
        if getattr(info, 'mode', 'python') == 'json':
            return data
        for key in ('audio_capture_start', 'audio_capture_end', 'audio_source', 'speaker_match_scores'):
            value = getattr(self, key)
            if value is not None and key not in excluded and (included is None or key in included):
                data[key] = value
        return data

    def __init__(self, **data: Any):
        if 'speaker_identity_status' not in data and data.get('is_user') is True:
            data['speaker_identity_status'] = SpeakerIdentityStatus.user
        speaker_in_payload = data.get('speaker') is not None
        speaker_id_in_payload = data.get('speaker_id') is not None
        super().__init__(**data)
        self.speaker_label_source = project_source(
            {
                'person_id': self.person_id,
                'is_user': self.is_user,
                'speaker_label_source': self.speaker_label_source,
                'speaker_match_source': self.speaker_match_source,
            }
        )
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

    def capture_window_bounds(self) -> Optional[Tuple[float, float]]:
        start, end = self.audio_capture_start, self.audio_capture_end
        if start is None or end is None or not math.isfinite(start) or not math.isfinite(end) or start >= end:
            return None
        return start, end

    def _clear_audio_capture_window(self) -> None:
        self.audio_capture_start = self.audio_capture_end = None
        self._capture_merge_proof = None

    def _clear_audio_evidence(self) -> None:
        self._clear_audio_capture_window()
        self._audio_capture_reason = 'partial_redistribution'
        self.audio_source = None

    def _merge_audio_source(self, other: 'TranscriptSegment') -> None:
        a_window = _sync_source_window(self.audio_source)
        b_window = _sync_source_window(other.audio_source)
        if a_window is None or b_window is None:
            self.audio_source = None
            return
        offsets = (
            a_window[0] - self.start,
            a_window[1] - self.end,
            b_window[0] - other.start,
            b_window[1] - other.end,
        )
        if (
            max(offsets) - min(offsets) > AUDIO_SOURCE_MERGE_TOLERANCE_SECONDS
            or max(a_window[0], b_window[0]) > min(a_window[1], b_window[1]) + AUDIO_SOURCE_MERGE_TOLERANCE_SECONDS
        ):
            self.audio_source = None
            return
        self.audio_source = {
            'type': 'sync',
            'start': min(a_window[0], b_window[0]),
            'end': max(a_window[1], b_window[1]),
        }

    def _merge_audio_capture_window(self, other: 'TranscriptSegment') -> None:
        from config.audio_timeline import live_capture_window_merge_union_enabled

        proof = None
        if live_capture_window_merge_union_enabled():
            left, right = self._capture_merge_proof, other._capture_merge_proof
            if (
                left
                and right
                and left.matches(self.capture_window_bounds())
                and right.matches(other.capture_window_bounds())
            ):
                proof = left.union(right)
        if proof is not None:
            self.audio_capture_start, self.audio_capture_end = proof.window
            self._capture_merge_proof = proof
            self._audio_capture_reason = 'known_window'
            return
        self._capture_merge_proof = None
        a_start, a_end = self.audio_capture_start, self.audio_capture_end
        b_start, b_end = other.audio_capture_start, other.audio_capture_end
        if (
            a_start is not None
            and a_end is not None
            and b_start is not None
            and b_end is not None
            and all(math.isfinite(value) for value in (a_start, a_end, b_start, b_end))
            and a_start < a_end
            and b_start < b_end
            and max(a_start, b_start) <= min(a_end, b_end)
        ):
            self.audio_capture_start = min(a_start, b_start)
            self.audio_capture_end = max(a_end, b_end)
        else:
            if self._audio_capture_reason == 'inherited_unknown' or other._audio_capture_reason == 'inherited_unknown':
                self._audio_capture_reason = 'inherited_unknown'
            elif a_start is None or a_end is None or b_start is None or b_end is None:
                self._audio_capture_reason = 'merge_unknown_side'
            elif (
                not all(math.isfinite(v) for v in (a_start, a_end, b_start, b_end))
                or a_start >= a_end
                or b_start >= b_end
            ):
                self._audio_capture_reason = 'merge_invalid_window'
            else:
                self._audio_capture_reason = 'merge_gap'
            self._clear_audio_capture_window()

    def assign_resolved_speaker(self, speaker_id: int, scope: str) -> None:
        """Adopt a conversation-wide speaker id; it is real diarization, not the SPEAKER_00 default."""
        self.speaker_id = speaker_id
        self.speaker = f'SPEAKER_{speaker_id}'
        self.speaker_id_scope = scope
        self._speaker_id_synthesized = False

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
        speaker_bound_ids: Optional[set[int]] = None,
        preserve_capture_windows: bool = False,
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
                and _is_chronological_continuation(a, b)
                and (len(a.text) < 125 or a.text[-1] not in SENTENCE_ENDERS)
            )

        def _should_merge_lowercase_continuation(a: 'TranscriptSegment', b: 'TranscriptSegment') -> bool:
            # No gap bound here by design: an incomplete lowercase sentence still belongs
            # to its speaker's next word no matter how long the pause was. But it must
            # still be b's predecessor, not a late arrival from an earlier batch -- that
            # ordering check is the part shared with _is_chronological_continuation.
            return (
                bool(a.text)
                and bool(b.text)
                and (a.speaker == b.speaker or (a.is_user and b.is_user))
                and a.text[-1] not in SENTENCE_ENDERS
                and _starts_with_lowercase_cased(b.text)
                and a.speech_profile_processed == b.speech_profile_processed
                and b.start >= a.start
                and b.end >= a.end
            )

        def _join_translations(a: 'TranscriptSegment', b: 'TranscriptSegment') -> List[Translation]:
            # A language translated on only one side would describe part of the merged
            # text; drop it so the translation path treats the segment as a miss.
            theirs = {t.lang: t.text for t in b.translations or []}
            return [
                Translation(lang=t.lang, text=f'{t.text} {theirs[t.lang]}')
                for t in a.translations or []
                if t.lang in theirs
            ]

        def _append_decided_speaker(
            a: 'TranscriptSegment', b: 'TranscriptSegment'
        ) -> Tuple[Optional['TranscriptSegment'], Optional['TranscriptSegment']]:
            # Both sides carry the same decided speaker_id (the caller refused any other
            # pair), though their SPEAKER_ spellings may differ. Only append in order:
            # sentence repair would retire a saved ID, and a late arrival would invert the span.
            if not _is_chronological_continuation(a, b) or a.speech_profile_processed != b.speech_profile_processed:
                return a, b
            if len(a.text) >= 125 and a.text[-1:] in SENTENCE_ENDERS and not _starts_with_lowercase_cased(b.text):
                return a, b
            a.text += f' {b.text}'
            a._merge_audio_source(b)
            a.end = b.end
            a.translations = _join_translations(a, b)
            a._merge_audio_capture_window(b)
            _absorb(b, a)
            return a, None

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
            # A speaker-wide decision covers every segment of that speaker, so its
            # segments may merge with each other but never trade words across it.
            if (
                speaker_bound_ids
                and a.speaker_id != b.speaker_id
                and (a.speaker_id in speaker_bound_ids or b.speaker_id in speaker_bound_ids)
            ):
                return a, b
            if b.stt_provider != a.stt_provider:
                return a, b
            if b.speaker_match_source != a.speaker_match_source:
                return a, b
            if b.speaker_label_source != a.speaker_label_source:
                return a, b
            if b.speaker_id_scope != a.speaker_id_scope:
                return a, b
            # An unplaced point must not merge into a covered segment and
            # silently inherit that segment's audio provenance.
            if b.audio_alignment != a.audio_alignment:
                return a, b
            if b.audio_capture_run != a.audio_capture_run:
                return a, b
            preserve_known_window = preserve_capture_windows and (
                a.capture_window_bounds() is not None or b.capture_window_bounds() is not None
            )
            if preserve_known_window:
                left, right = a.capture_window_bounds(), b.capture_window_bounds()
                if left is None or right is None or max(left[0], right[0]) > min(left[1], right[1]):
                    # Keep provider text/window pairs intact, rather than clear
                    # proof while absorbing an unknown or disjoint contributor.
                    return a, b
            if speaker_bound_ids and a.speaker_id in speaker_bound_ids:
                return _append_decided_speaker(a, b)

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
                        if preserve_known_window:
                            return a, b
                        a.text = f'{a.text} {first_sentence}'.strip()
                        b.text = rest
                        a._clear_audio_evidence()
                        b._clear_audio_evidence()
                        return a, b
                    if _can_backward_merge_single_sentence(first_sentence, last_incomplete):
                        a.text = f'{a.text} {first_sentence}'.strip()
                        a.audio_source = None
                        a._merge_audio_capture_window(b)
                        _absorb(b, a)
                        return a, None
                if last_incomplete and len(last_incomplete) < len(b.text.strip()):
                    if prefix and preserve_known_window:
                        return a, b
                    b.text = f'{last_incomplete} {b.text}'.strip()
                    if prefix:
                        a.text = prefix
                        a.end = min(a.end, b.start)
                        a._clear_audio_evidence()
                        b._clear_audio_evidence()
                        return a, b
                    a.text = ""
                    b.audio_source = None
                    b._merge_audio_capture_window(a)
                    _absorb(a, b)
                    return None, b
            if _should_merge_same_speaker(a, b):
                a.text += f' {b.text}'
                a._merge_audio_source(b)
                a.end = b.end
                a._merge_audio_capture_window(b)
                _absorb(b, a)
                return a, None

            if _should_merge_lowercase_continuation(a, b):
                a.text += f' {b.text}'
                a._merge_audio_source(b)
                a.end = b.end
                a._merge_audio_capture_window(b)
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


def transcript_segment_for_client(segment: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        key: value
        for key, value in segment.items()
        if key not in ('audio_capture_start', 'audio_capture_end', 'audio_source', 'speaker_match_scores')
    }


class ImprovedTranscriptSegment(BaseModel):
    speaker_id: int = Field(..., description='The correctly assigned speaker id')
    text: str = Field(..., description='The corrected text of the segment')


class ImprovedTranscript(BaseModel):
    result: List[ImprovedTranscriptSegment]
