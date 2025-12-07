from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import Column, String, Text, DateTime, Float, JSON, Integer, ForeignKey, Index
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from pydantic import BaseModel, Field
from enum import Enum

from .base import Base, TimestampMixin, UUIDMixin


class EntityType(str, Enum):
    person = "person"
    organization = "organization"
    location = "location"
    event = "event"
    project = "project"
    topic = "topic"
    task = "task"
    date = "date"
    product = "product"
    concept = "concept"
    other = "other"


class RelationType(str, Enum):
    knows = "knows"
    works_with = "works_with"
    works_at = "works_at"
    manages = "manages"
    assigned_to = "assigned_to"
    part_of = "part_of"
    related_to = "related_to"
    located_at = "located_at"
    occurred_on = "occurred_on"
    discussed = "discussed"
    mentioned_in = "mentioned_in"
    created = "created"
    owns = "owns"
    prefers = "prefers"
    dislikes = "dislikes"


class EntityDB(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "entities"
    
    uid: str = Column(String(64), nullable=False, index=True)
    name: str = Column(String(256), nullable=False)
    normalized_name: str = Column(String(256), nullable=False, index=True)
    entity_type: str = Column(String(32), nullable=False, index=True)
    
    description: Optional[str] = Column(Text, nullable=True)
    attributes: Optional[Dict[str, Any]] = Column(JSON, default=dict)
    aliases: List[str] = Column(JSON, default=list)
    
    embedding = Column(Vector(1536), nullable=True)
    
    mention_count: int = Column(Integer, default=1)
    last_mentioned: datetime = Column(DateTime(timezone=True), nullable=True)
    confidence: float = Column(Float, default=1.0)
    
    source_memory_ids: List[str] = Column(JSON, default=list)
    
    __table_args__ = (
        Index('ix_entities_uid_normalized', 'uid', 'normalized_name'),
        Index('ix_entities_uid_type', 'uid', 'entity_type'),
    )


class RelationshipDB(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "relationships"
    
    uid: str = Column(String(64), nullable=False, index=True)
    
    source_entity_id: str = Column(String(36), ForeignKey("entities.id"), nullable=False, index=True)
    target_entity_id: str = Column(String(36), ForeignKey("entities.id"), nullable=False, index=True)
    relation_type: str = Column(String(32), nullable=False, index=True)
    
    description: Optional[str] = Column(Text, nullable=True)
    properties: Optional[Dict[str, Any]] = Column(JSON, default=dict)
    
    strength: float = Column(Float, default=1.0)
    confidence: float = Column(Float, default=1.0)
    mention_count: int = Column(Integer, default=1)
    
    source_memory_id: Optional[str] = Column(String(36), nullable=True)
    
    __table_args__ = (
        Index('ix_relationships_source_target', 'source_entity_id', 'target_entity_id'),
        Index('ix_relationships_uid_type', 'uid', 'relation_type'),
    )


class EntityResponse(BaseModel):
    id: str
    name: str
    entity_type: str
    description: Optional[str] = None
    attributes: Dict[str, Any] = {}
    aliases: List[str] = []
    mention_count: int = 1
    confidence: float = 1.0
    created_at: datetime
    
    class Config:
        from_attributes = True


class RelationshipResponse(BaseModel):
    id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    description: Optional[str] = None
    properties: Dict[str, Any] = {}
    strength: float = 1.0
    confidence: float = 1.0
    created_at: datetime
    
    class Config:
        from_attributes = True


class EntityWithRelations(EntityResponse):
    outgoing_relations: List[RelationshipResponse] = []
    incoming_relations: List[RelationshipResponse] = []
    related_entities: List["EntityResponse"] = []


class GraphQueryResult(BaseModel):
    entities: List[EntityResponse] = []
    relationships: List[RelationshipResponse] = []
    paths: List[List[str]] = []
    context: str = ""


class ExtractedEntity(BaseModel):
    name: str
    entity_type: str
    description: Optional[str] = None
    attributes: Dict[str, Any] = {}
    confidence: float = 1.0


class ExtractedRelation(BaseModel):
    source: str
    target: str
    relation_type: str
    description: Optional[str] = None
    properties: Dict[str, Any] = {}
    confidence: float = 1.0
