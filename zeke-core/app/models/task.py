from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, String, Text, Boolean, DateTime, Integer, JSON
from pydantic import BaseModel, Field
from enum import Enum

from .base import Base, TimestampMixin, UUIDMixin


class TaskPriority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"


class TaskStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class TaskDB(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "tasks"
    
    uid: str = Column(String(64), nullable=False, index=True)
    
    title: str = Column(String(512), nullable=False)
    description: Optional[str] = Column(Text, nullable=True)
    
    priority: str = Column(String(16), default="medium")
    status: str = Column(String(16), default="pending")
    
    due_at: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    completed_at: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    
    conversation_id: Optional[str] = Column(String(36), nullable=True, index=True)
    
    tags: List[str] = Column(JSON, default=list)
    subtasks: List[dict] = Column(JSON, default=list)
    
    recurrence_rule: Optional[str] = Column(String(128), nullable=True)
    
    reminder_sent: bool = Column(Boolean, default=False)


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: TaskPriority = TaskPriority.medium
    due_at: Optional[datetime] = None
    conversation_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[TaskPriority] = None
    status: Optional[TaskStatus] = None
    due_at: Optional[datetime] = None


class TaskResponse(BaseModel):
    id: str
    uid: str
    title: str
    description: Optional[str] = None
    priority: str = "medium"
    status: str = "pending"
    due_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    conversation_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
