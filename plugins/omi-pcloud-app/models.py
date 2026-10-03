"""
Pydantic data models for pCloud Omi backup plugin.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PCloudUserSettings(BaseModel):
    """User preferences for pCloud conversation synchronization."""

    folder_name: str = Field(
        default="Omi Conversations",
        description="Root folder name on pCloud storage",
    )
    save_summary: bool = Field(
        default=True,
        description="Whether to export conversation summary markdown",
    )
    save_transcript: bool = Field(
        default=True,
        description="Whether to export conversation transcript markdown",
    )
    save_audio: bool = Field(
        default=True,
        description="Whether to export raw conversation audio",
    )
    location_id: int = Field(
        default=1,
        description="pCloud data center: 1 for United States, 2 for Europe",
    )
