"""
Pydantic models for Dropbox Omi plugin.
"""

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from omi_plugin_sdk.models import ActionItem, Conversation, EndpointResponse, Structured, TranscriptSegment


def coerce_tool_text(value: Any) -> Optional[str]:
    """Coerce a JSON tool parameter into usable stripped text.

    The Omi chat backend commonly emits JSON null for omitted tool parameters,
    and may pass non-string scalars. Nulls, booleans, containers, and values
    that are empty after stripping all normalize to None so handlers can apply
    one ``if not field`` guard; plain scalars are stringified.
    """
    if value is None or isinstance(value, (bool, dict, list, tuple, set)):
        return None
    if isinstance(value, str):
        cleaned = value.strip()
    elif isinstance(value, (int, float)):
        cleaned = str(value).strip()
    else:
        return None
    return cleaned or None


class ChatToolResponse(BaseModel):
    """Standard response model for Omi chat tool endpoints."""

    result: Optional[str] = Field(None, description="Successful result text")
    error: Optional[str] = Field(None, description="Error message")

    @model_validator(mode="after")
    def validate_result_or_error(self):
        if (self.result is None) == (self.error is None):
            raise ValueError("Exactly one of 'result' or 'error' must be provided.")
        return self


class ChatToolRequest(BaseModel):
    """Base payload for chat tool endpoints: every call carries the Omi user id."""

    uid: Optional[str] = Field(None, description="Omi user ID")

    @field_validator("uid", mode="before")
    @classmethod
    def _coerce_uid(cls, v):
        return coerce_tool_text(v)

    @classmethod
    def _base_kwargs(cls, body: dict) -> dict:
        return {"uid": coerce_tool_text(body.get("uid"))}

    @classmethod
    def from_payload(cls, body: dict) -> "ChatToolRequest":
        return cls(**cls._base_kwargs(body))


class SearchDropboxRequest(ChatToolRequest):
    """Request payload for the search_dropbox chat tool."""

    query: Optional[str] = Field(None, description="Search query - filename, content, or keywords")

    @field_validator("query", mode="before")
    @classmethod
    def _coerce_query(cls, v):
        return coerce_tool_text(v)

    @classmethod
    def from_payload(cls, body: dict) -> "SearchDropboxRequest":
        return cls(**cls._base_kwargs(body), query=coerce_tool_text(body.get("query")))


class ListDropboxRequest(ChatToolRequest):
    """Request payload for the list_dropbox_conversations chat tool."""

    folder: Optional[str] = Field(None, description="Optional folder path to list")

    @field_validator("folder", mode="before")
    @classmethod
    def _coerce_folder(cls, v):
        return coerce_tool_text(v)

    @classmethod
    def from_payload(cls, body: dict) -> "ListDropboxRequest":
        return cls(**cls._base_kwargs(body), folder=coerce_tool_text(body.get("folder")))


class ReadDropboxRequest(ChatToolRequest):
    """Request payload for the read_dropbox_file chat tool."""

    path: Optional[str] = Field(None, description="Full path to the file in Dropbox")

    @field_validator("path", mode="before")
    @classmethod
    def _coerce_path(cls, v):
        return coerce_tool_text(v)

    @classmethod
    def from_payload(cls, body: dict) -> "ReadDropboxRequest":
        return cls(**cls._base_kwargs(body), path=coerce_tool_text(body.get("path")))


class DropboxUserSettings(BaseModel):
    """User preferences for Dropbox sync."""

    folder_name: str = "Omi Conversations"
    save_summary: bool = True
    save_transcript: bool = True
    save_audio: bool = True
