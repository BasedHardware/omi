import json
import hashlib
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from models.memory_evidence import MemoryEvidence, SourceState

DEFAULT_SHORT_TERM_TTL = timedelta(hours=48)
DEFAULT_SHORT_TERM_TTL_DAYS = 2
RESTRICTED_SENSITIVITY_LABELS = frozenset(
    {
        "credential",
        "secret",
        "financial",
        "health",
        "intimate",
        "minor",
        "minors",
        "workplace_confidential",
        "identity_authentication",
    }
)


class MemoryLayer(str, Enum):
    short_term = "short_term"
    long_term = "long_term"
    archive = "archive"


# Legacy memory name — same enum, kept for backward-compatible imports.
MemoryTier = MemoryLayer


class MemoryKind(str, Enum):
    """Semantic kind for the intent-backed knowledge ledger.

    ``tier`` remains a storage-compatibility projection during the client
    migration. It is not the lifecycle authority for ledger rows.
    """

    fact = "fact"
    document = "document"
    trigger = "trigger"


class MemorySubjectScope(str, Enum):
    primary_user = "primary_user"
    user_owned_project = "user_owned_project"
    user_relationship = "user_relationship"
    third_party = "third_party"


class LedgerWriteReason(str, Enum):
    direct_user_statement = "direct_user_statement"
    explicit_remember = "explicit_remember"
    agent_reusable_conclusion = "agent_reusable_conclusion"
    recurring_workflow = "recurring_workflow"
    standing_trigger = "standing_trigger"
    onboarding = "onboarding"
    daily_reconciliation = "daily_reconciliation"
    legacy_migration = "legacy_migration"


MAX_LEDGER_CONTENT_CHARACTERS = 4_000
MAX_LEDGER_PLAYBOOK_BODY_CHARACTERS = 24_000
MAX_LEDGER_SLOT_CHARACTERS = 64
# Twelve deterministic selectors plus one separately governed action object.
MAX_LEDGER_TRIGGER_CONDITION_KEYS = 13
MAX_LEDGER_TRIGGER_CONDITION_CHARACTERS = 8_000
MAX_MEMORY_ARGUMENTS_JSON_BYTES = 8 * 1024


def normalized_memory_content_key(content: Optional[str]) -> Optional[str]:
    """Stable casefolded content identity used by authority-safe dedupe."""

    if content is None:
        return None
    normalized = " ".join(unicodedata.normalize("NFKC", content).casefold().split())
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class MemoryItemStatus(str, Enum):
    active = "active"
    superseded = "superseded"
    hidden = "hidden"
    tombstoned = "tombstoned"


class ProcessingState(str, Enum):
    pending = "pending"
    processed = "processed"
    blocked = "blocked"


class MemoryConsumer(str, Enum):
    omi_chat = "omi_chat"
    agent = "agent"
    third_party = "third_party"
    developer_api = "developer_api"
    mcp = "mcp"
    admin_debug = "admin_debug"
    eval = "eval"
    unknown = "unknown"


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True)
class MemoryAccessPolicy:
    consumer: MemoryConsumer
    app_has_default_memory_grant: bool = False
    archive_capability: bool = False
    raw_provenance_capability: bool = False

    @classmethod
    def for_omi_chat(cls, archive_capability: bool = False) -> "MemoryAccessPolicy":
        return cls(
            consumer=MemoryConsumer.omi_chat, app_has_default_memory_grant=True, archive_capability=archive_capability
        )

    @classmethod
    def for_third_party(
        cls, app_has_default_memory_grant: bool = False, archive_capability: bool = False
    ) -> "MemoryAccessPolicy":
        return cls(
            consumer=MemoryConsumer.third_party,
            app_has_default_memory_grant=app_has_default_memory_grant,
            archive_capability=archive_capability,
        )


