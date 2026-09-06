"""Pydantic models for The Metropolitan Museum of Art Omi integration plugin."""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class SearchArtworksRequest(BaseModel):
    """Request schema for searching Metropolitan Museum of Art artworks."""

    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Search term (e.g., 'sunflowers', 'Rembrandt', 'Greek pottery')",
    )
    artist_or_culture: Optional[bool] = Field(
        default=None,
        description="If True, restricts search match to artist or culture fields",
    )
    department_id: Optional[int] = Field(
        default=None,
        ge=1,
        description="Optional department ID filter to narrow search",
    )
    has_images: bool = Field(
        default=True,
        description="Whether to only return artworks that have public images",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Number of artwork summaries to return (1-10)",
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Query string cannot be empty or whitespace only")
        return cleaned


class ArtworkDetailsRequest(BaseModel):
    """Request schema for retrieving detailed artwork information."""

    object_id: int = Field(
        ...,
        ge=1,
        description="The unique object ID of the Metropolitan Museum artwork",
    )


class DepartmentHighlightsRequest(BaseModel):
    """Request schema for retrieving curated highlights for a department."""

    department_id: int = Field(
        ...,
        ge=1,
        description="The curatorial department ID (e.g., 11 for European Paintings)",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Number of department highlights to return (1-10)",
    )


class ArtworkSummary(BaseModel):
    """Concise representation of an artwork suitable for voice and list summaries."""

    object_id: int
    title: str
    artist_display_name: str
    object_date: str
    medium: str
    department: str
    primary_image_small: Optional[str] = None
    object_url: str


class ArtworkDetail(BaseModel):
    """Complete detail representation of a Metropolitan Museum artwork."""

    object_id: int
    title: str
    artist_display_name: str
    artist_display_bio: Optional[str] = None
    artist_nationality: Optional[str] = None
    culture: Optional[str] = None
    period: Optional[str] = None
    object_date: str
    medium: Optional[str] = None
    dimensions: Optional[str] = None
    department: str
    credit_line: Optional[str] = None
    classification: Optional[str] = None
    is_highlight: bool = False
    is_public_domain: bool = False
    primary_image: Optional[str] = None
    primary_image_small: Optional[str] = None
    object_url: str
    tags: List[str] = Field(default_factory=list)


class DepartmentItem(BaseModel):
    """Metropolitan Museum curatorial department item."""

    department_id: int
    display_name: str


class ChatToolResponse(BaseModel):
    """Standardized response format for Omi Chat Tools."""

    response: str
