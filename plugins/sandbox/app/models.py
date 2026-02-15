from pydantic import BaseModel
from typing import Optional


class TranscriptSegment(BaseModel):
    text: str = ''
    speaker_name: Optional[str] = 'SPEAKER_00'
    speaker_id: Optional[int] = 0
    is_user: bool = False
    start: float = 0.0
    end: float = 0.0
    person_id: Optional[str] = None


class WebhookRequest(BaseModel):
    session_id: str = ''
    segments: list[TranscriptSegment] = []


class NotificationPayload(BaseModel):
    prompt: str
    params: list[str] = ['user_name']


class WebhookResponse(BaseModel):
    message: Optional[str] = None
    notification: Optional[NotificationPayload] = None