class MemoryItemAlias(BaseModel):
    old_memory_id: str
    canonical_memory_id: str
    uid: str
    reason: str
    created_at: datetime

    @model_validator(mode="after")
    def validate_alias(self):
        if self.old_memory_id == self.canonical_memory_id:
            raise ValueError("alias cannot point to self")
        return self


MemoryItemAlias = MemoryItemAlias


class MemoryItem(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    memory_id: str
    uid: str
    canonical_memory_id: Optional[str] = None
    version: int
    tier: MemoryLayer
    status: MemoryItemStatus
    processing_state: ProcessingState
    content: Optional[str]
    normalized_content_key: Optional[str] = None
    evidence: List[MemoryEvidence] = Field(default_factory=list)
    source_state: SourceState
    sensitivity_labels: List[str]
    visibility: str
    user_asserted: bool
    captured_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None
    ledger_commit_id: Optional[str] = None
    ledger_sequence: Optional[int] = None
    item_revision: int = 1
    source_commit_id: Optional[str] = None
    source_commit_sequence: Optional[int] = None
    content_hash: Optional[str] = None
    account_generation: int = 0
    promotion: Optional[Dict[str, Any]] = None
    capture_device_ids: List[str] = Field(default_factory=list)
    primary_capture_device: Optional[str] = None
    corroboration_count: int = 0
    last_corroborated_at: Optional[datetime] = None
    half_life_days: Optional[float] = None
    belief_class: Optional[str] = None
    confidence: Optional[float] = None
    superseded_by: Optional[str] = None
    subject_entity_id: Optional[str] = None
    predicate: Optional[str] = None
    arguments: Dict[str, Any] = Field(default_factory=dict)
    kg_extracted: bool = False
    graph_ready: bool = False
    graph_assertion_id: Optional[str] = None
    graph_plan_hash: Optional[str] = None
    ledger_schema_version: Optional[str] = None
    kind: MemoryKind = MemoryKind.fact
    subject_scope: MemorySubjectScope = MemorySubjectScope.primary_user
    slot: Optional[str] = None
    body: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    curation_weight: int = 0
    trigger_condition: Dict[str, Any] = Field(default_factory=dict)
    intent_backed: bool = False
    write_reason: Optional[LedgerWriteReason] = None

    @field_validator("memory_id", "uid", "visibility")
    @classmethod
    def validate_nonblank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("required fields must not be blank")
        return value

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: int) -> int:
        if value < 1:
            raise ValueError("version must be positive")
        return value

    @field_validator("captured_at", "updated_at", "expires_at", "valid_from", "valid_to")
    @classmethod
    def validate_timezone(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("timestamps must be timezone-aware")
        return value

    @field_validator("sensitivity_labels")
    @classmethod
    def normalize_sensitivity(cls, value: List[str]) -> List[str]:
        return sorted({label.strip().lower() for label in value if label and label.strip()})

    @field_validator("slot")
    @classmethod
    def normalize_slot(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = "_".join(value.strip().lower().replace("-", "_").split())
        return normalized or None

    @field_validator("curation_weight")
    @classmethod
    def validate_curation_weight(cls, value: int) -> int:
        if value < -100 or value > 100:
            raise ValueError("curation_weight must be between -100 and 100")
        return value

    @field_validator("trigger_condition")
    @classmethod
    def validate_trigger_condition_size(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        try:
            encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError("trigger_condition must be JSON serializable") from exc
        if len(encoded) > MAX_LEDGER_TRIGGER_CONDITION_CHARACTERS:
            raise ValueError("ledger trigger condition exceeds the serialized limit")
        return value

    @computed_field(return_type=List[str])
    @property
    def source_ids(self) -> List[str]:
        """Exact query projection of the current embedded evidence identities."""
        return sorted(
            {
                source_id
                for evidence in self.evidence
                for source_id in (evidence.source_id, evidence.conversation_id)
                if source_id
            }
        )

    @model_validator(mode="after")
    def validate_tier_invariants(self):
        expected_content_key = normalized_memory_content_key(self.content)
        if self.normalized_content_key != expected_content_key:
            object.__setattr__(self, "normalized_content_key", expected_content_key)
        if self.updated_at < self.captured_at:
            raise ValueError("updated_at must be >= captured_at")
        if self.status == MemoryItemStatus.active and not (self.content or "").strip():
            raise ValueError("active memory requires content")
        if self.tier == MemoryLayer.short_term:
            if self.expires_at is None:
                raise ValueError("short_term memory requires expires_at")
            if self.expires_at <= self.captured_at:
                raise ValueError("short_term expires_at must be after captured_at")
        if self.tier == MemoryLayer.long_term and self.status == MemoryItemStatus.active:
            if not self.ledger_commit_id:
                raise ValueError("active long_term memory requires ledger_commit_id")
            if self.ledger_sequence is None:
                raise ValueError("active long_term memory requires ledger_sequence")
            if self.processing_state != ProcessingState.processed:
                raise ValueError("active long_term memory requires processing_state=processed")
            admission = (self.promotion or {}).get("admission_receipt")
            if admission is not None and (
                not self.graph_ready or not self.graph_assertion_id or not self.graph_plan_hash
            ):
                raise ValueError("admitted long_term memory requires an atomic graph assertion")
        if self.source_state == SourceState.active and not self.user_asserted:
            if not any(e.source_state == SourceState.active for e in self.evidence):
                raise ValueError("active source memory requires at least one active evidence record")
        if self.valid_to is not None:
            lower_bound = self.valid_from or self.captured_at
            if self.valid_to < lower_bound:
                raise ValueError("valid_to must be >= valid_from")
        if self.kind != MemoryKind.fact and self.slot is not None:
            raise ValueError("only fact ledger rows may define a slot")
        if self.kind == MemoryKind.trigger and not self.trigger_condition:
            raise ValueError("trigger ledger rows require trigger_condition")
        if self.kind != MemoryKind.trigger and self.trigger_condition:
            raise ValueError("trigger_condition is only valid for trigger ledger rows")
        if self.ledger_schema_version == "knowledge_ledger.v1":
            if len(self.content or "") > MAX_LEDGER_CONTENT_CHARACTERS:
                raise ValueError("knowledge ledger content exceeds the ledger limit")
            if len(self.slot or "") > MAX_LEDGER_SLOT_CHARACTERS:
                raise ValueError("knowledge ledger slot exceeds the ledger limit")
            if self.kind == MemoryKind.document:
                if not (self.body or "").strip():
                    raise ValueError("ledger documents require a non-empty body")
                if len(self.body or "") > MAX_LEDGER_PLAYBOOK_BODY_CHARACTERS:
                    raise ValueError("ledger document body exceeds the ledger limit")
            elif self.body is not None:
                raise ValueError("ledger body is only valid for document rows")
            if len(self.trigger_condition) > MAX_LEDGER_TRIGGER_CONDITION_KEYS:
                raise ValueError("ledger trigger condition exceeds the ledger key limit")
            if self.write_reason is None or (
                not self.intent_backed and self.write_reason != LedgerWriteReason.legacy_migration
            ):
                raise ValueError("knowledge ledger rows require an intent-backed write reason")
        return self


MemoryItem = MemoryItem


def memory_item_has_lifecycle_metadata(item: MemoryItem) -> bool:
    """Return whether a row still carries legacy lifecycle audit metadata."""

    return item.promotion is not None


def new_memory_id() -> str:
    return f"mem_{uuid.uuid4().hex}"


def _coerce_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def default_short_term_expiry(captured_at: datetime) -> datetime:
    return _coerce_aware_utc(captured_at) + DEFAULT_SHORT_TERM_TTL


def effective_short_term_expiry(item: MemoryItem) -> datetime:
    """Return the sooner of stored expiry and the current 48-hour policy.

    Already-written Short-term rows may still carry a 30-day ``expires_at``.
    Reads, promotion, and TTL decisions use this so those rows cannot linger
    past the live policy window.
    """
    policy_expiry = default_short_term_expiry(item.captured_at)
    stored = _coerce_aware_utc(item.expires_at) if item.expires_at is not None else policy_expiry
    return min(stored, policy_expiry)


def _base_policy_checks(item: MemoryItem, policy: MemoryAccessPolicy, now: datetime) -> Optional[AccessDecision]:
    if item.status != MemoryItemStatus.active:
        return AccessDecision(False, "not_active")
    if item.processing_state == ProcessingState.blocked:
        return AccessDecision(False, "processing_blocked")
    if item.source_state in {SourceState.tombstoned, SourceState.purged}:
        return AccessDecision(False, "source_not_active")
    if policy.consumer == MemoryConsumer.unknown:
        return AccessDecision(False, "unknown_consumer")
    if _has_restricted_sensitivity(item):
        return AccessDecision(False, "restricted_sensitivity")
    if item.visibility not in {"private", "public", "shared"}:
        return AccessDecision(False, "unknown_visibility")
    return None


def _has_restricted_sensitivity(item: MemoryItem) -> bool:
    return bool(set(item.sensitivity_labels).intersection(RESTRICTED_SENSITIVITY_LABELS))


def is_default_access_eligible(
    item: MemoryItem, policy: MemoryAccessPolicy, now: Optional[datetime] = None
) -> AccessDecision:
    current_time = now or datetime.now(timezone.utc)
    base = _base_policy_checks(item, policy, current_time)
    if base is not None:
        return base
    if item.tier == MemoryLayer.archive:
        return AccessDecision(False, "archive_requires_explicit_query")
    if policy.consumer in {MemoryConsumer.third_party, MemoryConsumer.developer_api, MemoryConsumer.mcp}:
        if not policy.app_has_default_memory_grant:
            return AccessDecision(False, "missing_default_memory_grant")
    if item.tier == MemoryLayer.short_term and effective_short_term_expiry(item) <= current_time:
        # Time alone is not a terminal lifecycle decision. Active Short-term
        # rows remain readable until canonical apply records promote/archive/
        # review/reject and moves them out of this state.
        return AccessDecision(True, "short_term_expired_pending_adjudication")
    if item.tier in {MemoryLayer.short_term, MemoryLayer.long_term}:
        return AccessDecision(True, "default_memory_allowed")
    return AccessDecision(False, "unsupported_tier")


def is_archive_access_eligible(
    item: MemoryItem, policy: MemoryAccessPolicy, now: Optional[datetime] = None
) -> AccessDecision:
    current_time = now or datetime.now(timezone.utc)
    base = _base_policy_checks(item, policy, current_time)
    if base is not None:
        return base
    if item.tier != MemoryLayer.archive:
        return AccessDecision(False, "not_archive")
    if not policy.archive_capability:
        return AccessDecision(False, "missing_archive_capability")
    return AccessDecision(True, "archive_explicit_allowed")


def derived_default_access_allowed(item: MemoryItem, consumer: str) -> bool:
    try:
        policy = MemoryAccessPolicy(consumer=MemoryConsumer(consumer), app_has_default_memory_grant=True)
    except ValueError:
        policy = MemoryAccessPolicy(consumer=MemoryConsumer.unknown)
    return is_default_access_eligible(item, policy).allowed


__all__ = [
    "AccessDecision",
    "DEFAULT_SHORT_TERM_TTL",
    "DEFAULT_SHORT_TERM_TTL_DAYS",
    "MemoryAccessPolicy",
    "MemoryConsumer",
    "MemoryItem",
    "MemoryItemAlias",
    "MemoryItemStatus",
    "MemoryLayer",
    "MemoryTier",
    "ProcessingState",
    "MemoryItem",
    "MemoryItemAlias",
    "default_short_term_expiry",
    "derived_default_access_allowed",
    "effective_short_term_expiry",
    "is_archive_access_eligible",
    "is_default_access_eligible",
    "new_memory_id",
]
