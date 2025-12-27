from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field


class Folder(BaseModel):
    """A folder for organizing conversations."""

    id: str
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Natural language instruction for AI folder assignment (e.g., 'Conversations about AI, machine learning, and building AI-powered apps')",
    )
    color: str = Field(default='#6B7280')
    icon: str = Field(default='folder')
    created_at: datetime
    updated_at: datetime
    order: int = 0
    is_default: bool = False
    is_system: bool = Field(default=False, description="True for category-based default folders")
    category_mapping: Optional[str] = Field(
        default=None, description="Maps to CategoryEnum value for backwards compatibility"
    )
    conversation_count: int = 0


class CreateFolderRequest(BaseModel):
    """Request model for creating a new folder."""

    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Natural language instruction for AI (e.g., 'Work meetings and project discussions')",
    )
    color: Optional[str] = None
    icon: Optional[str] = None


class UpdateFolderRequest(BaseModel):
    """Request model for updating folder metadata."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500, description="Natural language instruction for AI")
    color: Optional[str] = None
    icon: Optional[str] = None
    order: Optional[int] = None


class MoveConversationRequest(BaseModel):
    """Request model for moving a conversation to a folder."""

    folder_id: Optional[str] = None


class BulkMoveConversationsRequest(BaseModel):
    """Request model for moving multiple conversations to a folder."""

    conversation_ids: List[str]


class ReorderFoldersRequest(BaseModel):
    """Request model for reordering folders."""

    folder_ids: List[str]  # Ordered list of folder IDs
