"""Entity pages v1: derived views; corrections enter the authoritative ledger."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from models.review import EntityRef, EntityType, ReviewItem


class FactSource(BaseModel):
    kind: Literal['conversation', 'chat', 'screen', 'user']
    label: str
    conversation_id: Optional[str] = None
    at: Optional[datetime] = None


class Fact(BaseModel):
    fact_id: str
    text: str
    source: FactSource


class TaskRef(BaseModel):
    task_id: str
    description: str
    owner_label: Optional[str] = None
    due_at: Optional[datetime] = None
    waiting_on: Optional[str] = None


class ConversationRef(BaseModel):
    conversation_id: str
    title: str
    started_at: datetime
    duration_seconds: int


class EntityPage(BaseModel):
    entity_id: str
    type: EntityType
    name: str
    subtitle: Optional[str] = None
    organization: Optional[EntityRef] = None
    summary: Optional[str] = None
    summary_updated_at: Optional[datetime] = None
    people: list[EntityRef] = Field(default_factory=list)
    projects: list[EntityRef] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    open_tasks: list[TaskRef] = Field(default_factory=list)
    decisions: list[Fact] = Field(default_factory=list)
    recent_conversations: list[ConversationRef] = Field(default_factory=list)
    pending_question: Optional[ReviewItem] = None


class EntityCorrection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=2000)

    @field_validator('text')
    @classmethod
    def nonblank(cls, text: str) -> str:
        if not text.strip():
            raise ValueError('Correction must not be blank')
        return text.strip()


class EntitiesResponse(BaseModel):
    entities: list[EntityRef]
