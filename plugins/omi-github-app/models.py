"""
Pydantic models for the GitHub Omi plugin.
"""
from typing import List, Optional
from pydantic import BaseModel


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tools."""
    result: Optional[str] = None
    error: Optional[str] = None


class GitHubRepo(BaseModel):
    """GitHub repository information."""
    name: str
    full_name: str
    owner: str
    private: bool
    description: Optional[str] = None
    url: str


class GitHubIssue(BaseModel):
    """GitHub issue information."""
    number: int
    title: str
    state: str
    body: Optional[str] = None
    labels: List[str] = []
    url: str


class GitHubLabel(BaseModel):
    """GitHub label information."""
    name: str
    color: str
    description: Optional[str] = None
