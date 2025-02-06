from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class ActionItemStatus(str, Enum):
    OPEN = "open"
    COMPLETED = "completed"
    DELETED = "deleted"

class ActionItem(BaseModel):
    id: str = Field(description="Unique identifier for the action item")
    memory_id: Optional[str] = Field(description="Associated memory ID if created from a memory")
    uid: str = Field(description="User ID who owns this action item")
    description: str = Field(description="The action item text/description")
    status: ActionItemStatus = Field(default=ActionItemStatus.OPEN)
    created_at: datetime = Field(description="When the action item was created")
    updated_at: datetime = Field(description="Last time the action item was updated")
    completed_at: Optional[datetime] = Field(default=None, description="When the action item was completed")
    deleted_at: Optional[datetime] = Field(default=None, description="When the action item was deleted")
    due_date: Optional[datetime] = Field(default=None, description="Optional due date for the action item")