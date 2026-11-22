"""Read-only task membership; task contents never enter this representation."""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from models.conversation import Conversation


class ConversationTaskPresenceRequest(BaseModel):
    conversation_ids: List[str] = Field(min_length=1, max_length=100)

    @field_validator('conversation_ids')
    @classmethod
    def valid_ids(cls, values: List[str]) -> List[str]:
        if any(not value or len(value) > 128 or '/' in value or value in {'.', '..'} for value in values):
            raise ValueError('invalid conversation id')
        return list(dict.fromkeys(values))


class ConversationTaskPresenceResponse(BaseModel):
    presence: Dict[str, bool]


class TaskConversationPageRequest(BaseModel):
    query: str = Field(default='', max_length=2000)
    folder_id: Optional[str] = Field(default=None, max_length=128)
    starred: Optional[bool] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    include_discarded: bool = False
    limit: int = Field(default=25, ge=1, le=100)
    cursor: Optional[str] = Field(default=None, max_length=4096)

    @model_validator(mode='after')
    def ordered_dates(self):
        from utils.conversations.list_filters import aware_datetime

        if self.start_date is not None:
            self.start_date = aware_datetime(self.start_date)
        if self.end_date is not None:
            self.end_date = aware_datetime(self.end_date)
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError('start_date must be earlier than or equal to end_date')
        return self


class TaskConversationPageResponse(BaseModel):
    items: List[Conversation]
    next_cursor: Optional[str] = None
    # A bounded scan can return an empty intermediate page. Its cursor must
    # still be followed; it never establishes that the filtered set is empty.
    partial: bool = False
