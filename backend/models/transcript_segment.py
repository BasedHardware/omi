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
            return segments, (len(segments), len(segments))

        # By the first punctuation on text
        def _split(text: str) -> []:
            i = -1
            for m in ['.', '!', '?']:
                i = text.find(m)
                break
            if i == -1:
                return [text]

            parts = [text[: i + 1]]
            remaining = text[i + 1 :].strip()
            if remaining:
                parts.append(remaining)
            return parts

        # Refined new segments
        refined_segments = []
        for segment in new_segments:
            if segment.text and segment.text[0].islower() and re.search('[.?!]', segment.text):
                start = segment.start
                c_rate = (segment.end - segment.start) / len(segment.text)
                for text in _split(segment.text):
                    if not text:
                        continue
                    s = segment.copy(deep=True)
                    s.text = text

                    # Time alignment
                    s.start = start
                    s.end = start + c_rate * len(text)
                    start = s.end
                    refined_segments.append(s)
            else:
                refined_segments.append(segment)

        new_segments = refined_segments

        # Combined
        def _merge(a, b: TranscriptSegment):
            if not a or not b:
                return a, b
            if b.stt_provider != a.stt_provider:
                return a, b
            if (
                (a.speaker == b.speaker or (a.is_user and b.is_user))
                and a.speech_profile_processed == b.speech_profile_processed
                and (b.start - a.end < 3)
                and (len(a.text) < 125 or a.text[-1] not in [".", "?", "!"])
            ):
                a.text += f' {b.text}'
                a.end = b.end
                return a, None

            if (
                a.text
                and b.text
                and not a.text[-1] in [".", "?", "!"]
                and b.text[0].islower()
                and a.speech_profile_processed == b.speech_profile_processed
            ):
                a.text += f' {b.text}'
                a.end = b.end
                return a, None

            return a, b

        # Updates range [starts, ends)
        starts = len(segments)
        ends = 0

        # Join
        joined_similar_segments = [segments[-1].copy(deep=True)] if segments else []
        for new_segment in new_segments:
            if delta_seconds > 0:
                new_segment.start += delta_seconds
                new_segment.end += delta_seconds

            a, b = _merge(joined_similar_segments[-1] if joined_similar_segments else None, new_segment)
            if a:
                joined_similar_segments[-1] = a
            if b:
                joined_similar_segments.append(b)

        if segments and segments[-1].id == joined_similar_segments[0].id:
            # having updates
            if segments[-1].text != joined_similar_segments[0].text:
                starts = len(segments) - 1
            segments.pop(-1)

        segments.extend(joined_similar_segments)
        ends = len(segments)

        # Speechmatics specific issue with punctuation
        for i, segment in enumerate(segments):
            segments[i].text = (
                segments[i].text.strip().replace('  ', ' ').replace(' ,', ',').replace(' .', '.').replace(' ?', '?')
            )

        return segments, (starts, ends)


class ImprovedTranscriptSegment(BaseModel):
    speaker_id: int = Field(..., description='The correctly assigned speaker id')
    text: str = Field(..., description='The corrected text of the segment')


class ImprovedTranscript(BaseModel):
    result: List[ImprovedTranscriptSegment]
