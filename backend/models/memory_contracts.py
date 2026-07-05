import hashlib
import json
from enum import Enum
from typing import Any, Dict, List, Optional
from typing import Literal

from pydantic import AliasChoices, AwareDatetime, BaseModel, Field, field_validator, model_validator

from models.product_memory import MemoryTier

# Neutral fact-source string for new durable-memory patch ledger writes (schema literal unchanged).
DURABLE_MEMORY_PATCH_FACT_SOURCE = "durable_memory_patch"


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


class L1MemoryArchiveClass(str, Enum):
    general = "general"
    sensitive = "sensitive"


class L1MemoryArchiveItem(BaseModel):
    schema_version: str = "l1_memory_archive_item.v1"
    archive_id: str = ""
    user_id: str = ""
    source_id: str = ""
    source_type: str = ""
    text: str
    archive_class: L1MemoryArchiveClass = Field(
        default=L1MemoryArchiveClass.general,
        validation_alias=AliasChoices("archive_class", "class"),
        serialization_alias="class",
    )
    source_refs: List[Dict[str, Any]] = Field(default_factory=list[Dict[str, Any]])
    evidence_quotes: List[str] = Field(default_factory=list)
    speaker_label: Optional[str] = None
    speaker_scope: str = "session-local"
    # Who/what this item is about — free text, e.g. "the user", "Sarah (girlfriend)",
    # "unidentified non-primary speaker (speaker_1)", "Omi project", "Milo (cat)",
    # "Dr. Patel". Empty/unknown should be treated as uncertain, not as a named user.
    about: str = ""
    confidence: str = "medium"
    risk_flags: List[str] = Field(default_factory=list)
    allowed_use: Optional[str] = None
    normal_search_allowed: bool = True
    is_stable_profile_fact: bool = False
    search_result_label: str = "archived_evidence_not_stable_memory"
    extractor_version: str = "short_term_archive_llm_v1"

    @field_validator("confidence")
    @classmethod
    def validate_archive_confidence(cls, value: str) -> str:
        if value not in {"high", "medium", "low"}:
            raise ValueError("confidence must be high, medium, or low")
        return value

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        stripped = (value or "").strip()
        if not stripped:
            raise ValueError("text is required")
        return stripped

    @model_validator(mode="after")
    def derive_archive_policy_and_id(self):
        normalized_risks = {flag.lower() for flag in (self.risk_flags or [])}
        if normalized_risks.intersection(_SECRET_RISK_FLAGS):
            self.archive_class = L1MemoryArchiveClass.sensitive
        if self.archive_class == L1MemoryArchiveClass.sensitive:
            self.normal_search_allowed = False
            self.allowed_use = "restricted_archive_only"
        else:
            self.normal_search_allowed = True
            self.allowed_use = "archive_search"
        self.is_stable_profile_fact = False
        self.search_result_label = "archived_evidence_not_stable_memory"
        if not self.archive_id:
            payload = {
                "user_id": self.user_id,
                "source_id": self.source_id,
                "source_type": self.source_type,
                "text": self.text,
                "evidence_quotes": self.evidence_quotes,
            }
            self.archive_id = "l1_" + deterministic_contract_id("l1-archive-item", payload)[:20]
        return self


def filter_l1_archive_for_normal_search(
    items: List[L1MemoryArchiveItem], query: Optional[str] = None
) -> List[L1MemoryArchiveItem]:
    query_terms = {term.lower() for term in (query or "").split() if term.strip()}
    results = [
        item for item in items if item.archive_class == L1MemoryArchiveClass.general and item.normal_search_allowed
    ]
    if query_terms:

        def score(item: L1MemoryArchiveItem) -> tuple[int, str]:
            haystack = " ".join([item.text, " ".join(item.evidence_quotes)]).lower()
            return (sum(1 for term in query_terms if term in haystack), item.archive_id)

        results = [item for item in results if score(item)[0] > 0]
        results.sort(key=score, reverse=True)
    return results


