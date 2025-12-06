from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import Column, String, Text, Boolean, DateTime, Float, JSON, Enum as SQLEnum
from pydantic import BaseModel, Field
from enum import Enum

from .base import Base, TimestampMixin, UUIDMixin


class ConversationSource(str, Enum):
    omi = "omi"
    limitless = "limitless"
    phone = "phone"
    external = "external"


class ConversationCategory(str, Enum):
    personal = "personal"
    work = "work"
    social = "social"
    health = "health"
    finance = "finance"
    education = "education"
    entertainment = "entertainment"
    travel = "travel"
    family = "family"
    other = "other"


class TranscriptSegment(BaseModel):
    text: str
    speaker: Optional[str] = None
    speaker_id: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    is_user: bool = False


class ActionItem(BaseModel):
    description: str
    completed: bool = False
    due_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class ConversationDB(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "conversations"
    
    uid: str = Column(String(64), nullable=False, index=True)
    
    title: str = Column(String(512), nullable=True)
    overview: str = Column(Text, nullable=True)
    emoji: str = Column(String(8), default="🧠")
    category: str = Column(String(32), default="other")
    
    source: str = Column(String(32), default="omi")
    source_id: Optional[str] = Column(String(128), nullable=True, index=True)
    
    started_at: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    finished_at: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    
    transcript_segments: List[Dict] = Column(JSON, default=list)
    action_items: List[Dict] = Column(JSON, default=list)
    
    location_lat: Optional[float] = Column(Float, nullable=True)
    location_lng: Optional[float] = Column(Float, nullable=True)
    location_name: Optional[str] = Column(String(256), nullable=True)
    
    participants: List[str] = Column(JSON, default=list)
    
    discarded: bool = Column(Boolean, default=False)
    processed: bool = Column(Boolean, default=False)
    
    external_data: Dict = Column(JSON, default=dict)


class ConversationCreate(BaseModel):
    title: Optional[str] = None
    overview: Optional[str] = None
    category: ConversationCategory = ConversationCategory.other
    source: ConversationSource = ConversationSource.omi
    source_id: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    transcript_segments: List[TranscriptSegment] = Field(default_factory=list)
    action_items: List[ActionItem] = Field(default_factory=list)
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None
    location_name: Optional[str] = None
    participants: List[str] = Field(default_factory=list)
    external_data: Dict[str, Any] = Field(default_factory=dict)


class ConversationResponse(BaseModel):
    id: str
    uid: str
    title: Optional[str] = None
    overview: Optional[str] = None
    emoji: str = "🧠"
    category: str = "other"
    source: str = "omi"
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    transcript_segments: List[TranscriptSegment] = Field(default_factory=list)
    action_items: List[ActionItem] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
    
    def get_transcript_text(self) -> str:
        return "\n".join([
            f"{seg.speaker or 'Speaker'}: {seg.text}" 
            for seg in self.transcript_segments
        ])
