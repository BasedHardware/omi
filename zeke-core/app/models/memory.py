from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import Column, String, Text, Boolean, DateTime, Float, JSON, Integer, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import ARRAY
from pgvector.sqlalchemy import Vector
from pydantic import BaseModel, Field
from enum import Enum

from .base import Base, TimestampMixin, UUIDMixin


class MemoryCategory(str, Enum):
    interesting = "interesting"
    system = "system"
    manual = "manual"


class CurationStatus(str, Enum):
    pending = "pending"
    clean = "clean"
    needs_review = "needs_review"
    flagged = "flagged"
    deleted = "deleted"


class PrimaryTopic(str, Enum):
    personal_profile = "personal_profile"
    relationships = "relationships"
    commitments = "commitments"
    health = "health"
    travel = "travel"
    finance = "finance"
    hobbies = "hobbies"
    work = "work"
    preferences = "preferences"
    facts = "facts"
    other = "other"


class MemoryDB(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "memories"
    
    uid: str = Column(String(64), nullable=False, index=True)
    content: str = Column(Text, nullable=False)
    category: str = Column(String(32), default="interesting")
    visibility: str = Column(String(16), default="private")
    tags: List[str] = Column(JSON, default=list)
    
    conversation_id: Optional[str] = Column(String(36), nullable=True, index=True)
    
    reviewed: bool = Column(Boolean, default=False)
    user_review: Optional[bool] = Column(Boolean, nullable=True)
    manually_added: bool = Column(Boolean, default=False)
    edited: bool = Column(Boolean, default=False)
    
    embedding = Column(Vector(1536), nullable=True)
    
    confidence_score: float = Column(Float, default=1.0)
    
    access_count: int = Column(Integer, default=0)
    last_accessed: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    
    primary_topic: Optional[str] = Column(String(32), default="other", index=True)
    curation_status: str = Column(String(20), default="pending", index=True)
    curation_notes: Optional[str] = Column(Text, nullable=True)
    enriched_context: Optional[Dict[str, Any]] = Column(JSON, nullable=True)
    curation_confidence: Optional[float] = Column(Float, nullable=True)
    last_curated: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)


class Memory(BaseModel):
    content: str = Field(description="The content of the memory")
    category: MemoryCategory = Field(default=MemoryCategory.interesting)
    visibility: str = Field(default="private")
    tags: List[str] = Field(default_factory=list)


class MemoryCreate(Memory):
    conversation_id: Optional[str] = None
    manually_added: bool = False


class MemoryResponse(Memory):
    id: str
    uid: str
    created_at: datetime
    updated_at: datetime
    conversation_id: Optional[str] = None
    reviewed: bool = False
    confidence_score: float = 1.0
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    primary_topic: Optional[str] = "other"
    curation_status: str = "pending"
    curation_notes: Optional[str] = None
    enriched_context: Optional[Dict[str, Any]] = None
    curation_confidence: Optional[float] = None
    last_curated: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class CurationRunDB(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "memory_curation_runs"
    
    user_id: str = Column(String(64), nullable=False, index=True)
    status: str = Column(String(20), default="running")
    
    memories_processed: int = Column(Integer, default=0)
    memories_updated: int = Column(Integer, default=0)
    memories_flagged: int = Column(Integer, default=0)
    memories_deleted: int = Column(Integer, default=0)
    
    started_at: datetime = Column(DateTime(timezone=True), nullable=False)
    completed_at: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    
    error_message: Optional[str] = Column(Text, nullable=True)
    run_config: Optional[Dict[str, Any]] = Column(JSON, nullable=True)


class CurationRunResponse(BaseModel):
    id: str
    user_id: str
    status: str
    memories_processed: int = 0
    memories_updated: int = 0
    memories_flagged: int = 0
    memories_deleted: int = 0
    started_at: datetime
    completed_at: Optional[datetime] = None
    created_at: datetime
    error_message: Optional[str] = None
    
    class Config:
        from_attributes = True
