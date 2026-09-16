"""Pydantic models for Omi Hacker News App."""

from typing import Literal, Optional
from pydantic import BaseModel, Field


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None


class FrontPageRequest(BaseModel):
    """Request schema for get_front_page."""

    limit: Optional[int] = Field(default=10, ge=1, le=20)


class SearchStoriesRequest(BaseModel):
    """Request schema for search_stories."""

    query: Optional[str] = None
    limit: Optional[int] = Field(default=10, ge=1, le=20)
    sort_by: Optional[Literal["relevance", "date"]] = "relevance"


class DiscussionRequest(BaseModel):
    """Request schema for get_discussion."""

    item_id: Optional[int] = None
    comment_limit: Optional[int] = Field(default=5, ge=1, le=20)