class WorkingMemoryObservation(BaseModel):
    schema_version: str = "working_memory_observation.v1"
    observation_id: str = ""
    packet_id: Optional[str] = None
    content: str
    evidence_ids: List[str] = Field(default_factory=list)
    source_refs: List[Dict[str, Any]] = Field(default_factory=list[Dict[str, Any]])
    subject_entity_id: Optional[str] = None
    subject_scope: str = "primary_user"
    literal_observation: Optional[str] = None
    speaker_attribution: str = "unknown"
    source_mode: str = "unclear"
    relationship_to_user: str = "unclear"
    subject: str = "unclear"
    interpretation_level: str = "literal"
    why_captured: Optional[str] = None
    status: LifecycleState = LifecycleState.working
    confidence: str = "medium"
    risk_flags: List[str] = Field(default_factory=list)
    route_hint: Optional[str] = None
    allowed_use: Optional[str] = None
    predicate: Optional[str] = None
    arguments: Dict[str, Any] = Field(default_factory=dict)
    qualifiers: Dict[str, Any] = Field(default_factory=dict)
    extractor_version: str = "short_term_llm_observation_extractor_v1"

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: str) -> str:
        if value not in {"high", "medium", "low"}:
            raise ValueError("confidence must be high, medium, or low")
        return value

    @field_validator("speaker_attribution")
    @classmethod
    def normalize_speaker_attribution(cls, value: str) -> str:
        normalized = (value or "unknown").strip().lower()
        aliases = {
            "user": "primary_user",
            "primary": "primary_user",
            "non_primary": "non_primary_speaker",
            "other": "non_primary_speaker",
            "ai": "assistant",
        }
        normalized = aliases.get(normalized, normalized)
        return (
            normalized if normalized in {"primary_user", "non_primary_speaker", "assistant", "unknown"} else "unknown"
        )

    @field_validator("source_mode")
    @classmethod
    def normalize_source_mode(cls, value: str) -> str:
        normalized = (value or "unclear").strip().lower()
        aliases = {
            "chat": "conversation",
            "voice": "conversation",
            "tutorial": "media_or_tutorial",
            "media": "media_or_tutorial",
            "ocr": "ui_or_ocr",
            "ui": "ui_or_ocr",
            "game": "game_or_story",
            "story": "game_or_story",
        }
        normalized = aliases.get(normalized, normalized)
        return (
            normalized
            if normalized
            in {
                "conversation",
                "assistant_response",
                "media_or_tutorial",
                "ui_or_ocr",
                "game_or_story",
                "document",
                "unclear",
            }
            else "unclear"
        )

    @field_validator("relationship_to_user")
    @classmethod
    def normalize_relationship_to_user(cls, value: str) -> str:
        normalized = (value or "unclear").strip().lower()
        aliases = {
            "primary_user": "self",
            "user": "self",
            "user_owned_project": "owned_work",
            "owned_project": "owned_work",
            "question": "asking_about",
            "asked_about": "asking_about",
            "watched": "encountered",
            "heard": "encountered",
            "other": "other_speaker",
            "third_party": "other_speaker",
        }
        normalized = aliases.get(normalized, normalized)
        return (
            normalized
            if normalized
            in {"self", "owned_work", "adopted", "asking_about", "encountered", "other_speaker", "unclear"}
            else "unclear"
        )

    @field_validator("subject")
    @classmethod
    def normalize_subject(cls, value: str) -> str:
        """Allow arbitrary subject descriptions — not restricted to a fixed enum.

        Common aliases are normalized for consistency, but any descriptive value
        is accepted (e.g. "Milo (cat)", "Sarah", "neighborhood coffee shop").
        """
        normalized = (value or "unclear").strip()
        if not normalized:
            return "unclear"
        aliases = {
            "user": "self",
            "primary_user": "self",
            "project": "owned_project",
            "relationship": "person",
            "third_party": "other",
            "generic": "general",
        }
        return aliases.get(normalized.lower(), normalized)

    @field_validator("interpretation_level")
    @classmethod
    def normalize_interpretation_level(cls, value: str) -> str:
        normalized = (value or "literal").strip().lower()
        aliases = {"light": "light_inference", "heavy": "heavy_inference", "inferred": "light_inference"}
        normalized = aliases.get(normalized, normalized)
        return normalized if normalized in {"literal", "light_inference", "heavy_inference"} else "literal"

    @model_validator(mode="after")
    def derive_read_policy(self):
        self.allowed_use = derive_allowed_use(self.status, self.risk_flags)
        return self


