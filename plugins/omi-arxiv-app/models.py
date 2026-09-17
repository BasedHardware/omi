"""
Pydantic request and response models for the arXiv Omi integration app.
"""

from typing import Optional
from pydantic import BaseModel, Field


class ChatToolResponse(BaseModel):
    """Standard response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None


class SearchPapersRequest(BaseModel):
    """Request schema for /tools/search_papers."""

    query: Optional[str] = Field(
        default=None,
        description="Free-form research topic or keyword query.",
    )
    title: Optional[str] = Field(
        default=None,
        description="Optional title-specific search term.",
    )
    author: Optional[str] = Field(
        default=None,
        description="Optional author name filter.",
    )
    category: Optional[str] = Field(
        default=None,
        description="Optional arXiv category such as cs.AI, cs.CL, stat.ML, or quant-ph.",
    )
    sort_by: Optional[str] = Field(
        default="relevance",
        description="Sort order: relevance, submittedDate, or lastUpdatedDate.",
    )
    limit: Optional[int] = Field(
        default=5,
        description="Maximum papers to return (1-10).",
    )


class GetPaperDetailsRequest(BaseModel):
    """Request schema for /tools/get_paper_details."""

    paper_id: str = Field(
        ...,
        description="arXiv paper ID (e.g. 2401.01234, cs/9901001, or full arxiv.org/abs URL).",
    )


class SearchAuthorRequest(BaseModel):
    """Request schema for /tools/search_author."""

    author: str = Field(
        ...,
        description="Author name to search for.",
    )
    limit: Optional[int] = Field(
        default=5,
        description="Maximum papers to return (1-10).",
    )
