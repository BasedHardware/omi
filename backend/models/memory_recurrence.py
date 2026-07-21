"""Neutral canonical-memory recurrence signal consumed by workflow orchestration."""

import hashlib

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from models.action_item import EvidenceKind, EvidenceRef, EvidenceScope
from models.task_intelligence import StableId


class CanonicalRecurrenceSignal(BaseModel):
    """A repeated unresolved open loop observed during canonical consolidation.

    The memory domain may emit this evidence contract, but it never writes a
    Candidate or workstream. Workflow owns qualification and mutation.
    """

    model_config = ConfigDict(extra='forbid', frozen=True)

    signal_id: StableId
    title: str = Field(min_length=1, max_length=256)
    objective: str = Field(min_length=1, max_length=2048)
    anchor_task_description: str = Field(min_length=1, max_length=2000)
    occurrence_count: int = Field(ge=1)
    distinct_day_count: int = Field(ge=1)
    unresolved: bool
    confidence: float = Field(ge=0, le=1)
    first_seen_at: AwareDatetime
    last_seen_at: AwareDatetime
    evidence_refs: list[EvidenceRef] = Field(min_length=1, max_length=50)

    @field_validator('evidence_refs')
    @classmethod
    def validate_canonical_memory_evidence(cls, refs: list[EvidenceRef]) -> list[EvidenceRef]:
        if any(
            ref.scope != EvidenceScope.canonical
            or ref.kind not in {EvidenceKind.memory_item, EvidenceKind.conversation}
            for ref in refs
        ):
            raise ValueError('recurrence evidence must reference canonical memory or conversations')
        return refs

    @model_validator(mode='after')
    def validate_temporal_consistency(self):
        if self.first_seen_at > self.last_seen_at:
            raise ValueError('first_seen_at must not be after last_seen_at')
        if self.distinct_day_count > self.occurrence_count:
            raise ValueError('distinct_day_count cannot exceed occurrence_count')
        inclusive_day_span = (self.last_seen_at.date() - self.first_seen_at.date()).days + 1
        if self.distinct_day_count > inclusive_day_span:
            raise ValueError('distinct_day_count cannot exceed the observed date span')
        return self

    @property
    def stable_loop_key(self) -> str:
        """Canonical identity anchored to the first-seen evidence, not model wording."""
        anchor = self.evidence_refs[0]
        payload = f'{anchor.scope.value}:{anchor.kind.value}:{anchor.id}'
        return f'recurrence_loop_{hashlib.sha256(payload.encode("utf-8")).hexdigest()[:40]}'


__all__ = ['CanonicalRecurrenceSignal']