class SourceBackedMemoryCandidate(BaseModel):
    schema_version: str = "source_backed_memory_candidate.v1"
    candidate_id: str
    user_id: str
    source_id: str
    source_type: str
    source_version: str
    text: str
    evidence_ids: List[str] = Field(default_factory=list)
    source_refs: List[Dict[str, Any]] = Field(default_factory=list[Dict[str, Any]])
    captured_at: AwareDatetime
    expires_at: AwareDatetime
    initial_tier: MemoryTier = MemoryTier.short_term
    archive_id: Optional[str] = None
    default_access_candidate: bool = True
    risk_flags: List[str] = Field(default_factory=list)
    extractor_version: str = "source_backed_candidate_v1"

    @field_validator("candidate_id", "user_id", "source_id", "source_type", "source_version", "text")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        stripped = (value or "").strip()
        if not stripped:
            raise ValueError("required source-backed candidate fields must be non-empty")
        return stripped

    @model_validator(mode="after")
    def validate_candidate_tier(self):
        normalized_risks = {flag.lower().strip() for flag in self.risk_flags if flag and flag.strip()}
        if self.initial_tier == MemoryTier.archive:
            self.default_access_candidate = False
        else:
            self.initial_tier = MemoryTier.short_term
            self.archive_id = None
            self.default_access_candidate = not bool(normalized_risks.intersection(_SECRET_RISK_FLAGS))
        if self.expires_at <= self.captured_at:
            raise ValueError("expires_at must be after captured_at")
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


class L2MemoryRoute(BaseModel):
    schema_version: str = "l2_memory_route.v1"
    route: Literal["durable", "review", "discard", "hidden"]
    memory_text: Optional[str] = None
    evidence_quotes: List[str] = Field(default_factory=list)
    confidence: str = "medium"
    reason: str
    drop_reason: Optional[
        Literal[
            "ephemeral_chatter",
            "third_party_or_unknown_speaker",
            "ui_or_ocr_context",
            "unsupported_or_too_noisy",
            "secret_or_security_sensitive",
            "duplicate",
            "not_future_useful",
            "missing_user_tie",
        ]
    ] = None

    @field_validator("confidence")
    @classmethod
    def validate_route_confidence(cls, value: str) -> str:
        if value not in {"high", "medium", "low"}:
            raise ValueError("confidence must be high, medium, or low")
        return value

    @model_validator(mode="after")
    def validate_route_contract(self):
        if self.route in {"durable", "review"}:
            if not self.memory_text:
                raise ValueError("durable/review routes require memory_text")
            if not self.evidence_quotes:
                raise ValueError("durable/review routes require exact evidence_quotes")
            if self.drop_reason is not None:
                raise ValueError("durable/review routes must not set drop_reason")
        if self.route in {"discard", "hidden"} and not self.drop_reason:
            raise ValueError("discard/hidden routes require drop_reason")
        if self.route == "hidden" and self.drop_reason != "secret_or_security_sensitive":
            raise ValueError("hidden route requires secret_or_security_sensitive drop_reason")
        return self


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
    evidence_refs: List[EvidenceRef] = Field(default_factory=list)
    target_memory_id: Optional[str] = None
    new_memory_id: Optional[str] = None
    memory_text: Optional[str] = None
    predicate: Optional[str] = None
    arguments: Dict[str, Any] = Field(default_factory=dict)
    supersedes: List[str] = Field(default_factory=list)
    rationale: Optional[str] = None
    confidence: Literal["high", "medium", "low"] = "medium"
    relationship_to_user: Literal[
        "self",
        "owned_work",
        "adopted",
        "asking_about",
        "encountered",
        "other_speaker",
        "unclear",
    ] = "unclear"
    subject_entity_id: Optional[str] = None
    subject_label: Optional[str] = None
    aboutness: Literal["primary_user", "user_owned_project", "user_relationship", "third_party", "unclear"] = "unclear"
    initial_tier: MemoryTier = MemoryTier.long_term
    target_tier: Optional[MemoryTier] = None
    visibility: str = "private"
    user_asserted: bool = False

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
        if (
            self.result_status in {LifecycleState.active, LifecycleState.review}
            and not self.evidence_ids
            and not self.evidence_refs
        ):
            raise ValueError("active/review patches require exact supporting evidence ids or refs")
        return self


# Neutral symbol aliases (WS-G) — same types, canonical names for new code.
WorkingObservation = WorkingMemoryObservation
WorkingObservationArchiveItem = L1MemoryArchiveItem
PromotionRoute = L2MemoryRoute

__all__ = [
    "DURABLE_MEMORY_PATCH_FACT_SOURCE",
    "DurableMemoryPatch",
    "DurablePatchDecision",
    "EvidenceRef",
    "L1MemoryArchiveClass",
    "L1MemoryArchiveItem",
    "L2MemoryRoute",
    "L2SearchPlan",
    "L2SearchRequest",
    "L2SearchResult",
    "LifecycleState",
    "PromotionRoute",
    "SourceBackedMemoryCandidate",
    "DURABLE_MEMORY_PATCH_FACT_SOURCE",
    "WorkingMemoryObservation",
    "WorkingObservation",
    "WorkingObservationArchiveItem",
    "derive_allowed_use",
    "deterministic_contract_id",
    "filter_l1_archive_for_normal_search",
]
