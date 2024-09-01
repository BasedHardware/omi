from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional

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
    start: datetime
    duration: int
    description: Optional[str] = ''
    created: bool = False


class MemoryPhoto(BaseModel):
    base64: str
    description: str


class PluginResult(BaseModel):
    plugin_id: Optional[str]
    content: str


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


class Memory(BaseModel):
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    transcript_segments: List[TranscriptSegment] = []
    photos: Optional[List[MemoryPhoto]] = []
    # recordingFilePath: Optional[str] = None
    # recordingFileBase64: Optional[str] = None
    structured: Structured
    plugins_results: List[PluginResult] = []
    discarded: bool

    def get_transcript(self, include_timestamps: bool = False) -> str:
        # Warn: missing transcript for workflow source
        return TranscriptSegment.segments_as_string(self.transcript_segments, include_timestamps=include_timestamps)


class Geolocation(BaseModel):
    google_place_id: Optional[str] = None
    latitude: float
    longitude: float
    address: Optional[str] = None
    location_type: Optional[str] = None


class MemorySource(str, Enum):
    friend = 'friend'
    openglass = 'openglass'
    screenpipe = 'screenpipe'
    workflow = 'workflow'


class WorkflowMemorySource(str, Enum):
    audio = 'audio_transcript'
    other = 'other_text'


class WorkflowCreateMemory(BaseModel):
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    text: str
    text_source: WorkflowMemorySource = WorkflowMemorySource.audio
    language: Optional[str] = None
    geolocation: Optional[Geolocation] = None


class EndpointResponse(BaseModel):
    message: str = Field(description="A short message to be sent as notification to the user, if needed.", default='')


class RealtimePluginRequest(BaseModel):
    session_id: str
    segments: List[TranscriptSegment]
