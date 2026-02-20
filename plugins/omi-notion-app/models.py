"""
Pydantic models for the Notion Omi plugin.
"""
from typing import List, Optional
from pydantic import BaseModel


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tools."""
    result: Optional[str] = None
    error: Optional[str] = None


class NotionPage(BaseModel):
    """Notion page."""
    id: str
    title: str
    url: Optional[str] = None
    created_time: Optional[str] = None
    last_edited_time: Optional[str] = None
    archived: bool = False
    parent_type: Optional[str] = None
    parent_id: Optional[str] = None


class NotionDatabase(BaseModel):
    """Notion database."""
    id: str
    title: str
    url: Optional[str] = None
    properties: List[str] = []


class NotionBlock(BaseModel):
    """Notion block."""
    id: str
    type: str
    content: Optional[str] = None
    has_children: bool = False


class NotionWorkspace(BaseModel):
    """Notion workspace info."""
    id: str
    name: str
    icon: Optional[str] = None
