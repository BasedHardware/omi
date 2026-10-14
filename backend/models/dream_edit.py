"""Typed edits shared by Dream planning and the Review proposal contract."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from models.agent_refs import base_ref


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
    ] = Field(
        description='Spelling corrects a misheard or misspelled name or term. Never rewrite grammar, remove filler, or guess unclear speech.'
    )
    target: str = Field(
        description='Supplied record ref to edit, optionally with #segment-id or #start-seconds. One spelling edit fixes every occurrence in its target; with a fragment, only that transcript segment is changed.'
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
            if base_ref(self.target) not in {base_ref(ref) for ref in self.evidence} or self.other:
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


QUESTION_VALUE_DESCRIPTION = (
    "how much the answer changes what future agents should believe about this person's people, projects or vocabulary; "
    'trivial acronym casing is 1'
)


MEMORY_HYGIENE_KINDS = frozenset({'merge_memories', 'retire_memory', 'supersede_memory'})


class MemoryHygieneEdit(Strict):
    kind: Literal['retire_memory', 'supersede_memory'] = Field(
        description='Retire garbage (not merely low-importance facts), facts misattributed from another speaker, or facts contradicted by evidence. Supersede an old fact only with a newer time-scoped fact about the same attribute; age alone is not staleness.'
    )
    target: str = Field(description=Edit.model_fields['target'].description)
    before: str = Field(default='', description=Edit.model_fields['before'].description)
    other: str = Field(
        default='',
        description='For supersede_memory, the supplied newer memory ref. Otherwise empty. Choose exactly one of other or after.',
    )
    after: str = Field(
        default='',
        max_length=2000,
        description='For supersede_memory without other, the newer time-scoped fact text supported by conversations. Empty for retire_memory.',
    )
    effective_from: str = Field(
        default='',
        max_length=40,
        description='For supersede_memory: optional timezone-aware ISO 8601 time when the cited evidence says the new fact became true. Never invent a time; omit to use apply time.',
    )
    reason: str = Field(
        min_length=1,
        max_length=1000,
        description='Required explanation of garbage, another speaker attribution, contradiction, or the newer fact about the same attribute.',
    )
    evidence: list[str] = Field(
        min_length=1,
        max_length=10,
        description='Supplied conversation refs or other memory refs supporting retirement or replacement. The target alone is not evidence.',
    )

    @model_validator(mode='after')
    def hygiene_semantics(self):
        if self.kind == 'retire_memory' and (self.other or self.after):
            raise ValueError('Retirement changes status only')
        self.after = self.after.strip()
        if self.kind == 'supersede_memory' and bool(self.other) == bool(self.after):
            raise ValueError('Supersede requires exactly one of other or after')
        if not self.reason.strip():
            raise ValueError('Memory hygiene requires a reason')
        return self
