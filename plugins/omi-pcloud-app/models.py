"""
Pydantic data models for pCloud Omi backup plugin.
Omi webhook payloads are owned by omi_plugin_sdk.models, not local fallbacks.
"""

from __future__ import annotations

from typing import Literal
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
        default=False,
        description="Whether to export conversation transcript markdown (requires explicit consent)",
    )
    save_audio: bool = Field(
        default=False,
        description="Whether to export raw conversation audio (requires explicit consent)",
    )
    location_id: Literal[1, 2] = Field(
        default=1,
        description="pCloud data center: 1 for United States, 2 for Europe",
    )
