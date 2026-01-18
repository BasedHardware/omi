from datetime import timedelta
from typing import Optional, List, Tuple
import uuid
import re
from pydantic import BaseModel, Field

from models.other import Person


class Translation(BaseModel):
    lang: str
    text: str


class TranscriptSegment(BaseModel):
    id: Optional[str] = None
    text: str
    speaker: Optional[str] = 'SPEAKER_00'
    speaker_id: Optional[int] = None
    is_user: bool
    person_id: Optional[str] = None
    start: float
    end: float
    translations: Optional[List[Translation]] = []
    speech_profile_processed: bool = True
    stt_provider: Optional[str] = None

    def __init__(self, **data):
        super().__init__(**data)
        if not self.id:
            self.id = str(uuid.uuid4())
        self.speaker_id = int(self.speaker.split('_')[1]) if self.speaker else 0

    def get_timestamp_string(self):
        start_duration = timedelta(seconds=int(self.start))
        end_duration = timedelta(seconds=int(self.end))
        return f'{str(start_duration).split(".")[0]} - {str(end_duration).split(".")[0]}'

    @staticmethod
    def segments_as_string(segments, include_timestamps=False, user_name: str = None, people: List[Person] = None):
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
    def can_display_seconds(segments):
        for i in range(len(segments)):
            for j in range(i + 1, len(segments)):
                if segments[i].start > segments[j].end or segments[i].end > segments[j].start:
                    return False
        return True

    @staticmethod
    def combine_segments(segments: [], new_segments: List['TranscriptSegment'], delta_seconds: int = 0):
        if not new_segments or len(new_segments) == 0:
            return segments, [], []

        def _extract_last_incomplete_sentence(text: str) -> Tuple[Optional[str], str]:
            text = text.strip()
            if not text:
                return None, ""
            # Use lookbehind to split after sentence-ending punctuation
            parts = [p for p in re.split(r'(?<=[.?!])\s*', text) if p]
            if not parts:
                return None, text
            last = parts[-1]
            # Check if the last part is incomplete (doesn't end with punctuation)
            if last[-1] not in ".?!":
                prefix = " ".join(parts[:-1]).strip() if len(parts) > 1 else ""
                return last, prefix
            return None, text

        def _split_first_sentence(text: str) -> Tuple[str, str]:
            text = text.strip()
            if not text:
                return "", ""
            parts = [p for p in re.split(r'(?<=[.?!])\s*', text) if p]
            if not parts:
                return "", ""
            first = parts[0]
            rest = " ".join(parts[1:]).strip()
            return first, rest

        def _is_sentence_complete(text: str) -> bool:
            text = text.strip()
            return bool(text) and text[-1] in ".?!" and text[0].isupper()

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

        def _should_merge_same_speaker(a: 'TranscriptSegment', b: 'TranscriptSegment') -> bool:
            return (
                (a.speaker == b.speaker or (a.is_user and b.is_user))
                and a.speech_profile_processed == b.speech_profile_processed
                and (b.start - a.end < 3)
                and (len(a.text) < 125 or a.text[-1] not in [".", "?", "!"])
            )

        def _should_merge_lowercase_continuation(a: 'TranscriptSegment', b: 'TranscriptSegment') -> bool:
            return (
                a.text
                and b.text
                and (a.speaker == b.speaker or (a.is_user and b.is_user))
                and not a.text[-1] in [".", "?", "!"]
                and b.text[0].islower()
                and a.speech_profile_processed == b.speech_profile_processed
            )

        # Combined
        def _merge(a, b: TranscriptSegment):
            if not a or not b:
                return a, b
            if b.stt_provider != a.stt_provider:
                return a, b

            if a.speaker != b.speaker and not (a.is_user and b.is_user) and a.text and b.text:
                last_incomplete, prefix = _extract_last_incomplete_sentence(a.text)
                if last_incomplete:
                    first_sentence, rest = _split_first_sentence(b.text)
                    if _can_backward_merge_first_sentence(first_sentence, rest, last_incomplete):
                        a.text = f'{a.text} {first_sentence}'.strip()
                        b.text = rest
                        return a, b
                    if _can_backward_merge_single_sentence(first_sentence, last_incomplete):
                        a.text = f'{a.text} {first_sentence}'.strip()
                        return a, None
                if last_incomplete and len(last_incomplete) < len(b.text.strip()):
                    b.text = f'{last_incomplete} {b.text}'.strip()
                    if prefix:
                        a.text = prefix
                        a.end = min(a.end, b.start)
                        return a, b
                    a.text = ""
                    return None, b
            if _should_merge_same_speaker(a, b):
                a.text += f' {b.text}'
                a.end = b.end
                return a, None

            if _should_merge_lowercase_continuation(a, b):
                a.text += f' {b.text}'
                a.end = b.end
                return a, None

            return a, b

        removed_ids = []

        # Join
        joined_similar_segments = [segments[-1].model_copy(deep=True)] if segments else []
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
                    removed_ids.append(segments[-1].id)
                    dropped_existing_tail = True
                joined_similar_segments.pop()
            if b:
                joined_similar_segments.append(b)

        if dropped_existing_tail and segments:
            segments.pop(-1)
        elif segments and joined_similar_segments and segments[-1].id == joined_similar_segments[0].id:
            segments.pop(-1)

        segments.extend(joined_similar_segments)

        # Speechmatics specific issue with punctuation
        for i, segment in enumerate(segments):
            segments[i].text = (
                segments[i].text.strip().replace('  ', ' ').replace(' ,', ',').replace(' .', '.').replace(' ?', '?')
            )

        return segments, joined_similar_segments, removed_ids


class ImprovedTranscriptSegment(BaseModel):
    speaker_id: int = Field(..., description='The correctly assigned speaker id')
    text: str = Field(..., description='The corrected text of the segment')


class ImprovedTranscript(BaseModel):
    result: List[ImprovedTranscriptSegment]
