from datetime import timedelta
from typing import Optional, List

from pydantic import BaseModel, Field


class TranscriptSegment(BaseModel):
    text: str
    speaker: Optional[str] = 'SPEAKER_00'
    speaker_id: Optional[int] = None
    is_user: bool
    person_id: Optional[str] = None
    start: float
    end: float

    def __init__(self, **data):
        super().__init__(**data)
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
    def combine_segments(segments: [], new_segments: [], delta_seconds: int = 0):
        if not new_segments or len(new_segments) == 0:
            return segments

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

        if (segments and
                (segments[-1].speaker == joined_similar_segments[0].speaker or
                 (segments[-1].is_user and joined_similar_segments[0].is_user)) and
                (joined_similar_segments[0].start - segments[-1].end < 30)):
            segments[-1].text += f' {joined_similar_segments[0].text}'
            segments[-1].end = joined_similar_segments[0].end
            joined_similar_segments.pop(0)

        segments.extend(joined_similar_segments)

        # Speechmatics specific issue with punctuation
        for i, segment in enumerate(segments):
            segments[i].text = (
                segments[i].text.strip()
                .replace('  ', '')
                .replace(' ,', ',')
                .replace(' .', '.')
                .replace(' ?', '?')
            )
        return segments


class ImprovedTranscriptSegment(BaseModel):
    speaker_id: int = Field(..., description='The correctly assigned speaker id')
    text: str = Field(..., description='The corrected text of the segment')


class ImprovedTranscript(BaseModel):
    result: List[ImprovedTranscriptSegment]
