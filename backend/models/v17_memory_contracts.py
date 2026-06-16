import hashlib
import json
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class LifecycleState(str, Enum):
    working = "working"
    active = "active"
    context_only = "context_only"
    review = "review"
    superseded = "superseded"
    rejected = "rejected"
    hidden = "hidden"


class DurablePatchDecision(str, Enum):
    add = "add"
    update = "update"
    merge = "merge"
    add_evidence = "add_evidence"
    keep_both = "keep_both"
    skip_duplicate = "skip_duplicate"
    context_only = "context_only"
    reject = "reject"
    review = "review"


_STABLE_ALLOWED_USE_BY_STATE = {
    LifecycleState.working: "read_with_status",
    LifecycleState.active: "stable_profile_fact",
    LifecycleState.context_only: "context_only",
    LifecycleState.review: "review_only",
    LifecycleState.superseded: "history_only",
    LifecycleState.rejected: "audit_only",
    LifecycleState.hidden: "hidden",
}

_SECRET_RISK_FLAGS = {"secret", "credential", "pii_secret", "security_sensitive"}


def derive_allowed_use(status: LifecycleState | str, risk_flags: Optional[List[str]] = None) -> str:
    resolved = status if isinstance(status, LifecycleState) else LifecycleState(status)
    normalized_risks = {flag.lower() for flag in (risk_flags or [])}
    if resolved == LifecycleState.hidden or normalized_risks.intersection(_SECRET_RISK_FLAGS):
        return "hidden"
    return _STABLE_ALLOWED_USE_BY_STATE[resolved]


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def deterministic_contract_id(namespace: str, payload: Dict[str, Any]) -> str:
    return hashlib.sha256(f"{namespace}|{_canonical_json(payload)}".encode("utf-8")).hexdigest()


class EvidenceRef(BaseModel):
    evidence_id: str
    source_id: Optional[str] = None
    source_type: Optional[str] = None
    quote: Optional[str] = None
    artifact_ref: Dict[str, Any] = Field(default_factory=dict)


class WorkingMemoryObservation(BaseModel):
    schema_version: str = "working_memory_observation.v1"
    observation_id: str
    packet_id: Optional[str] = None
    content: str
    evidence_ids: List[str] = Field(default_factory=list)
    source_refs: List[Dict[str, Any]] = Field(default_factory=list)
    subject_entity_id: Optional[str] = None
    subject_scope: str = "primary_user"
    status: LifecycleState = LifecycleState.working
    confidence: str = "medium"
    risk_flags: List[str] = Field(default_factory=list)
    route_hint: Optional[str] = None
    allowed_use: Optional[str] = None
    predicate: Optional[str] = None
    arguments: Dict[str, Any] = Field(default_factory=dict)
    qualifiers: Dict[str, Any] = Field(default_factory=dict)
    extractor_version: str = "v17_l1_llm_observation_extractor_v1"

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: str) -> str:
        if value not in {"high", "medium", "low"}:
            raise ValueError("confidence must be high, medium, or low")
        return value

    @model_validator(mode="after")
    def derive_read_policy(self):
        self.allowed_use = derive_allowed_use(self.status, self.risk_flags)
        return self


class L2SearchRequest(BaseModel):
    query: str
    reason: str
    search_type: str = "semantic"
    max_results: int = 5

    @field_validator("max_results")
    @classmethod
    def validate_max_results(cls, value: int) -> int:
        if value < 1 or value > 5:
            raise ValueError("max_results must be between 1 and 5")
        return value


class L2SearchPlan(BaseModel):
    schema_version: str = "l2_custom_search_plan.v1"
    packet_id: str
    search_budget: int = 3
    searches: List[L2SearchRequest] = Field(default_factory=list)
    same_user_only: bool = True
    read_only: bool = True

    @field_validator("search_budget")
    @classmethod
    def validate_budget(cls, value: int) -> int:
        if value < 0 or value > 3:
            raise ValueError("search_budget must be between 0 and 3")
        return value

    @model_validator(mode="after")
    def enforce_search_budget_and_scope(self):
        if len(self.searches) > self.search_budget:
            raise ValueError("searches exceed search_budget")
        if self.same_user_only is not True:
            raise ValueError("same_user_only must be true")
        if self.read_only is not True:
            raise ValueError("read_only must be true")
        return self


class L2SearchResult(BaseModel):
    result_id: str
    content_hash: str
    status: LifecycleState
    source: str
    score: Optional[float] = None
    content: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DurableMemoryPatch(BaseModel):
    schema_version: str = "durable_memory_patch.v1"
    patch_id: str
    packet_id: str
    run_id: str
    observed_head_commit_id: Optional[str]
    idempotency_key: str
    decision: DurablePatchDecision
    result_status: LifecycleState
    evidence_ids: List[str] = Field(default_factory=list)
    target_memory_id: Optional[str] = None
    new_memory_id: Optional[str] = None
    memory_text: Optional[str] = None
    predicate: Optional[str] = None
    arguments: Dict[str, Any] = Field(default_factory=dict)
    supersedes: List[str] = Field(default_factory=list)
    rationale: Optional[str] = None

    @model_validator(mode="after")
    def validate_decision_contract(self):
        if (
            self.decision
            in {
                DurablePatchDecision.merge,
                DurablePatchDecision.update,
                DurablePatchDecision.add_evidence,
                DurablePatchDecision.skip_duplicate,
            }
            and not self.target_memory_id
        ):
            raise ValueError("target_memory_id is required for merge/update/add_evidence/skip_duplicate decisions")
        if self.decision == DurablePatchDecision.add and not self.memory_text and not self.new_memory_id:
            raise ValueError("add decisions require memory_text or new_memory_id")
        return self
