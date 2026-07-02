from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

ReplyDraftTone = Literal['natural', 'warm', 'brief', 'professional', 'playful']
ReplyDraftLength = Literal['short', 'medium', 'long']
MAX_REPLY_DRAFT_LENGTH = 3000
MAX_REPLY_DRAFT_ALTERNATIVES = 2
MAX_REPLY_DRAFT_SAFETY_NOTES = 5


def _strip_required_text(value):
    if isinstance(value, str):
        return value.strip()
    return value


def _strip_text_list(value):
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return value


class ReplyDraftRequest(BaseModel):
    incoming_message: str = Field(..., min_length=1, max_length=4000)
    recipient_name: Optional[str] = Field(default=None, max_length=120)
    channel: Optional[str] = Field(default=None, max_length=40)
    relationship: Optional[str] = Field(default=None, max_length=500)
    goal: Optional[str] = Field(default=None, max_length=800)
    extra_context: Optional[str] = Field(default=None, max_length=2000)
    tone: ReplyDraftTone = 'natural'
    length: ReplyDraftLength = 'medium'
    include_memories: bool = True
    include_recent_chat: bool = True

    @field_validator(
        'incoming_message', 'recipient_name', 'channel', 'relationship', 'goal', 'extra_context', mode='before'
    )
    @classmethod
    def _strip_blank_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class ReplyDraftGeneration(BaseModel):
    draft: str = Field(..., min_length=1, max_length=MAX_REPLY_DRAFT_LENGTH)
    alternatives: List[str] = Field(default_factory=list, max_length=MAX_REPLY_DRAFT_ALTERNATIVES)
    safety_notes: List[str] = Field(default_factory=list, max_length=MAX_REPLY_DRAFT_SAFETY_NOTES)

    @field_validator('draft', mode='before')
    @classmethod
    def _strip_draft(cls, value):
        return _strip_required_text(value)

    @field_validator('alternatives', 'safety_notes', mode='before')
    @classmethod
    def _strip_lists(cls, value):
        return _strip_text_list(value)


class ReplyDraftContextSummary(BaseModel):
    memories_used: int
    recent_chat_messages_used: int


class ReplyDraftResponse(BaseModel):
    draft: str = Field(..., min_length=1, max_length=MAX_REPLY_DRAFT_LENGTH)
    alternatives: List[str] = Field(default_factory=list, max_length=MAX_REPLY_DRAFT_ALTERNATIVES)
    needs_review: bool = True
    safety_notes: List[str] = Field(default_factory=list, max_length=MAX_REPLY_DRAFT_SAFETY_NOTES)
    used_context: ReplyDraftContextSummary

    @field_validator('draft', mode='before')
    @classmethod
    def _strip_draft(cls, value):
        return _strip_required_text(value)

    @field_validator('alternatives', 'safety_notes', mode='before')
    @classmethod
    def _strip_lists(cls, value):
        return _strip_text_list(value)
