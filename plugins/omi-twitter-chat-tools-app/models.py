"""Pydantic models for Twitter Omi Integration."""
from typing import Optional
from pydantic import BaseModel


class ChatToolResponse(BaseModel):
    """Response model for chat tool endpoints."""
    result: Optional[str] = None
    error: Optional[str] = None
