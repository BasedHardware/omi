from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Folder(BaseModel):
    id: str
    name: str = Field(min_length=1, max_length=100)
    color: Optional[str] = '#6B7280'
    icon: Optional[str] = 'folder'
    created_at: datetime
    updated_at: datetime
    order: int = 0
    is_default: bool = False
    conversation_count: int = 0


class CreateFolderRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: Optional[str] = None
    icon: Optional[str] = None


class UpdateFolderRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    color: Optional[str] = None
    icon: Optional[str] = None
    order: Optional[int] = None


class MoveConversationRequest(BaseModel):
    folder_id: Optional[str] = None


class BulkMoveConversationsRequest(BaseModel):
    conversation_ids: list[str]
    folder_id: str


class DeleteFolderRequest(BaseModel):
    move_conversations_to_folder_id: Optional[str] = None
