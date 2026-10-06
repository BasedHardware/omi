"""
Pydantic data models for pCloud Omi backup plugin.
Provides user settings and Omi conversation structures with graceful SDK fallback.
"""

from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import BaseModel, Field

try:
    from omi_plugin_sdk.models import ActionItem, Conversation, EndpointResponse, Structured, TranscriptSegment
except ImportError:
    from datetime import datetime

    class ActionItem(BaseModel):
        description: str
        completed: bool = False

    class Structured(BaseModel):
        title: str = "New Conversation"
        overview: str = ""
        emoji: str = "💬"
        category: str = "general"
        action_items: List[ActionItem] = Field(default_factory=list)

    class TranscriptSegment(BaseModel):
        text: str
        speaker: Optional[str] = None
        is_user: bool = False
        start: float = 0.0
        end: float = 0.0

    class Conversation(BaseModel):
        id: str = ""
        created_at: Optional[datetime] = None
        finished_at: Optional[datetime] = None
        structured: Structured = Field(default_factory=Structured)
        transcript_segments: List[TranscriptSegment] = Field(default_factory=list)
        discarded: bool = False

    class EndpointResponse(BaseModel):
        message: str = ""


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
        description="Whether to export conversation transcript markdown (requires explicit consent)",
    )
    save_audio: bool = Field(
        default=True,
        description="Whether to export raw conversation audio (requires explicit consent)",
    )
    location_id: Literal[1, 2] = Field(
        default=1,
        description="pCloud data center: 1 for United States, 2 for Europe",
    )
