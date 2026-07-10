"""
Pydantic models for the Linear Omi plugin.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from omi_plugin_sdk.models import Conversation, EndpointResponse, Structured, TranscriptSegment


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
    type: str
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
    identifier: str
    title: str
    description: Optional[str] = ""
    priority: int = 0
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


class ChatToolRequest(BaseModel):
    """Base request model for Omi chat tools."""

    uid: str
    app_id: str = ""
    tool_name: str = ""


class CreateIssueRequest(ChatToolRequest):
    """Request model for creating an issue."""

    title: str
    description: Optional[str] = ""
    priority: Optional[str] = None
    team_id: Optional[str] = None


class ListMyIssuesRequest(ChatToolRequest):
    """Request model for listing user's issues."""

    limit: int = 10
    status: Optional[str] = None


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
