"""
Pydantic models for Dropbox Omi plugin.
"""

from typing import Optional
from pydantic import BaseModel

from omi_plugin_sdk.models import ActionItem, Conversation, EndpointResponse, Structured, TranscriptSegment


class ChatToolResponse(BaseModel):
    """Standard response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None


class SearchDropboxRequest(BaseModel):
    """Request model for searching files in Dropbox."""

    uid: str
    query: str


class ListDropboxRequest(BaseModel):
    """Request model for listing files in Dropbox folder."""

    uid: str
    folder: Optional[str] = None


class ReadDropboxRequest(BaseModel):
    """Request model for reading file content from Dropbox."""

    uid: str
    path: str


class DropboxUserSettings(BaseModel):
    """User preferences for Dropbox sync."""

    folder_name: str = "Omi Conversations"
    save_summary: bool = True
    save_transcript: bool = True
    save_audio: bool = True
