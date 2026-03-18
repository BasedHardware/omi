"""Pydantic models for Zomato OMI integration."""

from typing import Optional, Any

from pydantic import BaseModel


class ChatToolResponse(BaseModel):
    """Standard response for chat tool endpoints."""

    result: str


class ToolRequest(BaseModel):
    """Base request model for all chat tool endpoints."""

    uid: str
    app_id: Optional[str] = None
    tool_name: Optional[str] = None
