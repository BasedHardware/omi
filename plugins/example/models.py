from datetime import datetime
from typing import List, Optional, Dict

from pydantic import BaseModel, Field


class Structured(BaseModel):
    title: str
    overview: str
    emoji: str = ''
    category: str = 'other'


class ActionItem(BaseModel):
    description: str


class Event(BaseModel):
    title: str
    startsAt: datetime
    duration: int
    description: Optional[str] = ''
    created: bool = False


class MemoryPhoto(BaseModel):
    base64: str
    description: str


class PluginResponse(BaseModel):
    pluginId: Optional[str] = None
    content: str


class TranscriptSegment(BaseModel):
    text: str
    speaker: str
    speaker_id: int
    is_user: bool
    start: float
    end: float

    @staticmethod
    def get_timestamp_string(start: float, end: float) -> str:
        def format_duration(seconds: float) -> str:
            total_seconds = int(seconds)
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            remaining_seconds = total_seconds % 60
            return f"{hours:02}:{minutes:02}:{remaining_seconds:02}"

        start_str = format_duration(start)
        end_str = format_duration(end)

        return f"{start_str} - {end_str}"

    @staticmethod
    def segments_as_string(segments: List[Dict]) -> str:
        transcript = ''

        for segment in segments:
            segment_text = segment['text'].strip()
            timestamp_str = f"[{TranscriptSegment.get_timestamp_string(segment['start'], segment['end'])}]"
            if segment.get('is_user', False):
                transcript += f"{timestamp_str} User: {segment_text} "
            else:
                transcript += f"{timestamp_str} Speaker {segment.get('speaker_id', '')}: {segment_text} "
            transcript += '\n\n'

        return transcript.strip()


class Memory(BaseModel):
    createdAt: datetime
    startedAt: Optional[datetime] = None
    finishedAt: Optional[datetime] = None
    transcript: str = ''
    transcriptSegments: List[TranscriptSegment] = []
    photos: Optional[List[MemoryPhoto]] = []
    recordingFilePath: Optional[str] = None
    recordingFileBase64: Optional[str] = None
    structured: Structured
    pluginsResponse: List[PluginResponse] = []
    discarded: bool


class EndpointResponse(BaseModel):
    message: str = Field(description="A short message to be sent as notification to the user, if needed.", default='')


class RealtimePluginRequest(BaseModel):
    session_id: str
    segments: List[TranscriptSegment]

    def get_segments(self):
        return list(map(lambda x: x.dict(), self.segments))
