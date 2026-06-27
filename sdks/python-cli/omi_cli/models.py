"""Pydantic shapes for omi-cli requests/responses.

Mirrors the subset of `backend/routers/developer.py` that the CLI exercises. We
hand-write these instead of codegen-from-OpenAPI because the spec at
``docs/api-reference/openapi.json`` is stale (last touched 2025-03-28, missing
goals entirely).

Where the backend has stricter validation (e.g. content min/max length), we
mirror the constraints so the CLI fails fast before hitting the API.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Memories
# ---------------------------------------------------------------------------


class MemoryCategory(str, Enum):
    """Mirrors backend ``MemoryCategory`` — the universe of valid category values."""

    core = "core"
    hobbies = "hobbies"
    lifestyle = "lifestyle"
    interests = "interests"
    habits = "habits"
    work = "work"
    skills = "skills"
    learnings = "learnings"
    other = "other"
    system = "system"


class MemoryVisibility(str, Enum):
    public = "public"
    private = "private"


class Memory(BaseModel):
    model_config = ConfigDict(extra="allow")  # tolerate fields the backend may add

    id: str
    content: str
    category: str  # accept any string so unknown categories don't crash the CLI
    visibility: Optional[str] = "private"
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    manually_added: bool = False
    reviewed: bool = False
    edited: bool = False


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    category: Optional[MemoryCategory] = None
    visibility: MemoryVisibility = MemoryVisibility.private
    tags: list[str] = Field(default_factory=list)


class MemoryUpdate(BaseModel):
    content: Optional[str] = Field(default=None, min_length=1, max_length=500)
    category: Optional[MemoryCategory] = None
    visibility: Optional[MemoryVisibility] = None
    tags: Optional[list[str]] = None


# ---------------------------------------------------------------------------
# Action items
# ---------------------------------------------------------------------------


class ActionItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    description: str
    completed: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    due_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    conversation_id: Optional[str] = None


class ActionItemCreate(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    completed: bool = False
    due_at: Optional[datetime] = None


class ActionItemUpdate(BaseModel):
    description: Optional[str] = Field(default=None, min_length=1, max_length=500)
    completed: Optional[bool] = None
    due_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------


class ConversationTextSource(str, Enum):
    audio_transcript = "audio_transcript"
    message = "message"
    other_text = "other_text"


class Conversation(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    structured: Optional[dict[str, Any]] = None
    language: Optional[str] = None
    source: Optional[str] = None
    folder_id: Optional[str] = None
    folder_name: Optional[str] = None


class ConversationSummary(BaseModel):
    """Trimmed view used in list output to keep tables narrow."""

    id: str
    title: str = ""
    category: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    source: Optional[str] = None


class ConversationCreate(BaseModel):
    text: str = Field(min_length=1, max_length=100000)
    text_source: ConversationTextSource = ConversationTextSource.other_text
    text_source_spec: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    language: str = "en"


class ConversationUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    discarded: Optional[bool] = None


# ---------------------------------------------------------------------------
# Goals
# ---------------------------------------------------------------------------


class GoalType(str, Enum):
    boolean = "boolean"
    scale = "scale"
    numeric = "numeric"


class Goal(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    goal_type: str
    target_value: float
    current_value: float
    min_value: float
    max_value: float
    unit: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class GoalCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    goal_type: GoalType = GoalType.scale
    target_value: float
    current_value: float = 0
    min_value: float = 0
    max_value: float = 10
    unit: Optional[str] = None


class GoalUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=500)
    target_value: Optional[float] = None
    current_value: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    unit: Optional[str] = None


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class DevApiKey(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    key_prefix: Optional[str] = None
    created_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    scopes: Optional[list[str]] = None
