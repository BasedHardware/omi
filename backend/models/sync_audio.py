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


class AudioUrlsResponse(BaseModel):
    audio_files: List[AudioFileUrlInfo]
    poll_after_ms: Optional[int] = None
