from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, String, Text, Boolean, DateTime, Float, JSON
from sqlalchemy.dialects.postgresql import ARRAY
from pgvector.sqlalchemy import Vector
from pydantic import BaseModel, Field
from enum import Enum

from .base import Base, TimestampMixin, UUIDMixin


class MemoryCategory(str, Enum):
    interesting = "interesting"
    system = "system"
    manual = "manual"


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
    
    class Config:
        from_attributes = True
