"""
Pydantic models for Dropbox Omi plugin.
"""

from datetime import timezone
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from omi_plugin_sdk.models import ActionItem, Conversation, EndpointResponse, Structured, TranscriptSegment


# ============== Request Models ==============


class ChatToolRequest(BaseModel):
    """Base request model for chat tool endpoints."""

    uid: str = Field(..., description="User ID")

    @field_validator("uid")
    @classmethod
    def uid_must_be_non_empty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("uid must not be empty")
        return v


class SearchDropboxRequest(ChatToolRequest):
    """Request for searching Dropbox files."""

    query: str = Field("", description="Search query")

    @field_validator("query")
    @classmethod
    def query_must_be_valid(cls, v: str) -> str:
        v = (v or "").strip()
        return v


class ListDropboxRequest(ChatToolRequest):
    """Request for listing Dropbox folder."""

    folder: Optional[str] = Field(None, description="Folder path to list")


class ReadDropboxFileRequest(ChatToolRequest):
    """Request for reading a Dropbox file."""

    path: str = Field(..., description="Full file path in Dropbox")

    @field_validator("path")
    @classmethod
    def path_must_be_non_empty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("path must not be empty")
        return v


# ============== Response Models ==============


class ChatToolResponse(BaseModel):
    """Typed response for chat tool endpoints."""

    result: Optional[str] = Field(None, description="Successful result text")
    error: Optional[str] = Field(None, description="Error message")

    def is_success(self) -> bool:
        return self.error is None and self.result is not None


class DropboxUserSettings(BaseModel):
    """User preferences for Dropbox sync."""

    folder_name: str = "Omi Conversations"
    save_summary: bool = True
    save_transcript: bool = True
    save_audio: bool = True
