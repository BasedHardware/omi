# DEPRECATED: This file has been deprecated long ago
#
# This file is deprecated and should be removed. The code is not used anymore and is not referenced in any other file.
# The only files that references this file are routers/processing_memories.py and utils/processing_conversations, which are also deprecated.

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel

from models.conversation import Geolocation
from models.transcript_segment import TranscriptSegment


class ProcessingConversationStatus(str, Enum):
    Capturing = 'capturing'
    Processing = 'processing'
    Done = 'done'
    Failed = 'failed'


class ProcessingConversation(BaseModel):
    id: str
    session_id: Optional[str] = None
    session_ids: List[str] = []
    audio_url: Optional[str] = None
    created_at: datetime
    capturing_to: Optional[datetime] = None
    status: Optional[ProcessingConversationStatus] = None
    timer_start: float
    timer_segment_start: Optional[float] = None
    timer_starts: List[float] = []
    language: Optional[str] = None  # applies only to Friend/Omi # TODO: once released migrate db to default 'en'
    transcript_segments: List[TranscriptSegment] = []
    geolocation: Optional[Geolocation] = None
    emotional_feedback: Optional[bool] = False

    memory_id: Optional[str] = None
    message_ids: List[str] = []

    @staticmethod
    def predict_capturing_to(processing_conversation, min_seconds_limit: int):
        timer_segment_start = processing_conversation.timer_segment_start if processing_conversation.timer_segment_start else processing_conversation.timer_start
        segment_end = processing_conversation.transcript_segments[-1].end if len(
            processing_conversation.transcript_segments) > 0 else 0
        return datetime.fromtimestamp(timer_segment_start + segment_end + min_seconds_limit, timezone.utc)


class BasicProcessingConversation(BaseModel):
    id: str
    timer_start: float
    created_at: datetime
    capturing_to: Optional[datetime] = None
    status: Optional[ProcessingConversationStatus] = None
    geolocation: Optional[Geolocation] = None
    emotional_feedback: Optional[bool] = False
    memory_id: Optional[str] = None


class DetailProcessingConversation(BaseModel):
    id: str
    timer_start: float
    created_at: datetime
    capturing_to: Optional[datetime] = None
    status: Optional[ProcessingConversationStatus] = None
    geolocation: Optional[Geolocation] = None
    emotional_feedback: Optional[bool] = False
    transcript_segments: List[TranscriptSegment] = []
    memory_id: Optional[str] = None


class UpdateProcessingConversation(BaseModel):
    id: Optional[str] = None
    capturing_to: Optional[datetime] = None
    geolocation: Optional[Geolocation] = None
    emotional_feedback: Optional[bool] = False


class UpdateProcessingConversationResponse(BaseModel):
    result: BasicProcessingConversation


class DetailProcessingConversationResponse(BaseModel):
    result: DetailProcessingConversation


class DetailProcessingConversationsResponse(BaseModel):
    result: List[DetailProcessingConversation]


class BasicProcessingConversationResponse(BaseModel):
    result: BasicProcessingConversation


class BasicProcessingMemoriesResponse(BaseModel):
    result: List[BasicProcessingConversation]
