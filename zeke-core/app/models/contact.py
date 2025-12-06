from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, String, Text, DateTime, JSON
from pydantic import BaseModel, Field

from .base import Base, TimestampMixin, UUIDMixin


class ContactDB(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "contacts"
    
    uid: str = Column(String(64), nullable=False, index=True)
    
    name: str = Column(String(256), nullable=False)
    relationship: Optional[str] = Column(String(128), nullable=True)
    
    phone: Optional[str] = Column(String(32), nullable=True)
    email: Optional[str] = Column(String(256), nullable=True)
    
    notes: Optional[str] = Column(Text, nullable=True)
    tags: List[str] = Column(JSON, default=list)
    
    last_mentioned_at: Optional[datetime] = Column(DateTime(timezone=True), nullable=True)
    mention_count: int = Column(default=0)
    
    metadata: dict = Column(JSON, default=dict)


class ContactCreate(BaseModel):
    name: str
    relationship: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    notes: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class ContactResponse(BaseModel):
    id: str
    uid: str
    name: str
    relationship: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    notes: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    last_mentioned_at: Optional[datetime] = None
    mention_count: int = 0
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
