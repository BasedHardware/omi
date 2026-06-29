"""
Pydantic models for Dropbox Omi plugin.
"""

from pydantic import BaseModel

from omi_plugin_sdk.models import ActionItem, Conversation, EndpointResponse, Structured, TranscriptSegment


class DropboxUserSettings(BaseModel):
    """User preferences for Dropbox sync."""

    folder_name: str = "Omi Conversations"
    save_summary: bool = True
    save_transcript: bool = True
    save_audio: bool = True
