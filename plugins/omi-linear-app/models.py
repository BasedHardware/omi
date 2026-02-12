"""
Pydantic models for the Linear Omi plugin.
"""
from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


class LinearUser(BaseModel):
    """Linear user information."""
    id: str
    name: str
    email: str = ""
    display_name: str = ""
    avatar_url: Optional[str] = None


class LinearTeam(BaseModel):
    """Linear team information."""
    id: str
    name: str
    key: str
    description: Optional[str] = ""


class LinearProject(BaseModel):
    """Linear project information."""
    id: str
    name: str
    description: str = ""
    state: str = ""
    url: Optional[str] = None


class WorkflowState(BaseModel):
    """Linear workflow state."""
    id: str
    name: str
    type: str  # backlog, unstarted, started, completed, canceled
    color: str = "#888"
    position: float = 0


class LinearLabel(BaseModel):
    """Linear label information."""
    id: str
    name: str
    color: str = ""


class LinearIssue(BaseModel):
    """Linear issue information."""
    id: str
    identifier: str  # e.g., "ENG-123"
    title: str
    description: Optional[str] = ""
    priority: int = 0  # 0 = No priority, 1 = Urgent, 2 = High, 3 = Medium, 4 = Low
    estimate: Optional[int] = None
    state: Optional[WorkflowState] = None
    assignee: Optional[LinearUser] = None
    creator: Optional[LinearUser] = None
    team: Optional[LinearTeam] = None
    project: Optional[LinearProject] = None
    labels: List[LinearLabel] = []
    url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class LinearComment(BaseModel):
    """Linear comment information."""
    id: str
    body: str
    user: Optional[LinearUser] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# Omi Chat Tool Models
class ChatToolRequest(BaseModel):
    """Base request model for Omi chat tools."""
    uid: str
    app_id: str = ""
    tool_name: str = ""


class CreateIssueRequest(ChatToolRequest):
    """Request model for creating an issue."""
    title: str
    description: Optional[str] = ""
    priority: Optional[str] = None  # urgent, high, medium, low, none
    team_id: Optional[str] = None


class ListMyIssuesRequest(ChatToolRequest):
    """Request model for listing user's issues."""
    limit: int = 10
    status: Optional[str] = None  # backlog, todo, in progress, done, cancelled


class UpdateIssueStatusRequest(ChatToolRequest):
    """Request model for updating issue status."""
    issue_identifier: str
    new_status: str


class SearchIssuesRequest(ChatToolRequest):
    """Request model for searching issues."""
    query: str
    limit: int = 5


class GetIssueRequest(ChatToolRequest):
    """Request model for getting issue details."""
    issue_identifier: str


class AddCommentRequest(ChatToolRequest):
    """Request model for adding a comment."""
    issue_identifier: str
    comment: str


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tools."""
    result: Optional[str] = None
    error: Optional[str] = None


# Omi Conversation Models (for future memory/webhook integrations)
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

