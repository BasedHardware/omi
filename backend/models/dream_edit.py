"""Typed edits shared by Dream planning and the Review proposal contract."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Edit(Strict):
    kind: Literal[
        'spelling',
        'title',
        'overview',
        'memory',
        'merge_people',
        'entity_summary',
        'close_task',
        'retire_task',
        'merge_memories',
    ]
    target: str
    other: str = ''
    before: str = ''
    after: str = ''
    reason: str = Field(min_length=1, max_length=1000)
    evidence: list[str] = Field(min_length=1, max_length=10)

    @model_validator(mode='after')
    def conversation_summary(self):
        if self.kind in {'title', 'overview'}:
            collection, separator, key = self.target.partition('/')
            if collection != 'conversations' or not separator or not key or '/' in key:
                raise ValueError('Summary edits require a conversation target')
            if self.target not in self.evidence or self.other:
                raise ValueError('Summary edits require their conversation as evidence and no other target')
            limit = 120 if self.kind == 'title' else 1000
            if not self.after.strip() or len(self.after) > limit or self.before == self.after:
                raise ValueError('Summary edits require a short changed value')
        return self


class Term(Strict):
    kind: Literal['person', 'organization', 'project', 'jargon']
    spelling: str = Field(min_length=1, max_length=50)
    aliases: list[str] = Field(default_factory=list, max_length=5)
    evidence: list[str] = Field(min_length=1, max_length=10)
