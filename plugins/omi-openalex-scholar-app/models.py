"""Pydantic models for Omi OpenAlex Scholar Integration App."""

from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class ChatToolResponse(BaseModel):
    """Standard response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None

    @model_validator(mode="after")
    def validate_result_or_error(self):
        if (self.result is None) == (self.error is None):
            raise ValueError("Exactly one of 'result' or 'error' must be provided.")
        return self


class SearchResearchPapersRequest(BaseModel):
    """Request model for searching scientific and academic papers."""

    query: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="Search topic, paper title keywords, or research field (e.g. 'transformer neural networks', 'CRISPR gene editing').",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=15,
        description="Number of papers to retrieve (1-15).",
    )

    @field_validator("query")
    @classmethod
    def normalize_query(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 2:
            raise ValueError("Search query must contain at least 2 non-whitespace characters.")
        return cleaned


class GetAuthorProfileRequest(BaseModel):
    """Request model for retrieving a researcher's academic profile."""

    author_name: str = Field(
        ...,
        min_length=2,
        max_length=150,
        description="Full name of the researcher or scholar (e.g. 'Yann LeCun', 'Geoffrey Hinton', 'Jennifer Doudna').",
    )

    @field_validator("author_name")
    @classmethod
    def normalize_author_name(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 2:
            raise ValueError("Author name must contain at least 2 non-whitespace characters.")
        return cleaned


class GetInstitutionSummaryRequest(BaseModel):
    """Request model for retrieving a university or research institute profile."""

    institution_name: str = Field(
        ...,
        min_length=2,
        max_length=150,
        description="Name of the university, lab, or institution (e.g. 'Stanford University', 'MIT', 'Max Planck Institute').",
    )

    @field_validator("institution_name")
    @classmethod
    def normalize_institution_name(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 2:
            raise ValueError("Institution name must contain at least 2 non-whitespace characters.")
        return cleaned


class ExploreAcademicTopicRequest(BaseModel):
    """Request model for exploring an academic topic or research field."""

    topic: Optional[str] = Field(
        default=None,
        max_length=150,
        description="Scientific topic, research cluster, or discipline (e.g. 'Quantum Computing', 'CRISPR Gene Editing').",
    )
    concept: Optional[str] = Field(
        default=None,
        max_length=150,
        description="Alias for topic for backward compatibility.",
    )

    @model_validator(mode="after")
    def resolve_topic_or_concept(self):
        target = self.topic or self.concept
        if not target or len(target.strip()) < 2:
            raise ValueError("A topic or concept name with at least 2 non-whitespace characters must be provided.")
        self.topic = target.strip()
        return self


# Backward-compatibility alias
ExploreAcademicConceptRequest = ExploreAcademicTopicRequest
