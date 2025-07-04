from datetime import timedelta
from typing import Optional, List, Tuple
import uuid
import re
from pydantic import BaseModel, Field


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
    def segments_as_string(segments, include_timestamps=False, user_name: str = None):
        if not user_name:
            user_name = 'User'
        transcript = ''
        include_timestamps = include_timestamps and TranscriptSegment.can_display_seconds(segments)
        for segment in segments:
            segment_text = segment.text.strip()
            timestamp_str = f'[{segment.get_timestamp_string()}] ' if include_timestamps else ''
            transcript += f'{timestamp_str}{user_name if segment.is_user else f"Speaker {segment.speaker_id}"}: {segment_text}\n\n'
        return transcript.strip()

    @staticmethod
    def can_display_seconds(segments):
        for i in range(len(segments)):
            for j in range(i + 1, len(segments)):
                if segments[i].start > segments[j].end or segments[i].end > segments[j].start:
                    return False
        return True

    @staticmethod
    def correct_diarization_errors(segments: List['TranscriptSegment']) -> Tuple[List['TranscriptSegment'], List[str]]:
        if len(segments) < 2:
            return [], []

        seg_a = segments[-2]
        seg_b = segments[-1]

        if seg_a.speaker == seg_b.speaker:
            return [], []

        # Heuristic to fix diarization errors between different speakers
        def _split_text(text: str) -> List[str]:
            if not text:
                return []
            # Split by punctuation, keeping the delimiter with the preceding part.
            parts = re.split(r'([.?!])', text)
            if len(parts) <= 1:
                return [text.strip()] if text.strip() else []
            result = [(parts[i] + (parts[i + 1] if i + 1 < len(parts) else '')).strip() for i in
                      range(0, len(parts), 2)]
            return [s for s in result if s]

        sub_segments_a = _split_text(seg_a.text)
        dangling_fragment = ""
        if sub_segments_a and not sub_segments_a[-1].endswith(('.', '?', '!')):
            dangling_fragment = sub_segments_a[-1]
        elif not sub_segments_a and seg_a.text:
            dangling_fragment = seg_a.text

        sub_segments_b = _split_text(seg_b.text)
        continuation_fragment = ""
        if sub_segments_b and sub_segments_b[0] and sub_segments_b[0][0].islower():
            continuation_fragment = sub_segments_b[0]
        elif not sub_segments_b and seg_b.text and seg_b.text[0].islower():
            continuation_fragment = seg_b.text

        updated_segments = []
        removed_segment_ids = []
        if dangling_fragment and continuation_fragment:
            if len(seg_a.text) < len(seg_b.text):
                # Move dangling_fragment from A to B
                original_a_id = seg_a.id
                seg_b.text = dangling_fragment + " " + seg_b.text
                seg_a.text = seg_a.text[:-len(dangling_fragment)].strip()
                updated_segments.append(seg_b)
                if not seg_a.text:
                    segments.pop(-2)
                    removed_segment_ids.append(original_a_id)
                else:
                    updated_segments.append(seg_a)
            else:
                # Move continuation_fragment from B to A
                original_b_id = seg_b.id
                seg_a.text = seg_a.text + " " + continuation_fragment
                seg_b.text = seg_b.text[len(continuation_fragment):].strip()
                updated_segments.append(seg_a)
                if not seg_b.text:
                    segments.pop(-1)
                    removed_segment_ids.append(original_b_id)
                else:
                    updated_segments.append(seg_b)
        return updated_segments, removed_segment_ids

    @staticmethod
    def combine_segments(segments: [], new_segments: [], delta_seconds: int = 0):
        if not new_segments or len(new_segments) == 0:
            return segments, (len(segments), len(segments))

        joined_similar_segments = []
        for new_segment in new_segments:
            if delta_seconds > 0:
                new_segment.start += delta_seconds
                new_segment.end += delta_seconds

            if (joined_similar_segments and
                    (joined_similar_segments[-1].speaker == new_segment.speaker or
                     (joined_similar_segments[-1].is_user and new_segment.is_user))):
                joined_similar_segments[-1].text += f' {new_segment.text}'
                joined_similar_segments[-1].end = new_segment.end
            else:
                joined_similar_segments.append(new_segment)

        # updates range [starts, ends)
        starts = len(segments)
        ends = 0

        if (segments and joined_similar_segments and
                (segments[-1].speaker == joined_similar_segments[0].speaker or
                 (segments[-1].is_user and joined_similar_segments[0].is_user)) and
                (joined_similar_segments[0].start - segments[-1].end < 30)):
            segments[-1].text += f' {joined_similar_segments[0].text}'
            segments[-1].end = joined_similar_segments[0].end
            joined_similar_segments.pop(0)
            starts = len(segments) - 1

        segments.extend(joined_similar_segments)
        ends = len(segments)

        # Speechmatics specific issue with punctuation
        for i, segment in enumerate(segments):
            segments[i].text = (
                segments[i].text.strip()
                .replace('  ', ' ')
                .replace(' ,', ',')
                .replace(' .', '.')
                .replace(' ?', '?')
            )

        return segments, (starts, ends)


class ImprovedTranscriptSegment(BaseModel):
    speaker_id: int = Field(..., description='The correctly assigned speaker id')
    text: str = Field(..., description='The corrected text of the segment')


class ImprovedTranscript(BaseModel):
    result: List[ImprovedTranscriptSegment]
