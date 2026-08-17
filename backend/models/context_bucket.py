"""Backend-owned context bucket contracts synced from capture devices.

Only validated facts cross the device boundary. Screenshots, quoted screen text,
narratives, and window titles stay on the capturing device and are named here
only through device-local evidence references.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from models.action_item import EvidenceKind, EvidenceRef, EvidenceScope
from models.task_intelligence import StableId


class BucketSubjectKind(str, Enum):
    app = 'app'
    document = 'document'
    destination = 'destination'
    handle = 'handle'


class FactDispositionState(str, Enum):
    none = 'none'
    candidate_pending = 'candidate_pending'
    task_created = 'task_created'
    update_proposed = 'update_proposed'


class ContextFactSync(BaseModel):
    """A single validated fact as published by a capture device."""

    model_config = ConfigDict(extra='forbid')

    fact_id: StableId
    statement: str = Field(min_length=1, max_length=500)
    identifiers: list[str] = Field(default_factory=list, max_length=8)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    notify_worthiness: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    disposition_state: FactDispositionState = FactDispositionState.none
    workstream_tag: Optional[str] = Field(default=None, max_length=128)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=50)
    expires_at: Optional[datetime] = None
    device_updated_at: datetime

    @model_validator(mode='after')
    def require_local_screen_evidence(self):
        """Bucket facts are extracted from the screen, so their evidence is too.

        Scope alone is not enough: a device_local ref of any other kind would
        claim a conversation or artifact as this fact's provenance, which the
        device cannot vouch for and no consumer could resolve.
        """

        for ref in self.evidence_refs:
            if ref.scope != EvidenceScope.device_local:
                raise ValueError('context fact evidence must stay device_local')
            if ref.kind != EvidenceKind.local_screen:
                raise ValueError('context fact evidence must be local_screen')
        for identifier in self.identifiers:
            if not identifier.strip():
                raise ValueError('identifiers cannot be blank')
        return self


class ContextBucketSync(BaseModel):
    """A bucket plus the validated facts a device wants published for it."""

    model_config = ConfigDict(extra='forbid')

    bucket_id: StableId
    subject_kind: BucketSubjectKind
    subject_id: str = Field(min_length=1, max_length=256)
    workstream_id: Optional[StableId] = None
    display_label: Optional[str] = Field(default=None, max_length=256)
    notify_worthiness: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    visit_count: int = Field(default=0, ge=0)
    last_visited_at: Optional[datetime] = None
    device_updated_at: datetime
    facts: list[ContextFactSync] = Field(default_factory=list, max_length=200)

    @model_validator(mode='after')
    def require_unique_fact_ids(self):
        seen = {fact.fact_id for fact in self.facts}
        if len(seen) != len(self.facts):
            raise ValueError('facts must have unique ids within a bucket')
        return self


class ContextBucketSyncRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    device_id: StableId
    buckets: list[ContextBucketSync] = Field(min_length=1, max_length=50)

    @model_validator(mode='after')
    def require_unique_bucket_ids(self):
        seen = {bucket.bucket_id for bucket in self.buckets}
        if len(seen) != len(self.buckets):
            raise ValueError('buckets must have unique ids within a request')
        facts_seen = {fact.fact_id for bucket in self.buckets for fact in bucket.facts}
        facts_total = sum(len(bucket.facts) for bucket in self.buckets)
        if len(facts_seen) != facts_total:
            raise ValueError('facts must have unique ids across the whole request')
        return self


class ContextBucketSyncReport(BaseModel):
    model_config = ConfigDict(extra='forbid')

    buckets_written: int = Field(ge=0)
    buckets_skipped_stale: int = Field(ge=0)
    facts_written: int = Field(ge=0)
    facts_skipped_stale: int = Field(ge=0)


class ContextFact(BaseModel):
    """A stored fact as read back by consumers."""

    model_config = ConfigDict(extra='forbid')

    fact_id: StableId
    bucket_id: StableId
    statement: str = Field(min_length=1, max_length=500)
    identifiers: list[str] = Field(default_factory=list, max_length=8)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    notify_worthiness: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    disposition_state: FactDispositionState = FactDispositionState.none
    workstream_tag: Optional[str] = Field(default=None, max_length=128)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=50)
    expires_at: Optional[datetime] = None
    device_id: StableId
    device_updated_at: datetime
    created_at: datetime
    updated_at: datetime


class ContextBucket(BaseModel):
    model_config = ConfigDict(extra='forbid')

    bucket_id: StableId
    subject_kind: BucketSubjectKind
    subject_id: str = Field(min_length=1, max_length=256)
    workstream_id: Optional[StableId] = None
    display_label: Optional[str] = Field(default=None, max_length=256)
    notify_worthiness: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    visit_count: int = Field(default=0, ge=0)
    last_visited_at: Optional[datetime] = None
    device_id: StableId
    device_updated_at: datetime
    created_at: datetime
    updated_at: datetime


class ContextBucketPurgeRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    bucket_ids: list[StableId] = Field(min_length=1, max_length=200)


class ContextBucketPurgeReport(BaseModel):
    model_config = ConfigDict(extra='forbid')

    buckets_deleted: int = Field(ge=0)
    facts_deleted: int = Field(ge=0)


__all__ = [
    'BucketSubjectKind',
    'ContextBucket',
    'ContextBucketPurgeReport',
    'ContextBucketPurgeRequest',
    'ContextBucketSync',
    'ContextBucketSyncReport',
    'ContextBucketSyncRequest',
    'ContextFact',
    'ContextFactSync',
    'FactDispositionState',
]
