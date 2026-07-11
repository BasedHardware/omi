from typing import List, Optional

from pydantic import BaseModel


class AudioPrecacheResponse(BaseModel):
    status: str
    message: Optional[str] = None
    audio_file_count: Optional[int] = None


class AudioFileUrlInfo(BaseModel):
    id: str
    status: str
    signed_url: Optional[str] = None
    content_type: Optional[str] = None
    duration: float = 0


class ConversationAudioSpanInfo(BaseModel):
    file_id: str
    wall_offset: float
    artifact_offset: float
    len: float


class ConversationAudioUrlInfo(BaseModel):
    status: str
    signed_url: Optional[str] = None
    content_type: Optional[str] = None
    duration: Optional[float] = None
    captured_duration: Optional[float] = None
    spans: List[ConversationAudioSpanInfo] = []


class AudioUrlsResponse(BaseModel):
    audio_files: List[AudioFileUrlInfo]
    conversation_audio: Optional[ConversationAudioUrlInfo] = None
    poll_after_ms: Optional[int] = None
