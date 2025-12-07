from datetime import datetime, time
from typing import Optional, List, Dict, Any
from sqlalchemy import Column, String, Text, Boolean, DateTime, Float, JSON, Integer, Time
from pydantic import BaseModel, Field, field_validator
from enum import Enum

from .base import Base, TimestampMixin, UUIDMixin


class ContextModeType(str, Enum):
    morning_planning = "morning_planning"
    family_time = "family_time"
    writing_mode = "writing_mode"
    work_mode = "work_mode"
    personal_project = "personal_project"
    relaxation = "relaxation"
    default = "default"


class ParkingLotPriority(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class ContextModeDB(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "context_modes"
    
    uid: str = Column(String(64), nullable=False, index=True)
    name: str = Column(String(64), nullable=False)
    mode_type: str = Column(String(32), nullable=False, index=True)
    description: Optional[str] = Column(Text, nullable=True)
    
    start_time: Optional[time] = Column(Time, nullable=True)
    end_time: Optional[time] = Column(Time, nullable=True)
    days_of_week: List[int] = Column(JSON, default=list)
    
    is_active: bool = Column(Boolean, default=True)
    priority: int = Column(Integer, default=0)
    
    prompt_style: Optional[str] = Column(String(32), default="balanced")
    response_brevity: Optional[str] = Column(String(16), default="normal")
    proactive_suggestions: bool = Column(Boolean, default=True)
    notification_level: Optional[str] = Column(String(16), default="normal")
    
    focus_areas: List[str] = Column(JSON, default=list)
    blocked_topics: List[str] = Column(JSON, default=list)
    
    custom_greeting: Optional[str] = Column(Text, nullable=True)
    custom_prompts: Optional[Dict[str, Any]] = Column(JSON, nullable=True)


class UserContextStateDB(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "user_context_states"
    
    uid: str = Column(String(64), nullable=False, unique=True, index=True)
    current_mode: Optional[str] = Column(String(32), default="default")
    mode_override: Optional[str] = Column(String(32), nullable=True)
    override_until: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    
    last_interaction: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    conversation_drift_count: int = Column(Integer, default=0)
    last_refocus_prompt: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    
    active_focus_topic: Optional[str] = Column(Text, nullable=True)
    focus_started_at: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    
    today_briefing_sent: bool = Column(Boolean, default=False)
    last_briefing_at: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    
    context_signals: Optional[Dict[str, Any]] = Column(JSON, nullable=True)


class ParkingLotItemDB(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "parking_lot_items"
    
    uid: str = Column(String(64), nullable=False, index=True)
    content: str = Column(Text, nullable=False)
    source_context: Optional[str] = Column(Text, nullable=True)
    
    priority: str = Column(String(16), default="medium")
    category: Optional[str] = Column(String(32), nullable=True)
    
    conversation_id: Optional[str] = Column(String(36), nullable=True)
    captured_at: datetime = Column(DateTime(timezone=True), nullable=False)
    
    is_processed: bool = Column(Boolean, default=False)
    processed_at: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    processed_action: Optional[str] = Column(String(64), nullable=True)
    
    reminder_at: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    tags: List[str] = Column(JSON, default=list)


class TimeSensitiveReminderDB(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "time_sensitive_reminders"
    
    uid: str = Column(String(64), nullable=False, index=True)
    title: str = Column(String(256), nullable=False)
    description: Optional[str] = Column(Text, nullable=True)
    
    reminder_time: datetime = Column(DateTime(timezone=True), nullable=False, index=True)
    lead_time_minutes: int = Column(Integer, default=15)
    
    reminder_type: str = Column(String(32), default="appointment")
    priority: str = Column(String(16), default="normal")
    
    is_recurring: bool = Column(Boolean, default=False)
    recurrence_pattern: Optional[str] = Column(String(64), nullable=True)
    
    notification_sent: bool = Column(Boolean, default=False)
    notification_sent_at: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    
    is_completed: bool = Column(Boolean, default=False)
    completed_at: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    
    source_task_id: Optional[str] = Column(String(36), nullable=True)
    extra_data: Optional[Dict[str, Any]] = Column(JSON, nullable=True)


class ContextModeCreate(BaseModel):
    name: str
    mode_type: ContextModeType = ContextModeType.default
    description: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    days_of_week: List[int] = Field(default_factory=list)
    prompt_style: str = "balanced"
    response_brevity: str = "normal"
    proactive_suggestions: bool = True
    notification_level: str = "normal"
    focus_areas: List[str] = Field(default_factory=list)
    blocked_topics: List[str] = Field(default_factory=list)
    custom_greeting: Optional[str] = None


class ContextModeResponse(BaseModel):
    id: str
    uid: str
    name: str
    mode_type: str
    description: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    days_of_week: List[int] = Field(default_factory=list)
    is_active: bool = True
    priority: int = 0
    prompt_style: str = "balanced"
    response_brevity: str = "normal"
    proactive_suggestions: bool = True
    notification_level: str = "normal"
    focus_areas: List[str] = Field(default_factory=list)
    blocked_topics: List[str] = Field(default_factory=list)
    custom_greeting: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}
    
    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def convert_time_to_str(cls, v):
        if v is None:
            return None
        if hasattr(v, 'strftime'):
            return v.strftime("%H:%M")
        return str(v)


class ParkingLotItemCreate(BaseModel):
    content: str
    priority: ParkingLotPriority = ParkingLotPriority.medium
    category: Optional[str] = None
    source_context: Optional[str] = None
    reminder_at: Optional[datetime] = None
    tags: List[str] = Field(default_factory=list)


class ParkingLotItemResponse(BaseModel):
    id: str
    uid: str
    content: str
    source_context: Optional[str] = None
    priority: str = "medium"
    category: Optional[str] = None
    captured_at: datetime
    is_processed: bool = False
    processed_at: Optional[datetime] = None
    processed_action: Optional[str] = None
    reminder_at: Optional[datetime] = None
    tags: List[str] = Field(default_factory=list)
    created_at: datetime
    
    class Config:
        from_attributes = True


class UserContextStateResponse(BaseModel):
    uid: str
    current_mode: str = "default"
    mode_override: Optional[str] = None
    override_until: Optional[datetime] = None
    last_interaction: Optional[datetime] = None
    conversation_drift_count: int = 0
    active_focus_topic: Optional[str] = None
    focus_started_at: Optional[datetime] = None
    today_briefing_sent: bool = False
    last_briefing_at: Optional[datetime] = None
    context_signals: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True


class TimeSensitiveReminderCreate(BaseModel):
    title: str
    description: Optional[str] = None
    reminder_time: datetime
    lead_time_minutes: int = 15
    reminder_type: str = "appointment"
    priority: str = "normal"
    is_recurring: bool = False
    recurrence_pattern: Optional[str] = None


class TimeSensitiveReminderResponse(BaseModel):
    id: str
    uid: str
    title: str
    description: Optional[str] = None
    reminder_time: datetime
    lead_time_minutes: int = 15
    reminder_type: str = "appointment"
    priority: str = "normal"
    is_recurring: bool = False
    recurrence_pattern: Optional[str] = None
    notification_sent: bool = False
    is_completed: bool = False
    created_at: datetime
    
    class Config:
        from_attributes = True


class DailyBriefing(BaseModel):
    greeting: str
    date: str
    current_mode: str
    weather_summary: Optional[str] = None
    schedule_summary: List[str] = Field(default_factory=list)
    pending_tasks: List[Dict[str, Any]] = Field(default_factory=list)
    overdue_tasks: List[Dict[str, Any]] = Field(default_factory=list)
    time_sensitive_reminders: List[Dict[str, Any]] = Field(default_factory=list)
    parking_lot_count: int = 0
    notable_memories: List[str] = Field(default_factory=list)
    proactive_suggestions: List[str] = Field(default_factory=list)
    focus_recommendation: Optional[str] = None
