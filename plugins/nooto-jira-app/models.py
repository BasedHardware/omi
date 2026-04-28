from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ChatToolRequest(BaseModel):
    uid: str


class ChatToolResponse(BaseModel):
    """Shared response wrapper for every /tools/* endpoint.

    Mirrors plugins/omi-linear-app's response shape so the Nooto backend can
    forward results into chat without per-tool adapters. When auth is missing
    or a refresh fails, populate `oauth_url` and let the chat agent surface it.
    """

    result: Optional[str] = None
    error: Optional[str] = None
    oauth_url: Optional[str] = None
    data: Optional[dict[str, Any]] = None


class TokenSet(BaseModel):
    access_token: str
    refresh_token: str
    expires_at: int
    scope: str = ""
    token_type: str = "Bearer"
    sites: list[dict[str, Any]] = Field(default_factory=list)
    default_cloud_id: Optional[str] = None
    updated_at: Optional[str] = None


# ── Chat tool request models ────────────────────────────────────────────────


class JiraCreateIssueRequest(ChatToolRequest):
    summary: str
    description: Optional[str] = None
    project_key: Optional[str] = None
    issue_type: str = "Task"
    priority: Optional[str] = None


class JiraListMyIssuesRequest(ChatToolRequest):
    status: Optional[str] = None
    limit: int = 10


class JiraSearchIssuesRequest(ChatToolRequest):
    query: str
    project_key: Optional[str] = None
    limit: int = 10


class JiraGetIssueRequest(ChatToolRequest):
    issue_key: str


class JiraUpdateStatusRequest(ChatToolRequest):
    issue_key: str
    new_status: str


class JiraAddCommentRequest(ChatToolRequest):
    issue_key: str
    comment: str


class JiraListProjectsRequest(ChatToolRequest):
    query: Optional[str] = None


# ── Proactive flow models ───────────────────────────────────────────────────

PriorityLiteral = Literal["Highest", "High", "Medium", "Low", "Lowest"]
IssueTypeLiteral = Literal["Task", "Bug", "Story", "Epic"]


class JiraIntent(BaseModel):
    detected: bool = False
    confidence: float = 0.0
    project_key: Optional[str] = None
    issue_type: IssueTypeLiteral = "Task"
    summary: str = ""
    description: str = ""
    priority: PriorityLiteral = "Medium"
    due_date: Optional[str] = None  # YYYY-MM-DD
    assignee_account_id: Optional[str] = None
    reasoning: str = ""


class JiraTicketCandidate(JiraIntent):
    suggestion_id: str
    source_quote: str = ""


class TranscriptSegment(BaseModel):
    text: str
    speaker: Optional[str] = None
    speaker_id: Optional[int] = None
    is_user: Optional[bool] = None
    person_id: Optional[str] = None
    start: Optional[float] = None
    end: Optional[float] = None


class WebhookRequest(BaseModel):
    segments: list[TranscriptSegment] = Field(default_factory=list)
    session_id: Optional[str] = None
    uid: Optional[str] = None


class ConfirmSuggestionResponse(BaseModel):
    status: Literal["filed", "dismissed", "already_filed", "already_dismissed", "expired", "error"]
    issue_key: Optional[str] = None
    message: Optional[str] = None


class UserSettings(BaseModel):
    enabled: bool = True
    autofile: bool = False
    default_project_key: Optional[str] = None
    quiet_hours: Optional[str] = None  # e.g. "22:00-07:00"
