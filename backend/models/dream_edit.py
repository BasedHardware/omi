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
    target: str = Field(
        description='Supplied record ref to edit. One spelling edit fixes every occurrence in this target.'
    )
    other: str = Field(
        default='',
        description='Only the second supplied record ref for merge_people or merge_memories. Empty for every non-merge edit.',
    )
    before: str = Field(
        default='',
        description='Exact wrong text as it appears in the target, including its capitalization. For spelling, one edit fixes every occurrence of this text.',
    )
    after: str = Field(
        default='',
        description='The corrected text, not a record ref. Required and nonempty for spelling, title and overview edits.',
    )
    reason: str = Field(min_length=1, max_length=1000)
    evidence: list[str] = Field(min_length=1, max_length=10)

    @model_validator(mode='after')
    def field_semantics(self):
        if self.kind not in {'merge_people', 'merge_memories'} and self.other:
            raise ValueError('Only merge edits may name a second record')
        if self.kind in {'spelling', 'title', 'overview'} and not self.after.strip():
            raise ValueError('Text edits require corrected text in after')
        if self.kind == 'spelling' and not self.before.strip():
            raise ValueError('Spelling edits require exact wrong text in before')
        return self

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
