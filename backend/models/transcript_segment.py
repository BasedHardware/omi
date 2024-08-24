from datetime import timedelta
from typing import Optional, List

from pydantic import BaseModel, Field


class TranscriptSegment(BaseModel):
    text: str
    speaker: Optional[str] = 'SPEAKER_00'
    speaker_id: Optional[int] = None
    is_user: bool
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
    def segments_as_string(segments, include_timestamps=False):
        transcript = ''
        include_timestamps = include_timestamps and TranscriptSegment.can_display_seconds(segments)
        for segment in segments:
            segment_text = segment.text.strip()
            timestamp_str = f'[{segment.get_timestamp_string()}] ' if include_timestamps else ''
            transcript += f'{timestamp_str}{"User" if segment.is_user else f"Speaker {segment.speaker_id}"}: {segment_text}\n\n'
        return transcript.strip()

    @staticmethod
    def can_display_seconds(segments):
        for i in range(len(segments)):
            for j in range(i + 1, len(segments)):
                if segments[i].start > segments[j].end or segments[i].end > segments[j].start:
                    return False
        return True


class ImprovedTranscriptSegment(BaseModel):
    speaker_id: int = Field(..., description='The correctly assigned speaker id')
    text: str = Field(..., description='The corrected text of the segment')
    # seconds: List[float] = Field(..., description='The start and end time of the segment')


class ImprovedTranscript(BaseModel):
    result: List[ImprovedTranscriptSegment]
