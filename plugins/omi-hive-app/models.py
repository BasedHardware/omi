"""
Pydantic models for the Hive Omi plugin.
"""
from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


# ============================================
# Hive Entity Models
# ============================================

class HiveUser(BaseModel):
    """Hive user information."""
    id: str
    email: Optional[str] = None
    name: Optional[str] = None
    profile_url: Optional[str] = None


class HiveWorkspace(BaseModel):
    """Hive workspace information."""
    id: str
    name: str
    description: Optional[str] = None


class HiveProject(BaseModel):
    """Hive project information."""
    id: str
    name: str
    description: Optional[str] = None
    status: Optional[str] = None
    workspace_id: Optional[str] = None
    workspace_name: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class HiveTask(BaseModel):
    """Hive task (action card) information."""
    id: str
    name: str
    description: Optional[str] = None
    status: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    assignees: List[str] = []
    due_date: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class HiveAction(BaseModel):
    """Hive action item (sub-task/checklist item)."""
    id: str
    name: str
    completed: bool = False
    task_id: Optional[str] = None
    task_name: Optional[str] = None
    assignee: Optional[str] = None
    due_date: Optional[datetime] = None


# ============================================
# Omi Chat Tool Models
# ============================================

class ChatToolRequest(BaseModel):
    """Base request model for Omi chat tools."""
    uid: str
    app_id: Optional[str] = None
    tool_name: Optional[str] = None


class GetProjectsRequest(ChatToolRequest):
    """Request model for getting projects."""
    workspace_name: Optional[str] = None
    limit: int = 10


class CreateTaskRequest(ChatToolRequest):
    """Request model for creating a task."""
    task_name: str
    project_name: Optional[str] = None
    project_id: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[str] = None


class GetTasksRequest(ChatToolRequest):
    """Request model for getting tasks."""
    project_name: Optional[str] = None
    project_id: Optional[str] = None
    status: Optional[str] = None
    limit: int = 10


class CreateActionRequest(ChatToolRequest):
    """Request model for creating an action item."""
    action_name: str
    task_name: Optional[str] = None
    task_id: Optional[str] = None
    assignee: Optional[str] = None
    due_date: Optional[str] = None


class SearchRequest(ChatToolRequest):
    """Request model for searching tasks/projects."""
    query: str
    limit: int = 10


class UpdateTaskStatusRequest(ChatToolRequest):
    """Request model for updating task status."""
    task_name: Optional[str] = None
    task_id: Optional[str] = None
    status: str


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tools."""
    result: Optional[str] = None
    error: Optional[str] = None


# ============================================
# Omi Conversation Models (for future use)
# ============================================

class TranscriptSegment(BaseModel):
    """Transcript segment from Omi conversation."""
    text: str
    speaker: Optional[str] = "SPEAKER_00"
    is_user: bool
    start: float
    end: float


class Structured(BaseModel):
    """Structured conversation data."""
    title: str
    overview: str
    emoji: str = ""
    category: str = "other"


class Conversation(BaseModel):
    """Omi conversation model."""
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    transcript_segments: List[TranscriptSegment] = []
    structured: Structured
    discarded: bool


class EndpointResponse(BaseModel):
    """Standard endpoint response for Omi webhooks."""
    message: str = Field(description="A short message to be sent as notification to the user, if needed.", default="")


