"""Dark, bounded once-per-local-day automatic memory sweep.

This module is an authority seam, not a scheduler.  It accepts a server-built
daily input, writes through the canonical ledger boundary, and stays completely
inert until an explicit backend authority opens it.  The completed-day producer
reads only bounded, finished transcript text (with an optional typed summary
packet), then invokes the existing memory model under an explicit cost budget.

The contract is deliberately small:

* one completed user-local day per input, with at most three missed days per run;
* at most 32 candidates and 16 durable writes per day;
* stable source keys and receipts make retry after a crash an exact no-op;
* direct user statements outrank reusable agent conclusions, which outrank
  sweep inferences;
* fact candidates may be added/amended automatically, while triggers may only
  repair an existing trigger; passive behavior never creates standing intent;
* source references are metadata-only; raw pixels and image payloads are
  rejected before any canonical write;
* account-deletion, owner, canonical-generation, and cursor CAS fences fail
  closed; disabling the authority never deletes already-written user data.

The maintenance job may import the closed scheduler seam, but no current writer
is changed and every runtime call remains inert until backend authority opens.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from dataclasses import dataclass, field
import importlib
import os
import re
from typing import Any, Dict, Iterable, List, Literal, Mapping, Optional, Tuple
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from google.cloud.firestore_v1 import FieldFilter
from google.cloud.firestore_v1.field_path import FieldPath
from google.cloud import firestore
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status
from database.account_deletion_projection_fence import read_account_deletion_projection_fence
from database.firestore_index_registry import (
    DAILY_SWEEP_ACTIVE_FACT_ENTITY_SLOT_QUERY,
    DAILY_SWEEP_ACTIVE_FACT_ENTITY_CONTENT_QUERY,
    DAILY_SWEEP_ACTIVE_FACT_ENTITY_QUERY,
    DAILY_SWEEP_ACTIVE_FACT_SUBJECT_CONTENT_QUERY,
    DAILY_SWEEP_ACTIVE_FACT_SUBJECT_QUERY,
    DAILY_SWEEP_ACTIVE_FACT_SLOT_QUERY,
)
from database.memory_collections import MemoryCollections
from models.memory_apply import MemoryControlState
from models.memory_contracts import deterministic_contract_id
from models.product_memory import (
    LedgerWriteReason,
    MemoryItem,
    MemoryItemStatus,
    MemoryKind,
    MemorySubjectScope,
    normalized_memory_content_key,
)
from utils.memory.canonical_memory_adapter import read_canonical_memory_item
from utils.memory.knowledge_ledger import (
    LedgerProvenance,
    LedgerWrite,
    amend_fact,
    save_ledger_write,
)
from utils.memory.memory_system import ensure_canonical_apply_control_state
from utils.memory.memory_authority import validate_uid_for_memory_path
from utils.memory.jit_trigger_contract import compile_trigger_condition

# These budgets are deliberately separate from the canonical write budget.  A
# completed-day producer must prove that it read the whole bounded source
# window before the cursor can advance; it may never turn an unavailable read
# into an empty day.
MAX_COMPLETED_DAY_CONVERSATIONS = 32
MAX_COMPLETED_DAY_INPUT_CHARACTERS = 48_000
MAX_ONBOARDING_CONVERSATIONS = 8
MAX_ONBOARDING_SCAN_PAGES = 16
MAX_ONBOARDING_INPUT_CHARACTERS = 24_000
MODEL_COST_PER_1K_INPUT_CHARACTERS_USD = 0.002
ONBOARDING_CONSUMED_STATE_PATH = "memory_control/daily_memory_sweep_onboarding"

SCHEMA_VERSION = "daily_memory_sweep.v1"
CURSOR_SCHEMA_VERSION = "daily_memory_sweep_cursor.v1"
RECEIPT_SCHEMA_VERSION = "daily_memory_sweep_receipt.v1"

MAX_CATCH_UP_DAYS = 3
MAX_CANDIDATES_PER_DAY = 32
MAX_WRITES_PER_DAY = 16
MAX_CONTENT_CHARACTERS = 1_200
MAX_SOURCE_ID_CHARACTERS = 256
MAX_SOURCE_REFS = 8
MAX_SOURCE_REF_CHARACTERS = 256
MAX_TRIGGER_CONDITION_KEYS = 12
DAILY_MEMORY_SWEEP_ENABLED_ENV = "MEMORY_DAILY_MEMORY_SWEEP_ENABLED"
DAILY_MEMORY_SWEEP_KILL_SWITCH_ENV = "MEMORY_DAILY_MEMORY_SWEEP_KILL_SWITCH"
DAILY_MEMORY_SWEEP_MODEL_ENABLED_ENV = "MEMORY_DAILY_MEMORY_SWEEP_MODEL_ENABLED"
DAILY_MEMORY_SWEEP_MODEL_NAME_ENV = "MEMORY_DAILY_MEMORY_SWEEP_MODEL_NAME"
DAILY_MEMORY_SWEEP_MAX_MODEL_CANDIDATES_ENV = "MEMORY_DAILY_MEMORY_SWEEP_MAX_MODEL_CANDIDATES"
DAILY_MEMORY_SWEEP_MAX_MODEL_COST_USD_ENV = "MEMORY_DAILY_MEMORY_SWEEP_MAX_MODEL_COST_USD"
DAILY_MEMORY_SWEEP_COHORT_ENABLED_ENV = "MEMORY_DAILY_MEMORY_SWEEP_COHORT_ENABLED"
DAILY_MEMORY_SWEEP_COHORT_NAME_ENV = "MEMORY_DAILY_MEMORY_SWEEP_COHORT_NAME"
DAILY_MEMORY_SWEEP_COHORT_FLAG_ENV = "MEMORY_DAILY_MEMORY_SWEEP_COHORT_FLAG"
DAILY_MEMORY_SWEEP_COHORT_TIMEOUT_ENV = "MEMORY_DAILY_MEMORY_SWEEP_COHORT_TIMEOUT_SECONDS"
DAILY_MEMORY_SWEEP_TIMEZONE_RECONCILIATION_ENV = "MEMORY_DAILY_MEMORY_SWEEP_TIMEZONE_RECONCILIATION_ENABLED"

RECEIPT_LEASE = timedelta(minutes=10)
MAX_AUTHORITATIVE_OCCUPANTS = 2

_ID_RE = re.compile(r"[a-z0-9][a-z0-9._:-]{0,127}")
_FORBIDDEN_SOURCE_MARKERS = (
    "base64",
    "data:image",
    "pixel",
    "raw_image",
    "raw-image",
    "screenshot_bytes",
    "image_bytes",
)
_FORBIDDEN_PAYLOAD_MARKERS = (
    "base64",
    "data:image",
    "image_bytes",
    "raw_image",
    "raw-image",
    "pixel",
    "screenshot",
    "bytes",
    "image",
    "raw",
)
_ALLOWED_SOURCE_TYPES = frozenset(
    {
        "conversation",
        "daily_summary",
        "explicit_user_statement",
        "onboarding",
        "agent_conclusion",
        "screen_metadata",
    }
)


def _reject_payload(value: Any, *, depth: int = 0, nodes: int = 0) -> None:
    """Reject image/raw/base64-shaped values recursively before compilation.

    Trigger conditions are metadata selectors, never a transport for pixels or
    opaque model payloads.  The recursive walk is intentionally stricter than
    the canonical model's JSON check and bounded to keep validation cheap.
    """

    if depth > 8 or nodes > 128:
        raise ValueError("trigger condition nesting exceeds the daily sweep budget")
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise ValueError("raw image/pixel payloads are not valid trigger metadata")
    if isinstance(value, str):
        lowered = value.casefold()
        if any(marker in lowered for marker in _FORBIDDEN_PAYLOAD_MARKERS):
            raise ValueError("raw image/base64 payloads are not valid trigger metadata")
        if len(value) > 300:
            raise ValueError("trigger condition values are oversized")
        return
    if isinstance(value, Mapping):
        if len(value) > MAX_TRIGGER_CONDITION_KEYS:
            raise ValueError("trigger condition exceeds the daily sweep budget")
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip() or len(key) > 64:
                raise ValueError("trigger condition keys must be bounded strings")
            lowered_key = key.casefold()
            if any(marker in lowered_key for marker in _FORBIDDEN_PAYLOAD_MARKERS):
                raise ValueError("raw image/base64 fields are not valid trigger metadata")
            _reject_payload(item, depth=depth + 1, nodes=nodes + 1)
        return
    if isinstance(value, (list, tuple, set, frozenset)):
        if len(value) > 128:
            raise ValueError("trigger condition has too many nested values")
        for item in value:
            _reject_payload(item, depth=depth + 1, nodes=nodes + 1)
        return
    if value is not None and not isinstance(value, (bool, int, float)):
        raise ValueError("trigger condition contains an unsupported value")


class SweepAuthorityState(BaseModel):
    """Backend-owned activation and kill-switch state.

    A client or candidate cannot set either field.  Both must be true to write;
    the separate kill switch is intentionally checked on every invocation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    kill_switch_active: bool = False
    authority_version: str = Field(default="v1", min_length=1, max_length=32)

    @property
    def may_write(self) -> bool:
        return self.enabled and not self.kill_switch_active


class DailySweepCohortAuthority(BaseModel):
    """Read-only per-user rollout seam (for example a PostHog flag read).

    The sweep never writes PostHog.  A deployment may inject a resolver that
    reads the cohort assignment; when the seam is enabled without a resolver,
    the scheduler fails closed for every user.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    cohort_name: str = ""


def daily_memory_sweep_cohort_authority_from_environment() -> DailySweepCohortAuthority:
    truthy = {"1", "true", "yes", "on"}
    return DailySweepCohortAuthority(
        enabled=os.getenv(DAILY_MEMORY_SWEEP_COHORT_ENABLED_ENV, "false").casefold() in truthy,
        # The old cohort name binding remains a compatibility alias.  New
        # deployments should name the PostHog feature flag explicitly.
        cohort_name=(
            os.getenv(DAILY_MEMORY_SWEEP_COHORT_FLAG_ENV) or os.getenv(DAILY_MEMORY_SWEEP_COHORT_NAME_ENV, "")
        ).strip(),
    )


def read_daily_memory_sweep_cohort_assignment(
    uid: str,
    cohort_name: str,
    *,
    resolver: Optional[Any] = None,
) -> bool:
    """Read-only per-user cohort seam used by the maintenance entrypoint.

    The default is deliberately fail-closed.  A deployment may inject a
    read-only PostHog resolver at this function boundary; this code never
    creates flags, identifies users, or mutates PostHog state.
    """

    normalized_uid = (uid or "").strip()
    normalized_flag = (cohort_name or "").strip()
    if not normalized_uid or not normalized_flag:
        return False
    # Tests and the maintenance adaptor inject a read-only resolver.  The
    # production fallback is lazy so importing this module never constructs a
    # client or performs network I/O.  No identify/capture call is made and
    # the user id comes only from the server-side inventory.
    reader = resolver
    if reader is None:
        api_key = (os.getenv("POSTHOG_PROJECT_API_KEY") or os.getenv("POSTHOG_API_KEY") or "").strip()
        host = (os.getenv("POSTHOG_HOST") or "https://app.posthog.com").strip()
        if not api_key or not host:
            return False
        try:
            posthog_module = importlib.import_module("posthog")
            client_type = getattr(posthog_module, "Posthog")
            timeout = float(os.getenv(DAILY_MEMORY_SWEEP_COHORT_TIMEOUT_ENV, "3"))
            if timeout <= 0 or timeout > 10:
                return False
            reader = client_type(
                project_api_key=api_key,
                host=host,
                feature_flags_request_timeout_seconds=timeout,
            )
        except Exception:
            return False
    try:
        get_flag = getattr(reader, "get_feature_flag", None)
        if callable(get_flag):
            result = get_flag(
                normalized_flag,
                normalized_uid,
                only_evaluate_locally=False,
                send_feature_flag_events=False,
            )
        elif callable(reader):
            result = reader(normalized_uid, normalized_flag)
        else:
            return False
    except Exception:
        return False
    # A boolean true is the only accepted assignment.  String variants are
    # deliberately not treated as enrollment: a flag configured with a named
    # variant must use a server-side boolean rollout or stay closed.
    return result is True


class DailySweepModelAuthority(BaseModel):
    """Explicit authority for the bounded completed-day candidate producer.

    ``model_name`` is checked against the configured ``memories`` route before
    the built-in extractor is called.  The optional extractor injection is for
    deterministic emulator/unit tests; production uses the same existing
    memory model route and never accepts a client-selected model.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    model_name: str = "disabled"
    max_candidates: int = Field(default=8, ge=0, le=MAX_CANDIDATES_PER_DAY)
    max_cost_usd: float = Field(default=0.0, ge=0.0, le=10.0)

    @property
    def route_is_budgeted(self) -> bool:
        return self.enabled and self.model_name not in {"", "disabled"} and self.max_cost_usd > 0


def daily_memory_sweep_model_authority_from_environment() -> DailySweepModelAuthority:
    truthy = {"1", "true", "yes", "on"}
    raw_candidates = os.getenv(DAILY_MEMORY_SWEEP_MAX_MODEL_CANDIDATES_ENV, "8")
    raw_cost = os.getenv(DAILY_MEMORY_SWEEP_MAX_MODEL_COST_USD_ENV, "0")
    try:
        max_candidates = int(raw_candidates)
        max_cost = float(raw_cost)
    except ValueError as exc:
        raise ValueError("daily sweep model budget environment is malformed") from exc
    return DailySweepModelAuthority(
        enabled=os.getenv(DAILY_MEMORY_SWEEP_MODEL_ENABLED_ENV, "false").casefold() in truthy,
        model_name=os.getenv(DAILY_MEMORY_SWEEP_MODEL_NAME_ENV, "disabled").strip() or "disabled",
        max_candidates=max_candidates,
        max_cost_usd=max_cost,
    )


class SweepFenceBlocked(RuntimeError):
    """A durable deletion or generation fence closed during a transaction."""


class SweepAuthoritativeQueryUnavailable(RuntimeError):
    """A bounded canonical query could not prove the occupant set."""


class SweepAuthority(str, Enum):
    direct_user_statement = "direct_user_statement"
    agent_reusable_conclusion = "agent_reusable_conclusion"
    sweep_inference = "sweep_inference"

    @property
    def rank(self) -> int:
        return {
            SweepAuthority.sweep_inference: 1,
            SweepAuthority.agent_reusable_conclusion: 2,
            SweepAuthority.direct_user_statement: 3,
        }[self]

    @property
    def ledger_reason(self) -> LedgerWriteReason:
        return {
            SweepAuthority.direct_user_statement: LedgerWriteReason.direct_user_statement,
            SweepAuthority.agent_reusable_conclusion: LedgerWriteReason.agent_reusable_conclusion,
            SweepAuthority.sweep_inference: LedgerWriteReason.daily_reconciliation,
        }[self]


class DailySweepCandidate(BaseModel):
    """One server-built, bounded candidate from a completed local day."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str
    kind: Literal["fact", "trigger"]
    operation: Literal["add", "amend", "repair"] = "add"
    content: str
    source_id: str
    source_type: str
    source_version: str = "v1"
    source_refs: Tuple[str, ...] = ()
    authority: SweepAuthority = SweepAuthority.sweep_inference
    target_memory_id: Optional[str] = None
    slot: Optional[str] = None
    subject_scope: MemorySubjectScope = MemorySubjectScope.primary_user
    subject_entity_id: Optional[str] = None
    trigger_condition: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("candidate_id", "target_memory_id", "subject_entity_id")
    @classmethod
    def validate_ids(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized or not _ID_RE.fullmatch(normalized.casefold()):
            raise ValueError("candidate identifiers must be bounded canonical ids")
        return normalized

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        normalized = " ".join((value or "").split())
        if not normalized:
            raise ValueError("candidate content is required")
        if len(normalized) > MAX_CONTENT_CHARACTERS:
            raise ValueError("candidate content exceeds the daily sweep budget")
        if any(marker in normalized.casefold() for marker in _FORBIDDEN_SOURCE_MARKERS):
            raise ValueError("raw image/pixel payloads are not valid sweep content")
        return normalized

    @field_validator("source_id", "source_type", "source_version")
    @classmethod
    def validate_source_identity(cls, value: str, info) -> str:
        normalized = (value or "").strip()
        limit = MAX_SOURCE_ID_CHARACTERS if info.field_name == "source_id" else 64
        if not normalized or len(normalized) > limit:
            raise ValueError("source identity is missing or oversized")
        lowered = normalized.casefold()
        if any(marker in lowered for marker in _FORBIDDEN_SOURCE_MARKERS):
            raise ValueError("raw image/pixel payloads are not valid sweep sources")
        if info.field_name == "source_type" and normalized not in _ALLOWED_SOURCE_TYPES:
            raise ValueError("unsupported sweep source type")
        return normalized

    @field_validator("source_refs")
    @classmethod
    def validate_source_refs(cls, value: Tuple[str, ...]) -> Tuple[str, ...]:
        normalized = tuple(sorted({ref.strip() for ref in value if ref and ref.strip()}))
        if len(normalized) > MAX_SOURCE_REFS:
            raise ValueError("source_refs exceed the daily sweep budget")
        for ref in normalized:
            lowered = ref.casefold()
            if len(ref) > MAX_SOURCE_REF_CHARACTERS or any(marker in lowered for marker in _FORBIDDEN_SOURCE_MARKERS):
                raise ValueError("source_refs must be bounded metadata-only references")
        return normalized

    @field_validator("slot")
    @classmethod
    def validate_slot(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = "_".join(value.strip().lower().replace("-", "_").split())
        if not normalized or len(normalized) > 64:
            raise ValueError("slot must be a bounded non-empty name")
        return normalized

    @field_validator("trigger_condition")
    @classmethod
    def validate_trigger_condition(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        _reject_payload(value)
        if len(value) > MAX_TRIGGER_CONDITION_KEYS:
            raise ValueError("trigger condition exceeds the daily sweep budget")
        return value

    @model_validator(mode="after")
    def validate_semantics(self) -> "DailySweepCandidate":
        if self.subject_scope == MemorySubjectScope.third_party and not self.subject_entity_id:
            raise ValueError("third-party sweep facts require subject_entity_id")
        if self.kind == "fact" and self.trigger_condition:
            raise ValueError("fact candidates cannot carry trigger conditions")
        if self.kind == "trigger" and self.operation != "repair":
            raise ValueError("the daily sweep may repair existing triggers but never invent them")
        if self.operation in {"amend", "repair"} and not self.target_memory_id:
            raise ValueError("amend/repair candidates require target_memory_id")
        if self.authority == SweepAuthority.direct_user_statement and self.source_type not in {
            "explicit_user_statement",
            "onboarding",
        }:
            raise ValueError("direct authority requires an explicit-user-statement or onboarding source")
        if self.kind == "trigger":
            # Compile at the boundary, then persist the normalized strict schema
            # so a future evaluator never receives an unvalidated ad-hoc map.
            object.__setattr__(
                self, "trigger_condition", compile_trigger_condition(self.trigger_condition).as_condition()
            )
        return self

    @property
    def source_key(self) -> str:
        return f"{self.source_type}:{self.source_id}:{self.candidate_id}"

    def digest(self) -> str:
        return deterministic_contract_id("daily-memory-sweep-candidate", self.model_dump(mode="json"))


class DailySweepInput(BaseModel):
    """Immutable input packet for one completed user-local date."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    uid: str
    local_date: date
    account_generation: int
    source_generation: int
    # Sweep-owned receipt namespace.  ``source_generation`` remains the live
    # canonical fence; this generation must not be advanced by a timezone
    # preference change in the global canonical control document.
    sweep_generation: int = 1
    timezone_name: str
    window_id: str
    window_start_utc: datetime
    window_end_utc: datetime
    complete: bool
    candidates: Tuple[DailySweepCandidate, ...] = ()
    # The producer attests the onboarding sources represented by this packet,
    # including sources that yielded zero candidates.  Consumption is done
    # after all candidate receipts commit, never once per candidate.
    onboarding_source_keys: Tuple[str, ...] = ()
    onboarding_source_progress: Dict[str, int] = Field(default_factory=dict)
    eligibility_proof: Literal["completed_transcript_v1", "none"] = "none"

    @field_validator("uid")
    @classmethod
    def validate_uid(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("uid is required")
        return normalized

    @field_validator("account_generation", "source_generation", "sweep_generation")
    @classmethod
    def validate_generations(cls, value: int) -> int:
        if value < 0:
            raise ValueError("generation must be nonnegative")
        return value

    @field_validator("window_start_utc", "window_end_utc")
    @classmethod
    def validate_window_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("input window timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @field_validator("candidates")
    @classmethod
    def validate_candidate_count(cls, value: Tuple[DailySweepCandidate, ...]) -> Tuple[DailySweepCandidate, ...]:
        if len(value) > MAX_CANDIDATES_PER_DAY:
            raise ValueError("daily sweep candidate window exceeded")
        return value

    @field_validator("onboarding_source_keys")
    @classmethod
    def validate_onboarding_source_keys(cls, value: Tuple[str, ...]) -> Tuple[str, ...]:
        normalized = tuple(sorted({item.strip() for item in value if item.strip()}))
        if len(normalized) > MAX_CANDIDATES_PER_DAY:
            raise ValueError("daily sweep onboarding source budget exceeded")
        if any(not item.startswith("onboarding:") or len(item) > MAX_SOURCE_ID_CHARACTERS for item in normalized):
            raise ValueError("invalid onboarding source key")
        return normalized

    @field_validator("onboarding_source_progress")
    @classmethod
    def validate_onboarding_source_progress(cls, value: Dict[str, int]) -> Dict[str, int]:
        normalized = {str(key).strip(): int(offset) for key, offset in value.items()}
        if len(normalized) > MAX_CANDIDATES_PER_DAY or any(
            not key.startswith("onboarding:") or offset < 0 for key, offset in normalized.items()
        ):
            raise ValueError("invalid onboarding source progress")
        return normalized

    @model_validator(mode="after")
    def validate_schema(self) -> "DailySweepInput":
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported daily sweep input schema")
        try:
            ZoneInfo(self.timezone_name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("input timezone must be an installed IANA timezone") from exc
        expected = completed_local_day_window(self.local_date, self.timezone_name)
        if (
            not self.complete
            or self.window_id != expected.window_id
            or self.window_start_utc != expected.start_utc
            or self.window_end_utc != expected.end_utc
        ):
            raise ValueError("input must be an immutable complete exact local-day packet")
        return self


class DailySweepSkip(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str
    reason: Literal[
        "duplicate_candidate",
        "lower_authority",
        "missing_target",
        "target_not_active",
        "target_kind_mismatch",
        "target_not_explicit_trigger",
        "source_key_conflict",
        "invalid_candidate",
        "existing_active_slot",
        "existing_active_subject",
    ]


class DailySweepPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    uid: str
    local_date: date
    idempotency_key: str
    candidates: Tuple[DailySweepCandidate, ...] = ()
    skipped: Tuple[DailySweepSkip, ...] = ()


class DailySweepCursor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = CURSOR_SCHEMA_VERSION
    uid: str
    account_generation: int
    source_generation: int
    sweep_generation: int = 1
    generation: int = 0
    timezone_name: Optional[str] = None
    last_completed_local_date: Optional[date] = None
    last_completed_window_id: Optional[str] = None
    last_completed_window_start_utc: Optional[datetime] = None
    last_completed_window_end_utc: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("updated_at", "last_completed_window_start_utc", "last_completed_window_end_utc")
    @classmethod
    def validate_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("cursor timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)

    @field_validator("timezone_name")
    @classmethod
    def validate_timezone_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("cursor timezone must be an installed IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def validate_window_identity(self) -> "DailySweepCursor":
        if self.last_completed_local_date is None:
            if any(
                (
                    self.last_completed_window_id,
                    self.last_completed_window_start_utc,
                    self.last_completed_window_end_utc,
                )
            ):
                raise ValueError("cursor window identity requires a completed local date")
        elif not (
            self.timezone_name
            and self.last_completed_window_id
            and self.last_completed_window_start_utc
            and self.last_completed_window_end_utc
        ):
            raise ValueError("completed cursor rows require an exact UTC window identity")
        return self


class DailySweepOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    uid: str
    status: Literal["disabled", "not_due", "blocked", "committed"]
    completed_local_dates: Tuple[date, ...] = ()
    committed_count: int = 0
    idempotent_count: int = 0
    skipped_count: int = 0
    blocked_reason: Optional[str] = None
    telemetry: Dict[str, int | str] = Field(default_factory=dict)


@dataclass(frozen=True)
class CompletedLocalDayWindow:
    start_utc: datetime
    end_utc: datetime
    window_id: str


def completed_local_day_window(local_date: date, timezone_name: str) -> CompletedLocalDayWindow:
    """Return the exact UTC half-open window for one local calendar day.

    ZoneInfo conversion intentionally preserves 23-hour spring-forward and
    25-hour fall-back days.  A timezone change while a cursor is non-empty is
    fail-closed by the runner: an operator must reconcile/reset the cursor, so
    overlap is never double-processed and a gap is never silently skipped.
    """

    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("timezone_name must be a valid IANA timezone") from exc
    start = datetime.combine(local_date, time.min, tzinfo=zone).astimezone(timezone.utc)
    end = datetime.combine(local_date + timedelta(days=1), time.min, tzinfo=zone).astimezone(timezone.utc)
    if end <= start:
        raise ValueError("local-day window must advance in UTC")
    window_id = deterministic_contract_id(
        "daily-memory-sweep-window",
        {
            "local_date": local_date.isoformat(),
            "timezone": timezone_name,
            "start_utc": start.isoformat(),
            "end_utc": end.isoformat(),
        },
    )
    return CompletedLocalDayWindow(start_utc=start, end_utc=end, window_id=window_id)


def _plan_id(uid: str, local_date: date) -> str:
    return "daily-memory-sweep:" + deterministic_contract_id(
        "daily-memory-sweep", {"uid": uid, "local_date": local_date.isoformat()}
    )


def _semantic_key(candidate: DailySweepCandidate) -> Tuple[str, str, str, str]:
    return (
        candidate.kind,
        candidate.subject_scope.value,
        candidate.subject_entity_id or "",
        candidate.target_memory_id or candidate.slot or candidate.content.casefold(),
    )


def plan_daily_memory_sweep(packet: DailySweepInput) -> DailySweepPlan:
    """Deterministically deduplicate candidates and apply authority ordering."""

    uid = packet.uid.strip()
    if not uid:
        raise ValueError("uid is required")
    by_source: Dict[str, DailySweepCandidate] = {}
    skipped: List[DailySweepSkip] = []
    # Sort before reducing so equal-authority input order cannot change the
    # selected winner (including malformed producer retries with one source key).
    for candidate in sorted(packet.candidates, key=lambda item: (item.source_key, item.digest())):
        key = candidate.source_key
        if key in by_source:
            prior = by_source[key]
            if candidate.digest() == prior.digest():
                skipped.append(DailySweepSkip(candidate_id=candidate.candidate_id, reason="duplicate_candidate"))
            elif candidate.digest() > prior.digest():
                by_source[key] = candidate
                skipped.append(DailySweepSkip(candidate_id=prior.candidate_id, reason="source_key_conflict"))
            else:
                skipped.append(DailySweepSkip(candidate_id=candidate.candidate_id, reason="source_key_conflict"))
            continue
        by_source[key] = candidate

    selected: Dict[Tuple[str, str, str, str], DailySweepCandidate] = {}
    for candidate in sorted(by_source.values(), key=lambda item: (item.source_key, item.digest())):
        semantic = _semantic_key(candidate)
        prior = selected.get(semantic)
        if prior is None:
            selected[semantic] = candidate
            continue
        candidate_order = (candidate.authority.rank, candidate.digest(), candidate.source_key)
        prior_order = (prior.authority.rank, prior.digest(), prior.source_key)
        if candidate_order > prior_order:
            skipped.append(DailySweepSkip(candidate_id=prior.candidate_id, reason="lower_authority"))
            selected[semantic] = candidate
        else:
            skipped.append(DailySweepSkip(candidate_id=candidate.candidate_id, reason="lower_authority"))

    candidates = tuple(sorted(selected.values(), key=lambda item: (item.kind, item.source_key)))
    skipped.sort(key=lambda item: (item.reason, item.candidate_id))
    return DailySweepPlan(
        uid=uid,
        local_date=packet.local_date,
        idempotency_key=_plan_id(uid, packet.local_date),
        candidates=candidates,
        skipped=tuple(skipped),
    )


def _cursor_ref(db_client: Any, uid: str) -> Any:
    return db_client.document(f"{MemoryCollections(uid=uid).user_root}/memory_control/daily_memory_sweep")


def _receipt_ref(db_client: Any, uid: str, receipt_id: str) -> Any:
    return db_client.document(f"{MemoryCollections(uid=uid).daily_memory_sweep_receipts}/{receipt_id}")


def _onboarding_source_receipt_ref(
    db_client: Any,
    uid: str,
    local_date: date,
    source_key: str,
    *,
    account_generation: int,
    source_generation: int,
    sweep_generation: int = 1,
) -> Any:
    source_receipt_id = (
        "source_"
        + deterministic_contract_id(
            "daily-memory-sweep-onboarding-source-receipt",
            {
                "uid": uid,
                "local_date": local_date.isoformat(),
                "source_key": source_key,
                "account_generation": account_generation,
                "source_generation": source_generation,
                "sweep_generation": sweep_generation,
            },
        )[:40]
    )
    return _receipt_ref(db_client, uid, source_receipt_id)


def _receipt_id(
    uid: str,
    local_date: date,
    candidate: DailySweepCandidate,
    *,
    account_generation: int,
    source_generation: int,
    sweep_generation: int = 1,
) -> str:
    return (
        "receipt_"
        + deterministic_contract_id(
            "daily-memory-sweep-receipt",
            {
                "uid": uid,
                "local_date": local_date.isoformat(),
                "source_key": candidate.source_key,
                "account_generation": account_generation,
                "source_generation": source_generation,
                "sweep_generation": sweep_generation,
            },
        )[:40]
    )


def _read_cursor(db_client: Any, uid: str, control: MemoryControlState) -> DailySweepCursor:
    snapshot = _cursor_ref(db_client, uid).get()
    if not getattr(snapshot, "exists", False):
        return DailySweepCursor(
            uid=uid,
            account_generation=control.account_generation,
            source_generation=control.source_generation,
        )
    try:
        cursor = DailySweepCursor.model_validate(snapshot.to_dict() or {})
    except Exception as exc:
        raise RuntimeError("daily sweep cursor is malformed") from exc
    if cursor.uid != uid or cursor.account_generation != control.account_generation:
        raise RuntimeError("daily sweep cursor owner or generation mismatch")
    if cursor.source_generation != control.source_generation:
        if cursor.source_generation > control.source_generation:
            raise RuntimeError("daily sweep cursor source generation is ahead of canonical control")
        if not _rollover_cursor_source_generation(
            db_client,
            uid,
            cursor,
            control,
        ):
            raise RuntimeError("daily sweep cursor source-generation rollover conflict")
        snapshot = _cursor_ref(db_client, uid).get()
        try:
            cursor = DailySweepCursor.model_validate(snapshot.to_dict() or {})
        except Exception as exc:
            raise RuntimeError("daily sweep cursor is malformed after source-generation rollover") from exc
        if cursor.source_generation != control.source_generation:
            raise RuntimeError("daily sweep cursor source-generation rollover did not commit")
    return cursor


def _rollover_cursor_source_generation(
    db_client: Any,
    uid: str,
    prior: DailySweepCursor,
    control: MemoryControlState,
) -> bool:
    """CAS source generation while preserving the exact completed-day identity.

    A source refresh must not replay a completed local day or silently skip a
    pending one. Receipts are generation-namespaced, so stale packets/receipts
    cannot be reused after this transaction.
    """

    ref = _cursor_ref(db_client, uid)

    def rollover(transaction: Any) -> bool:
        deletion_ref, control_ref = _live_fence_refs(db_client, uid)
        if not _transaction_fence_open(
            transaction,
            deletion_ref,
            control_ref,
            uid=uid,
            account_generation=control.account_generation,
            source_generation=control.source_generation,
        ):
            return False
        snapshot = ref.get(transaction=transaction)
        if not getattr(snapshot, "exists", False):
            return prior.source_generation == control.source_generation
        payload = snapshot.to_dict() or {}
        if (
            payload.get("uid") != uid
            or int(payload.get("account_generation", -1)) != control.account_generation
            or int(payload.get("source_generation", -1)) != prior.source_generation
            or int(payload.get("generation", -1)) != prior.generation
        ):
            return False
        transaction.set(
            ref,
            {
                **payload,
                "source_generation": control.source_generation,
                "generation": prior.generation + 1,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        return True

    transaction = db_client.transaction()
    return bool(firestore.transactional(rollover)(transaction))


def reconcile_daily_memory_sweep_timezone(
    uid: str,
    timezone_name: str,
    *,
    db_client: Any,
    reconciliation_authorized: bool = False,
) -> bool:
    """Explicitly re-anchor a cursor after a user timezone change.

    A timezone change can create a 23/25-hour overlap or gap.  The scheduler
    therefore blocks automatically; this separate server-only operation rolls
    the sweep-owned receipt namespace while preserving the completed-day
    anchor.  The global canonical source generation is never mutated here.
    """

    if not reconciliation_authorized:
        return False
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("timezone_name must be a valid IANA timezone") from exc
    # Ensure the control document exists before entering the transaction; the
    # transaction below still re-reads the live value and fences the cursor
    # namespace atomically.
    ensure_canonical_apply_control_state(uid, db_client=db_client)
    ref = _cursor_ref(db_client, uid)

    def reconcile(transaction: Any) -> bool:
        deletion_ref, control_ref = _live_fence_refs(db_client, uid)
        deletion_snapshot = deletion_ref.get(transaction=transaction)
        deletion_payload = deletion_snapshot.to_dict() if getattr(deletion_snapshot, "exists", False) else {}
        if account_deletion_blocks_access(
            normalize_account_deletion_status(
                marker_exists=bool(getattr(deletion_snapshot, "exists", False)),
                raw_status=deletion_payload.get("wipe_status") if isinstance(deletion_payload, dict) else None,
            )
        ):
            return False
        control_snapshot = control_ref.get(transaction=transaction)
        if not getattr(control_snapshot, "exists", False):
            return False
        control_payload = control_snapshot.to_dict() or {}
        try:
            live_control = MemoryControlState.model_validate(control_payload)
        except Exception:
            return False
        if live_control.uid != uid:
            return False
        snapshot = ref.get(transaction=transaction)
        if not getattr(snapshot, "exists", False):
            transaction.set(
                ref,
                DailySweepCursor(
                    uid=uid,
                    account_generation=live_control.account_generation,
                    source_generation=live_control.source_generation,
                    sweep_generation=1,
                    timezone_name=timezone_name,
                ).model_dump(mode="json"),
            )
            return True
        try:
            cursor = DailySweepCursor.model_validate(snapshot.to_dict() or {})
        except Exception:
            return False
        if (
            cursor.uid != uid
            or cursor.account_generation != live_control.account_generation
            or cursor.source_generation != live_control.source_generation
        ):
            return False
        if cursor.timezone_name == timezone_name:
            return True
        # Receipt IDs include the sweep-owned generation.  Roll that namespace
        # in the same transaction as the timezone anchor so an overlapping
        # local date cannot collide with the old completed receipt set.
        now = datetime.now(timezone.utc)
        transaction.set(
            ref,
            {
                "schema_version": CURSOR_SCHEMA_VERSION,
                "uid": uid,
                "account_generation": live_control.account_generation,
                "source_generation": live_control.source_generation,
                "sweep_generation": cursor.sweep_generation + 1,
                "generation": cursor.generation + 1,
                "timezone_name": timezone_name,
                "last_completed_local_date": cursor.last_completed_local_date,
                "last_completed_window_id": cursor.last_completed_window_id,
                "last_completed_window_start_utc": cursor.last_completed_window_start_utc,
                "last_completed_window_end_utc": cursor.last_completed_window_end_utc,
                "updated_at": now,
            },
        )
        return True

    return bool(firestore.transactional(reconcile)(db_client.transaction()))


def reconcile_daily_memory_sweep_timezones_for_maintenance(
    uid_inventory: Iterable[str],
    *,
    timezone_resolver: Any,
    db_client: Any,
    authorized: bool = False,
    max_users: int = 400,
) -> Tuple[str, ...]:
    """Bounded operator/runtime entrypoint for explicit timezone reconciliation."""

    if not authorized:
        return ()
    reconciled: List[str] = []
    for uid in tuple(sorted({str(item).strip() for item in uid_inventory if str(item).strip()}))[:max_users]:
        try:
            timezone_name = str(timezone_resolver(uid) or "UTC")
            if reconcile_daily_memory_sweep_timezone(
                uid,
                timezone_name,
                db_client=db_client,
                reconciliation_authorized=True,
            ):
                reconciled.append(uid)
        except Exception:
            # A malformed profile or a contention failure must not turn this
            # bounded auxiliary pass into a cursor-advancing fallback.
            continue
    return tuple(reconciled)


def _pending_receipt_dates(
    db_client: Any,
    uid: str,
    *,
    through: date,
    account_generation: int,
    source_generation: int,
    sweep_generation: int = 1,
) -> Tuple[date, ...]:
    """Recover bounded incomplete dates when a crash occurred before cursor CAS."""

    try:
        snapshots = list(
            db_client.collection(MemoryCollections(uid=uid).daily_memory_sweep_receipts)
            .where(filter=FieldFilter("receipt_state", "==", "pending"))
            .limit(MAX_CANDIDATES_PER_DAY * MAX_CATCH_UP_DAYS)
            .stream()
        )
    except Exception:
        # A missing index/query support is not evidence that there are no
        # pending dates. The regular cursor path remains safe and the caller
        # will block on missing input rather than advance.
        return ()
    dates: set[date] = set()
    for snapshot in snapshots:
        payload = snapshot.to_dict() or {}
        if (
            not isinstance(payload, dict)
            or int(payload.get("account_generation", -1)) != account_generation
            or int(payload.get("source_generation", -1)) != source_generation
            or int(payload.get("sweep_generation", 1)) != sweep_generation
        ):
            continue
        raw = payload.get("local_date")
        try:
            local_date = date.fromisoformat(str(raw))
        except (TypeError, ValueError):
            continue
        if local_date <= through:
            dates.add(local_date)
    return tuple(sorted(dates))


def _live_fence_refs(db_client: Any, uid: str) -> Tuple[Any, Any]:
    return (
        db_client.document(f"account_deletions/{uid}"),
        db_client.document(MemoryCollections(uid=uid).memory_apply_control_state),
    )


def _transaction_fence_open(
    transaction: Any,
    deletion_ref: Any,
    control_ref: Any,
    *,
    uid: str,
    account_generation: int,
    source_generation: int,
) -> bool:
    """Read deletion and live control state in the same transaction as writes."""

    deletion_snapshot = deletion_ref.get(transaction=transaction)
    deletion_payload = deletion_snapshot.to_dict() if getattr(deletion_snapshot, "exists", False) else {}
    deletion_status = normalize_account_deletion_status(
        marker_exists=bool(getattr(deletion_snapshot, "exists", False)),
        raw_status=deletion_payload.get("wipe_status") if isinstance(deletion_payload, dict) else None,
    )
    if account_deletion_blocks_access(deletion_status):
        return False
    control_snapshot = control_ref.get(transaction=transaction)
    if not getattr(control_snapshot, "exists", False):
        return False
    control_payload = control_snapshot.to_dict() or {}
    return (
        isinstance(control_payload, dict)
        and control_payload.get("uid") == uid
        and int(control_payload.get("account_generation", -1)) == account_generation
        and int(control_payload.get("source_generation", -1)) == source_generation
    )


def _advance_cursor_txn(
    transaction: Any,
    ref: Any,
    uid: str,
    account_generation: int,
    source_generation: int,
    sweep_generation: int,
    expected_generation: int,
    local_date: date,
    timezone_name: str,
    window_start_utc: datetime,
    window_end_utc: datetime,
    window_id: str,
    deletion_ref: Any,
    control_ref: Any,
    now: datetime,
) -> bool:
    if not _transaction_fence_open(
        transaction,
        deletion_ref,
        control_ref,
        uid=uid,
        account_generation=account_generation,
        source_generation=source_generation,
    ):
        return False
    snapshot = ref.get(transaction=transaction)
    payload = snapshot.to_dict() if getattr(snapshot, "exists", False) else {}
    if payload:
        if (
            payload.get("uid") != uid
            or int(payload.get("account_generation", -1)) != account_generation
            or int(payload.get("source_generation", -1)) != source_generation
        ):
            return False
        if int(payload.get("sweep_generation", 1)) != sweep_generation:
            return False
        if int(payload.get("generation", -1)) != expected_generation:
            return False
        if payload.get("timezone_name") not in {None, timezone_name}:
            return False
        prior = payload.get("last_completed_local_date")
        if isinstance(prior, str) and prior == local_date.isoformat():
            return payload.get("last_completed_window_id") == window_id
        if isinstance(prior, str) and prior > local_date.isoformat():
            return False
    elif expected_generation != 0:
        return False
    transaction.set(
        ref,
        {
            "schema_version": CURSOR_SCHEMA_VERSION,
            "uid": uid,
            "account_generation": account_generation,
            "source_generation": source_generation,
            "sweep_generation": sweep_generation,
            "generation": expected_generation + 1,
            "timezone_name": timezone_name,
            "last_completed_local_date": local_date.isoformat(),
            "last_completed_window_id": window_id,
            "last_completed_window_start_utc": window_start_utc,
            "last_completed_window_end_utc": window_end_utc,
            "updated_at": now,
        },
    )
    return True


def _advance_cursor(
    db_client: Any,
    uid: str,
    control: MemoryControlState,
    cursor: DailySweepCursor,
    local_date: date,
    timezone_name: str,
    window_start_utc: datetime,
    window_end_utc: datetime,
    window_id: str,
    *,
    sweep_generation: Optional[int] = None,
) -> bool:
    transaction = db_client.transaction()
    transactional = firestore.transactional(_advance_cursor_txn)
    deletion_ref, control_ref = _live_fence_refs(db_client, uid)
    return bool(
        transactional(
            transaction,
            _cursor_ref(db_client, uid),
            uid,
            control.account_generation,
            control.source_generation,
            sweep_generation if sweep_generation is not None else cursor.sweep_generation,
            cursor.generation,
            local_date,
            timezone_name,
            window_start_utc,
            window_end_utc,
            window_id,
            deletion_ref,
            control_ref,
            datetime.now(timezone.utc),
        )
    )


def _claim_receipt(
    db_client: Any,
    uid: str,
    local_date: date,
    candidate: DailySweepCandidate,
    *,
    account_generation: int,
    source_generation: int,
    claimant: str,
    claim_now: datetime,
    window: CompletedLocalDayWindow,
    sweep_generation: int = 1,
) -> Literal["claimed", "idempotent", "conflict"]:
    receipt_ref = _receipt_ref(
        db_client,
        uid,
        _receipt_id(
            uid,
            local_date,
            candidate,
            account_generation=account_generation,
            source_generation=source_generation,
            sweep_generation=sweep_generation,
        ),
    )
    digest = candidate.digest()
    normalized_now = claim_now.astimezone(timezone.utc)

    def claim(transaction: Any) -> Literal["claimed", "idempotent", "conflict"]:
        deletion_ref, control_ref = _live_fence_refs(db_client, uid)
        if not _transaction_fence_open(
            transaction,
            deletion_ref,
            control_ref,
            uid=uid,
            account_generation=account_generation,
            source_generation=source_generation,
        ):
            return "conflict"
        snapshot = receipt_ref.get(transaction=transaction)
        existing = snapshot.to_dict() if getattr(snapshot, "exists", False) else None
        if existing is not None:
            if (
                existing.get("uid") != uid
                or existing.get("source_key") != candidate.source_key
                or existing.get("candidate_digest") != digest
                or int(existing.get("account_generation", -1)) != account_generation
                or int(existing.get("source_generation", -1)) != source_generation
                or int(existing.get("sweep_generation", 1)) != sweep_generation
                or existing.get("local_timezone_window_id") != window.window_id
                or existing.get("window_start_utc") != window.start_utc
                or existing.get("window_end_utc") != window.end_utc
            ):
                return "conflict"
            if existing.get("receipt_state") == "committed":
                return "idempotent"
            prior_claimant = existing.get("claimant")
            if prior_claimant and prior_claimant != claimant:
                expires_raw = existing.get("claim_expires_at")
                try:
                    expires = (
                        expires_raw
                        if isinstance(expires_raw, datetime)
                        else datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
                    )
                    if (
                        expires.tzinfo is None
                        or expires.utcoffset() is None
                        or expires.astimezone(timezone.utc) > normalized_now
                    ):
                        return "conflict"
                except (TypeError, ValueError):
                    # An old or malformed pending claim is never guessed at or
                    # overwritten. The next retry must use an explicit repair.
                    return "conflict"
            transaction.set(
                receipt_ref,
                {
                    "claimant": claimant,
                    "claimed_at": normalized_now,
                    "claim_expires_at": normalized_now + RECEIPT_LEASE,
                },
                merge=True,
            )
            return "claimed"
        transaction.set(
            receipt_ref,
            {
                "schema_version": RECEIPT_SCHEMA_VERSION,
                "uid": uid,
                "local_date": local_date.isoformat(),
                "source_key": candidate.source_key,
                "candidate_digest": digest,
                "account_generation": account_generation,
                "source_generation": source_generation,
                "sweep_generation": sweep_generation,
                "claimant": claimant,
                "receipt_state": "pending",
                "local_timezone_window_id": window.window_id,
                "window_start_utc": window.start_utc,
                "window_end_utc": window.end_utc,
                "claimed_at": normalized_now,
                "claim_expires_at": normalized_now + RECEIPT_LEASE,
            },
        )
        return "claimed"

    transaction = db_client.transaction()
    transactional = firestore.transactional(claim)
    return transactional(transaction)


def _finish_receipt(
    db_client: Any,
    uid: str,
    local_date: date,
    candidate: DailySweepCandidate,
    *,
    memory_id: Optional[str],
    outcome: Literal["committed", "skipped"] = "committed",
    skip_reason: Optional[str] = None,
    account_generation: int,
    source_generation: int,
    claimant: str,
    window: CompletedLocalDayWindow,
    sweep_generation: int = 1,
) -> None:
    receipt_ref = _receipt_ref(
        db_client,
        uid,
        _receipt_id(
            uid,
            local_date,
            candidate,
            account_generation=account_generation,
            source_generation=source_generation,
            sweep_generation=sweep_generation,
        ),
    )

    def finish(transaction: Any) -> None:
        deletion_ref, control_ref = _live_fence_refs(db_client, uid)
        if not _transaction_fence_open(
            transaction,
            deletion_ref,
            control_ref,
            uid=uid,
            account_generation=account_generation,
            source_generation=source_generation,
        ):
            raise SweepFenceBlocked("daily sweep receipt completion fence closed")
        snapshot = receipt_ref.get(transaction=transaction)
        if not getattr(snapshot, "exists", False):
            raise RuntimeError("daily sweep receipt disappeared before completion")
        existing = snapshot.to_dict() or {}
        if (
            existing.get("uid") != uid
            or existing.get("source_key") != candidate.source_key
            or existing.get("candidate_digest") != candidate.digest()
            or int(existing.get("account_generation", -1)) != account_generation
            or int(existing.get("source_generation", -1)) != source_generation
            or int(existing.get("sweep_generation", 1)) != sweep_generation
            or existing.get("claimant") != claimant
            or existing.get("local_timezone_window_id") != window.window_id
            or existing.get("window_start_utc") != window.start_utc
            or existing.get("window_end_utc") != window.end_utc
        ):
            raise RuntimeError("daily sweep receipt changed while completing")
        payload: Dict[str, Any] = {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "receipt_state": "committed",
            "source_generation": source_generation,
            "sweep_generation": sweep_generation,
            "claimant": claimant,
            "outcome": outcome,
            "local_timezone_window_id": window.window_id,
            "window_start_utc": window.start_utc,
            "window_end_utc": window.end_utc,
            "completed_at": datetime.now(timezone.utc),
        }
        if memory_id:
            payload["memory_id"] = memory_id
        if skip_reason:
            payload["skip_reason"] = skip_reason
        transaction.set(receipt_ref, payload, merge=True)

    transaction = db_client.transaction()
    firestore.transactional(finish)(transaction)


def _finish_onboarding_sources(
    db_client: Any,
    uid: str,
    local_date: date,
    source_keys: Iterable[str],
    candidates: Iterable[DailySweepCandidate],
    *,
    account_generation: int,
    source_generation: int,
    window: CompletedLocalDayWindow,
    source_progress: Optional[Mapping[str, int]] = None,
    sweep_generation: int = 1,
) -> bool:
    """Atomically consume onboarding sources after every candidate is safe.

    A source receipt is separate from candidate receipts.  If the process dies
    after one canonical write, the source remains retryable; the next attempt
    sees the committed candidate receipt and finishes the remaining candidates
    before writing the source marker.  Empty model output still has a source
    receipt and is therefore not re-run forever.
    """

    normalized_keys = tuple(sorted(set(source_keys)))
    if not normalized_keys:
        return True
    candidates_by_source: Dict[str, List[DailySweepCandidate]] = {key: [] for key in normalized_keys}
    for candidate in candidates:
        source_key = f"onboarding:{candidate.source_id.split(':', 1)[-1]}"
        if source_key in candidates_by_source:
            candidates_by_source[source_key].append(candidate)
    consumed_ref = db_client.document(f"users/{uid}/{ONBOARDING_CONSUMED_STATE_PATH}")

    def complete(transaction: Any) -> bool:
        deletion_ref, control_ref = _live_fence_refs(db_client, uid)
        if not _transaction_fence_open(
            transaction,
            deletion_ref,
            control_ref,
            uid=uid,
            account_generation=account_generation,
            source_generation=source_generation,
        ):
            return False
        consumed_snapshot = transaction.get(consumed_ref)
        consumed_payload = consumed_snapshot.to_dict() if getattr(consumed_snapshot, "exists", False) else {}
        raw_consumed = consumed_payload.get("consumed_source_keys", []) if isinstance(consumed_payload, dict) else []
        consumed_values = list(raw_consumed) if isinstance(raw_consumed, list) else []
        raw_offsets = consumed_payload.get("candidate_offsets", {}) if isinstance(consumed_payload, dict) else {}
        offsets = {
            key: int(value)
            for key, value in raw_offsets.items()
            if isinstance(key, str) and isinstance(value, int) and value >= 0
        }
        source_receipts: List[Tuple[Any, str]] = []
        candidate_receipts: List[Any] = []
        # Firestore requires all reads before writes.  Candidate receipts are
        # proof that canonical application completed for this whole source.
        for source_key in normalized_keys:
            if source_key not in (source_progress or {}):
                source_ref = _onboarding_source_receipt_ref(
                    db_client,
                    uid,
                    local_date,
                    source_key,
                    account_generation=account_generation,
                    source_generation=source_generation,
                    sweep_generation=sweep_generation,
                )
                source_receipts.append((source_ref, source_key))
            for candidate in candidates_by_source[source_key]:
                candidate_receipts.append(
                    _receipt_ref(
                        db_client,
                        uid,
                        _receipt_id(
                            uid,
                            local_date,
                            candidate,
                            account_generation=account_generation,
                            source_generation=source_generation,
                            sweep_generation=sweep_generation,
                        ),
                    )
                )
        source_snapshots = [transaction.get(ref) for ref, _ in source_receipts]
        candidate_snapshots = [transaction.get(ref) for ref in candidate_receipts]
        for snapshot in candidate_snapshots:
            if not getattr(snapshot, "exists", False) or (snapshot.to_dict() or {}).get("receipt_state") != "committed":
                return False
        next_consumed = list(consumed_values)
        for (source_ref, source_key), snapshot in zip(source_receipts, source_snapshots):
            if getattr(snapshot, "exists", False) and (snapshot.to_dict() or {}).get("receipt_state") == "committed":
                if source_key not in next_consumed:
                    next_consumed.append(source_key)
                continue
            transaction.set(
                source_ref,
                {
                    "schema_version": "daily_memory_sweep_onboarding_source.v1",
                    "uid": uid,
                    "local_date": local_date.isoformat(),
                    "source_key": source_key,
                    "account_generation": account_generation,
                    "source_generation": source_generation,
                    "sweep_generation": sweep_generation,
                    "window_id": window.window_id,
                    "window_start_utc": window.start_utc,
                    "window_end_utc": window.end_utc,
                    "receipt_state": "committed",
                    "completed_at": datetime.now(timezone.utc),
                },
            )
            if source_key not in next_consumed:
                next_consumed.append(source_key)
            offsets.pop(source_key, None)
        for source_key, offset in (source_progress or {}).items():
            if source_key not in normalized_keys or offset < 0:
                return False
            # A partial source has committed candidate receipts for exactly
            # this prefix.  Persisting the offset in the same transaction as
            # those proof reads makes retry/restart advance without dropping
            # the unprocessed tail.
            offsets[source_key] = offset
        transaction.set(
            consumed_ref,
            {
                "schema_version": "daily_memory_sweep_onboarding.v1",
                "consumed_source_keys": next_consumed[-MAX_CANDIDATES_PER_DAY:],
                "candidate_offsets": dict(list(offsets.items())[-MAX_CANDIDATES_PER_DAY:]),
                "account_generation": account_generation,
                "source_generation": source_generation,
                "sweep_generation": sweep_generation,
                "updated_at": datetime.now(timezone.utc),
            },
            merge=True,
        )
        return True

    return bool(firestore.transactional(complete)(db_client.transaction()))


def _target_for_candidate(uid: str, candidate: DailySweepCandidate, *, db_client: Any) -> Optional[MemoryItem]:
    if not candidate.target_memory_id:
        return None
    return read_canonical_memory_item(uid, candidate.target_memory_id, db_client=db_client)


def _target_authority(item: MemoryItem) -> int:
    reason = item.write_reason
    if reason in {
        LedgerWriteReason.direct_user_statement,
        LedgerWriteReason.explicit_remember,
        LedgerWriteReason.onboarding,
    }:
        return SweepAuthority.direct_user_statement.rank
    if reason == LedgerWriteReason.agent_reusable_conclusion:
        return SweepAuthority.agent_reusable_conclusion.rank
    return SweepAuthority.sweep_inference.rank


def _find_active_slot_or_subject(
    uid: str,
    candidate: DailySweepCandidate,
    *,
    db_client: Any,
) -> Optional[MemoryItem]:
    """Find one deterministic active canonical occupant using a targeted query.

    A broad collection scan is unsafe here: truncation could be mistaken for
    an empty slot and create a duplicate. The production query is narrowed by
    active fact + subject identity (+ slot when present), and a result page
    larger than the bounded proof fails closed.
    """

    if candidate.kind != "fact":
        return None
    collection = db_client.collection(MemoryCollections(uid=uid).memory_items)
    where = getattr(collection, "where", None)
    if not callable(where):
        raise SweepAuthoritativeQueryUnavailable("canonical occupant query is unavailable")
    values = {
        "status": MemoryItemStatus.active.value,
        "kind": MemoryKind.fact.value,
        "subject_scope": candidate.subject_scope.value,
    }
    snapshots: List[Any] = []
    try:
        if candidate.slot:
            query_spec = (
                DAILY_SWEEP_ACTIVE_FACT_ENTITY_SLOT_QUERY
                if candidate.subject_entity_id is not None
                else DAILY_SWEEP_ACTIVE_FACT_SLOT_QUERY
            )
        else:
            # Content equality is part of the Firestore predicate for the
            # unslotted path.  Do not bound a broad subject page and then
            # casefold/filter locally: the matching occupant could be row 4.
            query_spec = (
                DAILY_SWEEP_ACTIVE_FACT_ENTITY_CONTENT_QUERY
                if candidate.subject_entity_id is not None
                else DAILY_SWEEP_ACTIVE_FACT_SUBJECT_CONTENT_QUERY
            )
        query = query_spec.build(
            collection,
            {
                **values,
                **(
                    {"normalized_content_key": normalized_memory_content_key(candidate.content)}
                    if not candidate.slot
                    else {}
                ),
                **({"slot": candidate.slot} if candidate.slot else {}),
                **(
                    {"subject_entity_id": candidate.subject_entity_id}
                    if candidate.subject_entity_id is not None
                    else {}
                ),
            },
            field_filter_factory=FieldFilter,
        )
        snapshots = list(query.limit(MAX_AUTHORITATIVE_OCCUPANTS + 1).stream())
        if not candidate.slot and not snapshots:
            # Migration-safe fallback for rows written before the key was
            # introduced.  It remains a targeted subject/entity proof and
            # fails closed on truncation; it never scans an unbounded
            # collection or trusts a broad first page.
            legacy_spec = (
                DAILY_SWEEP_ACTIVE_FACT_ENTITY_QUERY
                if candidate.subject_entity_id is not None
                else DAILY_SWEEP_ACTIVE_FACT_SUBJECT_QUERY
            )
            legacy_query = legacy_spec.build(
                collection,
                {
                    **values,
                    **(
                        {"subject_entity_id": candidate.subject_entity_id}
                        if candidate.subject_entity_id is not None
                        else {}
                    ),
                },
                field_filter_factory=FieldFilter,
            )
            snapshots = list(legacy_query.limit(MAX_AUTHORITATIVE_OCCUPANTS + 1).stream())
    except Exception as exc:
        raise SweepAuthoritativeQueryUnavailable("canonical occupant query failed") from exc
    if len(snapshots) > MAX_AUTHORITATIVE_OCCUPANTS:
        raise SweepAuthoritativeQueryUnavailable("canonical occupant query exceeded proof budget")
    items: List[MemoryItem] = []
    for snapshot in snapshots:
        raw = snapshot.to_dict()
        if not isinstance(raw, dict):
            raise SweepAuthoritativeQueryUnavailable("canonical occupant row is malformed")
        item = MemoryItem.model_validate(raw)
        if (
            item.uid != uid
            or item.status != MemoryItemStatus.active
            or item.kind != MemoryKind.fact
            or item.subject_scope != candidate.subject_scope
            or item.subject_entity_id != candidate.subject_entity_id
            or (candidate.slot and item.slot != candidate.slot)
            or (not candidate.slot and item.normalized_content_key != normalized_memory_content_key(candidate.content))
        ):
            continue
        items.append(item)
    return sorted(items, key=lambda item: item.memory_id)[0] if items else None


def _apply_candidate(
    uid: str,
    local_date: date,
    candidate: DailySweepCandidate,
    *,
    db_client: Any,
) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(memory_id, skip_reason)``; all writes use canonical apply."""

    target = _target_for_candidate(uid, candidate, db_client=db_client)
    effective_operation = candidate.operation
    if candidate.operation == "add":
        occupant = _find_active_slot_or_subject(uid, candidate, db_client=db_client)
        if occupant is not None:
            if candidate.authority.rank <= _target_authority(occupant):
                return occupant.memory_id, "existing_active_slot" if candidate.slot else "existing_active_subject"
            target = occupant
            effective_operation = "amend"
    if effective_operation in {"amend", "repair"}:
        if target is None:
            return None, "missing_target"
        if target.status != MemoryItemStatus.active:
            return None, "target_not_active"
        if candidate.authority.rank < _target_authority(target):
            return None, "lower_authority"
        if candidate.kind == "fact" and target.kind != MemoryKind.fact:
            return None, "target_kind_mismatch"
        if candidate.kind == "trigger" and target.kind != MemoryKind.trigger:
            return None, "target_kind_mismatch"
        if candidate.kind == "trigger" and target.write_reason != LedgerWriteReason.standing_trigger:
            return None, "target_not_explicit_trigger"

    provenance = LedgerProvenance(
        source_id=candidate.source_id,
        source_type=candidate.source_type,
        source_version=candidate.source_version,
        action_id=f"{_plan_id(uid, local_date)}:{candidate.source_key}",
        artifact_ref={
            "local_date": local_date.isoformat(),
            "source_refs": list(candidate.source_refs),
            # Repair provenance is deliberately separate from the durable
            # standing-trigger authority below.
            "sweep_repair": (
                {
                    "schema_version": SCHEMA_VERSION,
                    "authority": candidate.authority.value,
                    "operation": candidate.operation,
                }
                if candidate.kind == "trigger"
                else None
            ),
        },
        quote_refs=[{"source_ref": ref} for ref in candidate.source_refs],
    )
    if candidate.kind == "trigger":
        reason = LedgerWriteReason.standing_trigger
    elif candidate.source_type == "onboarding":
        reason = LedgerWriteReason.onboarding
    else:
        reason = candidate.authority.ledger_reason
    if effective_operation == "amend":
        assert target is not None
        memory_id = amend_fact(
            uid,
            target.memory_id,
            candidate.content,
            provenance=provenance,
            write_reason=reason,
            slot=candidate.slot,
            subject_scope=candidate.subject_scope,
            subject_entity_id=candidate.subject_entity_id,
            valid_from=datetime.combine(local_date, time.min, tzinfo=timezone.utc),
            db_client=db_client,
            required_source_item=target,
        )
        return memory_id, None

    write = LedgerWrite(
        kind=MemoryKind.trigger if candidate.kind == "trigger" else MemoryKind.fact,
        content=candidate.content,
        provenance=provenance,
        write_reason=reason,
        subject_scope=candidate.subject_scope,
        subject_entity_id=candidate.subject_entity_id,
        slot=candidate.slot,
        trigger_condition=candidate.trigger_condition,
        # A completed-day replay must derive identical mutation metadata.  The
        # ledger otherwise defaults ``valid_from`` to wall-clock ``now`` and a
        # crash after canonical apply would produce a different operation ID.
        valid_from=datetime.combine(local_date, time.min, tzinfo=timezone.utc),
        # Inference-backed rows stay out of the user-asserted profile path.
        user_asserted=candidate.authority == SweepAuthority.direct_user_statement,
        supersedes=([target.memory_id] if effective_operation == "repair" and target is not None else []),
    )
    return save_ledger_write(uid, write, db_client=db_client, required_source_item=target), None


def _blocked_output(
    uid: str, reason: str, *, status: Literal["blocked", "disabled", "not_due"] = "blocked"
) -> DailySweepOutput:
    return DailySweepOutput(
        uid=uid,
        status=status,
        blocked_reason=reason if status == "blocked" else None,
        telemetry={"status": status, "blocked_reason": reason if status == "blocked" else "none"},
    )


def run_daily_memory_sweep(
    uid: str,
    timezone_name: str,
    now: datetime,
    inputs_by_date: Mapping[date, DailySweepInput],
    *,
    db_client: Any,
    authority: SweepAuthorityState = SweepAuthorityState(),
    max_catch_up_days: int = MAX_CATCH_UP_DAYS,
    claimant: Optional[str] = None,
) -> DailySweepOutput:
    """Run bounded completed local days with durable cursor and source receipts.

    ``inputs_by_date`` is server-owned and must contain only complete local-day
    packets.  The function never consumes today's partial window.  It advances
    the cursor only after every candidate in a day is either committed,
    idempotently replayed, or explicitly skipped by a deterministic validation
    fence.  A canonical write failure leaves the cursor behind for retry.
    """

    normalized_uid = (uid or "").strip()
    validate_uid_for_memory_path(normalized_uid)
    if not authority.may_write:
        return _blocked_output(normalized_uid, "authority_closed", status="disabled")
    if max_catch_up_days < 1 or max_catch_up_days > MAX_CATCH_UP_DAYS:
        raise ValueError("max_catch_up_days must be between 1 and the bounded maximum")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    try:
        local_today = now.astimezone(ZoneInfo(timezone_name)).date()
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("timezone_name must be a valid IANA timezone") from exc
    if any(packet.uid != normalized_uid for packet in inputs_by_date.values()):
        return _blocked_output(normalized_uid, "input_owner_mismatch")

    try:
        deletion_fence = read_account_deletion_projection_fence(normalized_uid, db_client=db_client)
        if deletion_fence.blocks_projection_writes:
            return _blocked_output(normalized_uid, "account_deletion_fence")
        control = ensure_canonical_apply_control_state(normalized_uid, db_client=db_client)
        cursor = _read_cursor(db_client, normalized_uid, control)
    except Exception:
        return _blocked_output(normalized_uid, "authority_state_unavailable")
    if cursor.last_completed_local_date is not None and cursor.timezone_name != timezone_name:
        # Changing zones can make a previously completed local date overlap or
        # leave a gap in UTC.  Require an explicit server-side reconciliation;
        # never silently replay or skip data.
        return _blocked_output(normalized_uid, "timezone_changed_requires_reconciliation")
    eligible_through = local_today - timedelta(days=1)
    first_pending = (
        cursor.last_completed_local_date + timedelta(days=1)
        if cursor.last_completed_local_date is not None
        else eligible_through
    )
    pending_receipt_dates = _pending_receipt_dates(
        db_client,
        normalized_uid,
        through=eligible_through,
        account_generation=control.account_generation,
        source_generation=control.source_generation,
        sweep_generation=cursor.sweep_generation,
    )
    if first_pending > eligible_through:
        return _blocked_output(normalized_uid, "no_completed_local_day", status="not_due")
    if pending_receipt_dates:
        # A crash can leave a receipt for an older day while the wall clock
        # moves on. Recover that exact day first; do not demand a newer day's
        # source packet and accidentally turn a recoverable replay into a
        # cursor-advancing gap.
        dates = list(pending_receipt_dates[:max_catch_up_days])
    else:
        dates = [first_pending + timedelta(days=index) for index in range(max_catch_up_days)]
        dates = [item for item in dates if item <= eligible_through]

    completed: List[date] = []
    committed_count = 0
    idempotent_count = 0
    skipped_count = 0
    current_cursor = cursor
    # A production invocation owns a unique lease. Date-derived claimants made
    # two independent runners look like one worker and could strand pending
    # work across the next day.
    receipt_claimant = claimant or f"run:{uuid4().hex}"
    for local_date in dates:
        packet = inputs_by_date.get(local_date)
        if packet is None:
            return _blocked_output(normalized_uid, f"missing_input:{local_date.isoformat()}")
        if packet.local_date != local_date:
            return _blocked_output(normalized_uid, "input_date_mismatch")
        if (
            packet.account_generation != control.account_generation
            or packet.source_generation != control.source_generation
            or packet.sweep_generation != current_cursor.sweep_generation
        ):
            return _blocked_output(normalized_uid, "input_generation_mismatch")
        if packet.timezone_name != timezone_name:
            return _blocked_output(normalized_uid, "input_timezone_mismatch")
        expected_window = completed_local_day_window(local_date, timezone_name)
        if (
            not packet.complete
            or packet.window_id != expected_window.window_id
            or packet.window_start_utc != expected_window.start_utc
            or packet.window_end_utc != expected_window.end_utc
        ):
            return _blocked_output(normalized_uid, "incomplete_or_wrong_window")
        try:
            plan = plan_daily_memory_sweep(packet)
        except Exception:
            return _blocked_output(normalized_uid, "invalid_input_packet")
        skipped_count += len(plan.skipped)
        if len(plan.candidates) > MAX_WRITES_PER_DAY:
            return _blocked_output(normalized_uid, "write_budget_exceeded")
        for candidate in plan.candidates:
            claim = _claim_receipt(
                db_client,
                normalized_uid,
                local_date,
                candidate,
                account_generation=control.account_generation,
                source_generation=control.source_generation,
                claimant=receipt_claimant,
                claim_now=now,
                window=expected_window,
                sweep_generation=current_cursor.sweep_generation,
            )
            if claim == "conflict":
                return _blocked_output(normalized_uid, "source_idempotency_conflict")
            if claim == "idempotent":
                idempotent_count += 1
                continue
            try:
                memory_id, skip_reason = _apply_candidate(
                    normalized_uid,
                    local_date,
                    candidate,
                    db_client=db_client,
                )
            except SweepAuthoritativeQueryUnavailable:
                return _blocked_output(normalized_uid, "canonical_occupant_query_unavailable")
            if skip_reason:
                skipped_count += 1
                try:
                    _finish_receipt(
                        db_client,
                        normalized_uid,
                        local_date,
                        candidate,
                        memory_id=memory_id,
                        outcome="skipped",
                        skip_reason=skip_reason,
                        account_generation=control.account_generation,
                        source_generation=control.source_generation,
                        claimant=receipt_claimant,
                        window=expected_window,
                        sweep_generation=current_cursor.sweep_generation,
                    )
                except SweepFenceBlocked:
                    return _blocked_output(normalized_uid, "receipt_completion_fence_closed")
                continue
            if not memory_id:
                return _blocked_output(normalized_uid, "empty_canonical_write_result")
            try:
                _finish_receipt(
                    db_client,
                    normalized_uid,
                    local_date,
                    candidate,
                    memory_id=memory_id,
                    account_generation=control.account_generation,
                    source_generation=control.source_generation,
                    claimant=receipt_claimant,
                    window=expected_window,
                    sweep_generation=current_cursor.sweep_generation,
                )
            except SweepFenceBlocked:
                return _blocked_output(normalized_uid, "receipt_completion_fence_closed")
            committed_count += 1
        if not _finish_onboarding_sources(
            db_client,
            normalized_uid,
            local_date,
            packet.onboarding_source_keys,
            plan.candidates,
            account_generation=control.account_generation,
            source_generation=control.source_generation,
            window=expected_window,
            source_progress=packet.onboarding_source_progress,
            sweep_generation=current_cursor.sweep_generation,
        ):
            return _blocked_output(normalized_uid, "onboarding_source_receipt_incomplete")
        window = completed_local_day_window(local_date, timezone_name)
        window_start_utc, window_end_utc, window_id = window.start_utc, window.end_utc, window.window_id
        if not _advance_cursor(
            db_client,
            normalized_uid,
            control,
            current_cursor,
            local_date,
            timezone_name,
            window_start_utc,
            window_end_utc,
            window_id,
            sweep_generation=current_cursor.sweep_generation,
        ):
            return _blocked_output(normalized_uid, "cursor_conflict")
        current_cursor = current_cursor.model_copy(
            update={
                "generation": current_cursor.generation + 1,
                "timezone_name": timezone_name,
                "last_completed_local_date": local_date,
                "last_completed_window_id": window_id,
                "last_completed_window_start_utc": window_start_utc,
                "last_completed_window_end_utc": window_end_utc,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        completed.append(local_date)

    status: Literal["committed"] = "committed"
    return DailySweepOutput(
        uid=normalized_uid,
        status=status,
        completed_local_dates=tuple(completed),
        committed_count=committed_count,
        idempotent_count=idempotent_count,
        skipped_count=skipped_count,
        telemetry={
            "status": status,
            "days": len(completed),
            "committed": committed_count,
            "idempotent": idempotent_count,
            "skipped": skipped_count,
        },
    )


@dataclass(frozen=True)
class DailySweepRuntimeSources:
    """Structured server-owned sources adapted by the maintenance scheduler.

    ``daily_summary`` is the normal completed-day producer.  The two explicit
    auxiliary channels keep onboarding cold-start facts and reconciliation of
    already-standing triggers visible in the contract; neither channel may
    create a trigger from passive behavior.
    """

    daily_summary: Tuple[DailySweepCandidate, ...] = ()
    onboarding_cold_start: Tuple[DailySweepCandidate, ...] = ()
    existing_trigger_reconciliation: Tuple[DailySweepCandidate, ...] = ()
    # ``complete`` is an immutable producer attestation. False means the
    # source is absent/partial and the cursor must not advance, even when the
    # candidate list is empty (the explicit complete-zero case is True).
    complete: bool = False
    source_status: Literal["complete", "complete_zero", "incomplete", "absent"] = "incomplete"
    # All unconsumed onboarding source identities observed by the producer.
    # This includes zero-candidate sources and is completed only after the
    # corresponding candidate receipts are durable.
    onboarding_source_keys: Tuple[str, ...] = ()
    onboarding_source_progress: Mapping[str, int] = field(default_factory=dict)
    eligibility_proof: Literal["completed_transcript_v1", "none"] = "none"
    # Content-free accounting used to enforce the model budget.  It is never
    # emitted as a user-facing telemetry payload.
    model_cost_usd: float = 0.0

    @classmethod
    def from_iterables(
        cls,
        *,
        daily_summary: Iterable[DailySweepCandidate] = (),
        onboarding_cold_start: Iterable[DailySweepCandidate] = (),
        existing_trigger_reconciliation: Iterable[DailySweepCandidate] = (),
        complete: bool = False,
        source_status: Literal["complete", "complete_zero", "incomplete", "absent"] = "incomplete",
        onboarding_source_keys: Iterable[str] = (),
        onboarding_source_progress: Optional[Mapping[str, int]] = None,
        eligibility_proof: Literal["completed_transcript_v1", "none"] = "none",
        model_cost_usd: float = 0.0,
    ) -> "DailySweepRuntimeSources":
        summary_values = tuple(daily_summary)
        onboarding_values = tuple(onboarding_cold_start)
        trigger_values = tuple(existing_trigger_reconciliation)
        normalized_status: Literal["complete", "complete_zero", "incomplete", "absent"] = (
            "complete"
            if complete and source_status == "complete_zero" and (summary_values or onboarding_values or trigger_values)
            else source_status
        )
        return cls(
            daily_summary=summary_values,
            onboarding_cold_start=onboarding_values,
            existing_trigger_reconciliation=trigger_values,
            complete=complete,
            source_status=normalized_status,
            onboarding_source_keys=tuple(sorted(set(onboarding_source_keys))),
            onboarding_source_progress=dict(onboarding_source_progress or {}),
            eligibility_proof=eligibility_proof,
            model_cost_usd=model_cost_usd,
        )

    def candidates(self) -> Tuple[DailySweepCandidate, ...]:
        return self.daily_summary + self.onboarding_cold_start + self.existing_trigger_reconciliation


def build_daily_sweep_input(
    uid: str,
    local_date: date,
    *,
    account_generation: int,
    source_generation: int,
    sweep_generation: int = 1,
    timezone_name: str,
    sources: DailySweepRuntimeSources,
) -> DailySweepInput:
    """Adapt typed daily-summary/onboarding/trigger sources into one packet."""

    window = completed_local_day_window(local_date, timezone_name)
    return DailySweepInput(
        uid=uid,
        local_date=local_date,
        account_generation=account_generation,
        source_generation=source_generation,
        sweep_generation=sweep_generation,
        timezone_name=timezone_name,
        window_id=window.window_id,
        window_start_utc=window.start_utc,
        window_end_utc=window.end_utc,
        complete=sources.complete,
        candidates=sources.candidates(),
        onboarding_source_keys=sources.onboarding_source_keys,
        onboarding_source_progress=dict(sources.onboarding_source_progress or {}),
        eligibility_proof=sources.eligibility_proof,
    )


def _bounded_candidate_channel(
    raw: Any,
    *,
    source_type: Optional[str] = None,
    authority: Optional[SweepAuthority] = None,
    trusted_direct: bool = False,
    max_candidates: int = MAX_CANDIDATES_PER_DAY,
) -> Tuple[DailySweepCandidate, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)) or len(raw) > max_candidates:
        raise ValueError("daily sweep source channel exceeds its bounded candidate budget")
    parsed: List[DailySweepCandidate] = []
    for item in raw:
        if isinstance(item, DailySweepCandidate):
            payload = item.model_dump(mode="python")
        elif isinstance(item, dict):
            payload = dict(item)
        else:
            raise ValueError("daily sweep source candidate must be an object")
        # Source producers are not authorities.  Never let a producer payload
        # smuggle in direct-user authority (or a different source type).  The
        # only exception is the trusted canonical onboarding channel, whose
        # adapter has already authenticated that the evidence came from an
        # onboarding conversation.
        if source_type is not None:
            supplied_source_type = payload.get("source_type")
            if supplied_source_type is not None and supplied_source_type != source_type:
                if not (trusted_direct and supplied_source_type == "explicit_user_statement"):
                    raise ValueError("daily sweep candidate source type is not trusted")
            payload["source_type"] = source_type
        if authority is not None:
            supplied_authority = payload.get("authority")
            if supplied_authority is not None:
                try:
                    supplied_authority = SweepAuthority(supplied_authority)
                except ValueError as exc:
                    raise ValueError("daily sweep candidate authority is invalid") from exc
                if supplied_authority != authority and not (
                    trusted_direct and supplied_authority == SweepAuthority.direct_user_statement
                ):
                    raise ValueError("daily sweep candidate authority is not trusted")
            payload["authority"] = authority
        candidate = DailySweepCandidate.model_validate(payload)
        parsed.append(candidate)
    return tuple(parsed)


def _read_completed_day_conversation_texts(
    uid: str,
    window: CompletedLocalDayWindow,
    *,
    db_client: Any,
    max_conversations: int,
    max_characters: int,
) -> Tuple[Tuple[Tuple[str, str], ...], Literal["complete", "incomplete"]]:
    """Read only bounded textual conversations in one exact UTC window.

    This adapter deliberately strips photos and other media.  A query failure,
    an over-budget page, or an undecodable conversation is incomplete rather
    than an empty source, so callers cannot move the cursor past unprocessed
    data.
    """

    collection = db_client.collection(f"users/{uid}/conversations")
    where = getattr(collection, "where", None)
    if not callable(where):
        return (), "incomplete"
    try:
        try:
            query: Any = where(filter=FieldFilter("started_at", ">=", window.start_utc))
            query = query.where(filter=FieldFilter("started_at", "<", window.end_utc))
        except TypeError:
            query = where("started_at", ">=", window.start_utc)
            query = query.where("started_at", "<", window.end_utc)
        try:
            query = query.order_by("started_at")
        except (AttributeError, TypeError):
            # A small injected emulator fake may not implement ordering; the
            # identity and bounded page still hold, and model output is sorted
            # below by the stable document id.
            pass
        snapshots = list(query.limit(max_conversations + 1).stream())
    except Exception:
        return (), "incomplete"
    if len(snapshots) > max_conversations:
        return (), "incomplete"

    from database.conversations import (  # pyright: ignore[reportPrivateUsage]
        _prepare_conversation_for_read as prepare_conversation_for_read,  # pyright: ignore[reportPrivateUsage]
    )
    from models.conversation import Conversation

    rows: List[Tuple[str, str]] = []
    total_characters = 0
    for snapshot in snapshots:
        conversation_id = str(getattr(snapshot, "id", "") or "")
        raw = snapshot.to_dict() or {}
        if not conversation_id or not isinstance(raw, dict):
            return (), "incomplete"
        # A timestamp range is not an eligibility proof.  Discarded rows are
        # intentionally excluded, while processing/in-progress/unfinished
        # rows keep the source incomplete so a later retry cannot advance the
        # cursor past a transcript that may still change.
        eligibility = _completed_day_row_eligibility(raw)
        if eligibility == "discarded":
            continue
        if eligibility != "eligible":
            return (), "incomplete"
        try:
            prepared = prepare_conversation_for_read(raw, uid)  # pyright: ignore[reportPrivateUsage]
            conversation = Conversation(**(prepared or {}))
            # TranscriptSegment.segments_as_string is the canonical textual
            # rendering.  It ignores photos by construction.
            text = conversation.get_transcript(include_timestamps=False) or ""
        except Exception:
            return (), "incomplete"
        text = text.strip()
        if not text:
            continue
        total_characters += len(text)
        if total_characters > max_characters:
            return (), "incomplete"
        rows.append((conversation_id, text))
    rows.sort(key=lambda row: row[0])
    return tuple(rows), "complete"


def _completed_day_row_eligibility(raw: Mapping[str, Any]) -> Literal["eligible", "discarded", "unfinished"]:
    """Return the pre-extraction eligibility proof for one conversation row."""

    if bool(raw.get("discarded", False)):
        return "discarded"
    raw_status = raw.get("status")
    status = getattr(raw_status, "value", raw_status)
    if status != "completed" or not isinstance(raw.get("finished_at"), datetime):
        return "unfinished"
    return "eligible"


def _extract_daily_memory_candidates(uid: str, text: str) -> Tuple[Any, ...]:
    """Invoke Omi's existing bounded memory extractor for sweep input."""

    from utils.llm.memories import extract_memories_from_text

    # The model receives transcript text only.  ``strict`` makes provider or
    # parser failure visible to the producer rather than silently attesting an
    # empty day.
    return tuple(extract_memories_from_text(uid, text, "daily_summary", strict=True))


def _cached_summary_eligibility_attested(
    payload: Mapping[str, Any],
    *,
    local_date: date,
    window: CompletedLocalDayWindow,
    timezone_name: Optional[str] = None,
) -> bool:
    """Prove a cached candidate channel came from a completed-day producer.

    ``memory_candidates`` was historically an opportunistic cache field.  It
    is not sufficient evidence that all conversations in the UTC window were
    terminal, or that discarded/processing rows were excluded.  The cache is
    therefore accepted only with the producer's immutable attestation.
    """

    if payload.get("complete") is not True or payload.get("eligibility_proof") != "completed_transcript_v1":
        return False
    if payload.get("source_status") not in {"complete", "complete_zero"}:
        return False
    attestation = payload.get("eligibility_attestation")
    if not isinstance(attestation, Mapping):
        return False
    if (
        attestation.get("schema_version") != "completed_day_eligibility.v1"
        or attestation.get("local_date") != local_date.isoformat()
        or not isinstance(attestation.get("timezone_name"), str)
        or (timezone_name is not None and attestation.get("timezone_name") != timezone_name)
        or attestation.get("window_id") != window.window_id
        or attestation.get("window_start_utc") != window.start_utc
        or attestation.get("window_end_utc") != window.end_utc
    ):
        return False
    # Any discarded, processing, unfinished, or missing row makes the packet
    # incomplete.  Complete-zero is represented by all counts being zero.
    for key in ("eligible_count", "discarded_count", "processing_count", "unfinished_count"):
        value = attestation.get(key)
        if not isinstance(value, int) or value < 0:
            return False
    return (
        attestation["discarded_count"] == 0
        and attestation["processing_count"] == 0
        and attestation["unfinished_count"] == 0
    )


def _onboarding_consumed_keys(db_client: Any, uid: str) -> frozenset[str]:
    snapshot = db_client.document(f"users/{uid}/{ONBOARDING_CONSUMED_STATE_PATH}").get()
    if not getattr(snapshot, "exists", False):
        return frozenset()
    payload = snapshot.to_dict() or {}
    values = payload.get("consumed_source_keys") if isinstance(payload, dict) else None
    if not isinstance(values, list):
        return frozenset()
    return frozenset(str(value) for value in values if isinstance(value, str))


@dataclass(frozen=True)
class OnboardingSourceProduction:
    """Named result for the bounded onboarding producer contract."""

    candidates: Tuple[DailySweepCandidate, ...] = ()
    complete: bool = False
    source_keys: Tuple[str, ...] = ()
    source_progress: Mapping[str, int] = field(default_factory=dict)


def _produce_onboarding_sources(
    uid: str,
    *,
    db_client: Any,
    max_candidates: int,
    model_authority: DailySweepModelAuthority,
    model_extractor: Optional[Any] = None,
) -> OnboardingSourceProduction:
    """Produce once-only facts from server-marked onboarding conversations.

    ``request.source`` and client onboarding flags are not provenance.  The
    listen runtime writes a random server-generated onboarding session marker
    into ``external_data``; only that marker is accepted here.  The returned
    source keys are consumed later, after all candidate receipts (or an
    explicit zero-candidate source receipt) commit.
    """

    collection = db_client.collection(f"users/{uid}/conversations")
    where = getattr(collection, "where", None)
    if not callable(where):
        return OnboardingSourceProduction()
    consumed = _onboarding_consumed_keys(db_client, uid)
    try:
        # The server-generated marker is the only provenance predicate. Read
        # bounded ordered pages and keep paging past consumed rows before the
        # processable cap. This cannot starve behind hundreds of old sources.
        snapshots: List[Any] = []
        after_id = ""
        for _ in range(MAX_ONBOARDING_SCAN_PAGES):
            try:
                query: Any = where(filter=FieldFilter("external_data.onboarding_session_id", ">", ""))
            except TypeError:
                query = where("external_data.onboarding_session_id", ">", "")
            if after_id:
                try:
                    query = query.where(filter=FieldFilter(FieldPath.document_id(), ">", after_id))
                except TypeError:
                    query = query.where(FieldPath.document_id(), ">", after_id)
            try:
                query = query.order_by(FieldPath.document_id())
            except (AttributeError, TypeError):
                try:
                    query = query.order_by("__name__")
                except (AttributeError, TypeError):
                    pass
            page = list(query.limit(MAX_ONBOARDING_CONVERSATIONS).stream())
            if not page:
                break
            snapshots.extend(page)
            after_id = str(getattr(page[-1], "id", "") or "")
            processable = sum(1 for row in snapshots if f"onboarding:{getattr(row, 'id', '')}" not in consumed)
            if processable >= MAX_ONBOARDING_CONVERSATIONS or len(page) < MAX_ONBOARDING_CONVERSATIONS:
                break
    except Exception:
        return OnboardingSourceProduction()
    progress_snapshot = db_client.document(f"users/{uid}/{ONBOARDING_CONSUMED_STATE_PATH}").get()
    progress_payload = progress_snapshot.to_dict() if getattr(progress_snapshot, "exists", False) else {}
    raw_progress = progress_payload.get("candidate_offsets", {}) if isinstance(progress_payload, dict) else {}
    candidate_offsets = {
        key: int(value)
        for key, value in raw_progress.items()
        if isinstance(key, str) and key.startswith("onboarding:") and isinstance(value, int) and value >= 0
    }
    from database.conversations import (  # pyright: ignore[reportPrivateUsage]
        _prepare_conversation_for_read as prepare_conversation_for_read,  # pyright: ignore[reportPrivateUsage]
    )
    from models.conversation import Conversation

    rows: List[Tuple[str, str]] = []
    source_keys: List[str] = []
    source_progress: Dict[str, int] = {}
    zero_source_keys: List[str] = []
    total_characters = 0
    for snapshot in snapshots:
        conversation_id = str(getattr(snapshot, "id", "") or "")
        raw = snapshot.to_dict() or {}
        if not conversation_id or not isinstance(raw, dict):
            return OnboardingSourceProduction()
        external_data = raw.get("external_data")
        onboarding_session_id = external_data.get("onboarding_session_id") if isinstance(external_data, dict) else None
        if not isinstance(onboarding_session_id, str) or len(onboarding_session_id) < 16:
            continue
        source_key = f"onboarding:{conversation_id}"
        if source_key in consumed:
            continue
        # Filtering occurs before the processable cap.  A consumed row never
        # occupies one of the eight source slots.
        if len(source_keys) >= MAX_ONBOARDING_CONVERSATIONS:
            continue
        source_keys.append(source_key)
        try:
            prepared = prepare_conversation_for_read(raw, uid)  # pyright: ignore[reportPrivateUsage]
            conversation = Conversation(**(prepared or {}))
            text = (conversation.get_transcript(include_timestamps=False) or "").strip()
        except Exception:
            return OnboardingSourceProduction()
        if not text:
            # An empty onboarding recording is a complete, consumed source; it
            # cannot become a direct memory later.
            zero_source_keys.append(source_key)
            continue
        total_characters += len(text)
        if total_characters > MAX_ONBOARDING_INPUT_CHARACTERS:
            return OnboardingSourceProduction()
        rows.append((conversation_id, text))
    if not rows:
        # Includes non-empty source rows whose model output is empty and
        # genuinely empty transcripts.  The caller still receives source_keys
        # so the source is consumed exactly once after the day packet commits.
        return OnboardingSourceProduction(complete=True, source_keys=tuple(source_keys))
    if not model_authority.route_is_budgeted:
        return OnboardingSourceProduction()
    extractor = model_extractor or _extract_daily_memory_candidates
    if model_extractor is None:
        from utils.llm.model_config import get_model

        if model_authority.model_name != get_model("memories"):
            return OnboardingSourceProduction()
    estimated_cost = (total_characters / 1000.0) * MODEL_COST_PER_1K_INPUT_CHARACTERS_USD
    if estimated_cost > model_authority.max_cost_usd:
        return OnboardingSourceProduction()
    candidates: List[DailySweepCandidate] = []
    processed_source_keys = list(zero_source_keys)
    try:
        for conversation_id, text in rows:
            row_candidates: List[DailySweepCandidate] = []
            source_key = f"onboarding:{conversation_id}"
            offset = candidate_offsets.get(source_key, 0)
            extracted = tuple(extractor(uid, text) or ())
            if offset > len(extracted):
                return OnboardingSourceProduction()
            row_candidates_all: List[Tuple[int, DailySweepCandidate]] = []
            for index, memory in enumerate(extracted[offset:], start=offset):
                content = str(getattr(memory, "content", "") or "").strip()
                if not content:
                    continue
                row_candidates_all.append(
                    (
                        index,
                        DailySweepCandidate(
                            candidate_id=deterministic_contract_id(
                                "daily-sweep-onboarding-candidate",
                                {"uid": uid, "source": conversation_id, "index": index},
                            )[:128],
                            kind="fact",
                            operation="add",
                            content=content,
                            source_id=f"onboarding:{conversation_id}",
                            source_type="onboarding",
                            source_version="onboarding-memory-model.v1",
                            source_refs=(f"conversation:{conversation_id}",),
                            authority=SweepAuthority.direct_user_statement,
                            subject_scope=MemorySubjectScope.primary_user,
                            subject_entity_id=getattr(memory, "subject_entity_id", None),
                        ),
                    )
                )
            available = max(0, max_candidates - len(candidates))
            row_candidates = [candidate for _, candidate in row_candidates_all[:available]]
            candidates.extend(row_candidates)
            if available == 0:
                next_offset = offset
            elif len(row_candidates_all) <= available:
                next_offset = len(extracted)
            else:
                next_offset = row_candidates_all[available - 1][0] + 1
            if next_offset >= len(extracted):
                processed_source_keys.append(source_key)
            else:
                # Preserve the unconsumed tail for a later bounded packet.
                source_progress[source_key] = next_offset
                processed_source_keys.append(source_key)
            if len(candidates) >= max_candidates:
                break
    except Exception:
        return OnboardingSourceProduction()
    # Sources after the bounded candidate page remain retryable.  They are not
    # included in the source-completion attestation for this packet.
    return OnboardingSourceProduction(
        candidates=tuple(candidates),
        complete=True,
        source_keys=tuple(sorted(set(processed_source_keys))),
        source_progress=source_progress,
    )


def produce_completed_day_daily_summary_sources(
    uid: str,
    local_date: date,
    timezone_name: str,
    control: MemoryControlState,
    *,
    db_client: Any,
    model_authority: Optional[DailySweepModelAuthority] = None,
    model_extractor: Optional[Any] = None,
) -> DailySweepRuntimeSources:
    """Produce the exact completed-day source, including its bounded model call.

    A summary document is a cache, not a producer authority.  When its
    candidate channel is absent, this function reads the completed day's
    conversation transcripts and invokes the existing memory extractor behind
    the explicit model/cost seam.  The cursor advances for an empty day only
    after a bounded source query proves that the day contained no textual
    conversations (or a summary explicitly attests zero conversations).
    """

    window = completed_local_day_window(local_date, timezone_name)
    collection = db_client.collection(f"users/{uid}/daily_summaries")
    where = getattr(collection, "where", None)
    if not callable(where):
        raise ValueError("daily summary completed-day query is unavailable")
    try:
        try:
            query: Any = where(filter=FieldFilter("date", "==", local_date.isoformat()))
        except TypeError:
            query = where("date", "==", local_date.isoformat())
        snapshots = list(query.limit(1).stream())
    except Exception as exc:
        raise ValueError("daily summary completed-day query failed") from exc
    payload: Dict[str, Any] = {}
    if snapshots:
        payload_value = snapshots[0].to_dict() or {}
        if not isinstance(payload_value, dict):
            raise ValueError("daily summary payload is malformed")
        payload = payload_value
        if payload.get("date") != local_date.isoformat():
            raise ValueError("daily summary date identity mismatch")
        if any(key in payload for key in ("window_id", "window_start_utc", "window_end_utc")) and (
            payload.get("window_id") != window.window_id
            or payload.get("window_start_utc") != window.start_utc
            or payload.get("window_end_utc") != window.end_utc
        ):
            raise ValueError("daily summary window identity mismatch")

    model = model_authority or daily_memory_sweep_model_authority_from_environment()

    # A persisted candidate list is accepted only when the model authority is
    # open.  In particular, a missing key is not interpreted as []: older
    # summary writers did not produce this field and must not advance the new
    # cursor without a producer proof.
    if "memory_candidates" in payload:
        raw_candidates = payload.get("memory_candidates")
        if (
            raw_candidates is None
            or payload.get("uid") != uid
            or payload.get("account_generation") != control.account_generation
            or payload.get("source_generation") != control.source_generation
            or payload.get("timezone_name") != timezone_name
            or not _cached_summary_eligibility_attested(
                payload, local_date=local_date, window=window, timezone_name=timezone_name
            )
        ):
            return DailySweepRuntimeSources.from_iterables(source_status="incomplete")
        if not model.route_is_budgeted:
            return DailySweepRuntimeSources.from_iterables(source_status="incomplete")
        persisted_candidates = _bounded_candidate_channel(
            raw_candidates,
            source_type="daily_summary",
            authority=SweepAuthority.sweep_inference,
            max_candidates=model.max_candidates,
        )
        return DailySweepRuntimeSources.from_iterables(
            daily_summary=persisted_candidates,
            complete=True,
            source_status="complete" if persisted_candidates else "complete_zero",
            model_cost_usd=0.0,
        )

    conversation_rows, conversation_status = _read_completed_day_conversation_texts(
        uid,
        window,
        db_client=db_client,
        max_conversations=MAX_COMPLETED_DAY_CONVERSATIONS,
        max_characters=MAX_COMPLETED_DAY_INPUT_CHARACTERS,
    )
    if conversation_status == "incomplete":
        return DailySweepRuntimeSources.from_iterables(source_status="incomplete")
    if not conversation_rows:
        # The query itself is the producer's complete-zero attestation.  A
        # missing summary is therefore safe only after this proof, never from
        # a missing Firestore document alone.
        return DailySweepRuntimeSources.from_iterables(
            complete=True,
            source_status="complete_zero",
            eligibility_proof="completed_transcript_v1",
        )
    if not model.route_is_budgeted:
        return DailySweepRuntimeSources.from_iterables(source_status="incomplete")

    extractor = model_extractor or _extract_daily_memory_candidates
    if model_extractor is None:
        # The deployment may only name the model configured for the existing
        # memory route.  It cannot select an arbitrary model through a source
        # packet or staging document.
        from utils.llm.model_config import get_model

        if model.model_name != get_model("memories"):
            return DailySweepRuntimeSources.from_iterables(source_status="incomplete")
    total_characters = sum(len(text) for _, text in conversation_rows)
    estimated_cost = (total_characters / 1000.0) * MODEL_COST_PER_1K_INPUT_CHARACTERS_USD
    if estimated_cost > model.max_cost_usd:
        return DailySweepRuntimeSources.from_iterables(source_status="incomplete")
    candidates: List[DailySweepCandidate] = []
    try:
        for conversation_id, text in conversation_rows:
            extracted = extractor(uid, text)
            for index, memory in enumerate(extracted or ()):
                content = str(getattr(memory, "content", "") or "").strip()
                if not content:
                    continue
                source_id = f"conversation:{conversation_id}"
                candidates.append(
                    DailySweepCandidate(
                        candidate_id=deterministic_contract_id(
                            "daily-sweep-model-candidate",
                            {"uid": uid, "date": local_date.isoformat(), "source": source_id, "index": index},
                        )[:128],
                        kind="fact",
                        operation="add",
                        content=content,
                        source_id=source_id,
                        source_type="daily_summary",
                        source_version="daily-memory-model.v1",
                        source_refs=(f"conversation:{conversation_id}",),
                        authority=SweepAuthority.sweep_inference,
                        subject_scope=MemorySubjectScope.primary_user,
                        subject_entity_id=getattr(memory, "subject_entity_id", None),
                    )
                )
                if len(candidates) >= model.max_candidates:
                    break
            if len(candidates) >= model.max_candidates:
                break
    except Exception:
        # Model/provider failures are source incompleteness, not complete-zero.
        return DailySweepRuntimeSources.from_iterables(source_status="incomplete")
    return DailySweepRuntimeSources.from_iterables(
        daily_summary=candidates,
        complete=True,
        source_status="complete" if candidates else "complete_zero",
        eligibility_proof="completed_transcript_v1",
        model_cost_usd=estimated_cost,
    )


def produce_onboarding_seed_sources(
    uid: str,
    *,
    db_client: Any,
    max_candidates: int = 8,
) -> Tuple[DailySweepCandidate, ...]:
    """Return candidates from the real onboarding conversation source.

    The old adapter read ``users.onboarding.memory_candidates`` even though no
    writer ever persisted that field.  Onboarding is represented by
    conversations carrying a server-generated session marker.  Consumption is
    marked transactionally after the source's candidate receipts complete.
    """

    production = _produce_onboarding_sources(
        uid,
        db_client=db_client,
        max_candidates=max_candidates,
        model_authority=daily_memory_sweep_model_authority_from_environment(),
    )
    return production.candidates


def _iter_active_standing_triggers(uid: str, *, db_client: Any) -> Tuple[MemoryItem, ...]:
    """Read the bounded trigger-repair cohort through an authoritative query."""

    collection = db_client.collection(MemoryCollections(uid=uid).memory_items)
    where = getattr(collection, "where", None)
    if not callable(where):
        raise ValueError("standing-trigger reconciliation query is unavailable")
    query = collection
    for field_name, value in (
        ("status", MemoryItemStatus.active.value),
        ("kind", MemoryKind.trigger.value),
        ("write_reason", LedgerWriteReason.standing_trigger.value),
    ):
        try:
            query = query.where(filter=FieldFilter(field_name, "==", value))
        except TypeError:
            query = query.where(field_name, "==", value)
    try:
        snapshots = list(query.limit(MAX_WRITES_PER_DAY + 1).stream())
    except Exception as exc:
        raise ValueError("standing-trigger reconciliation query failed") from exc
    if len(snapshots) > MAX_WRITES_PER_DAY:
        raise ValueError("standing-trigger reconciliation exceeded proof budget")
    items: List[MemoryItem] = []
    for snapshot in snapshots:
        payload = snapshot.to_dict() or {}
        if not isinstance(payload, dict):
            raise ValueError("standing-trigger row is malformed")
        item = MemoryItem.model_validate(payload)
        if (
            item.uid == uid
            and item.status == MemoryItemStatus.active
            and item.kind == MemoryKind.trigger
            and item.write_reason == LedgerWriteReason.standing_trigger
        ):
            items.append(item)
    return tuple(sorted(items, key=lambda item: item.memory_id))


def firestore_daily_sweep_source_provider(
    uid: str,
    local_date: date,
    control: MemoryControlState,
    *,
    db_client: Any,
    timezone_name: str = "UTC",
) -> DailySweepRuntimeSources:
    """Read one bounded backend-produced source packet for the scheduler.

    The document is intentionally a staging/adaptor record, not a second
    memory authority.  Existing daily-summary, onboarding-cold-start, and
    standing-trigger reconciliation producers may write this typed packet;
    canonical memory remains the only durable output authority.
    """

    current_cursor = _read_cursor(db_client, uid, control)

    ref = db_client.document(f"{MemoryCollections(uid=uid).daily_memory_sweep_sources}/{local_date.isoformat()}")
    snapshot = ref.get()
    if not getattr(snapshot, "exists", False):
        # The source is not allowed to advance the cursor merely because the
        # staging document is absent. Fall back only to the durable completed-
        # day summary producer; its missing-summary result remains incomplete.
        summary_sources = produce_completed_day_daily_summary_sources(
            uid,
            local_date,
            timezone_name,
            control,
            db_client=db_client,
        )
        model_authority = daily_memory_sweep_model_authority_from_environment()
        onboarding_production = _produce_onboarding_sources(
            uid,
            db_client=db_client,
            max_candidates=model_authority.max_candidates,
            model_authority=model_authority,
        )
        return DailySweepRuntimeSources.from_iterables(
            daily_summary=summary_sources.daily_summary,
            onboarding_cold_start=onboarding_production.candidates,
            onboarding_source_keys=onboarding_production.source_keys,
            onboarding_source_progress=onboarding_production.source_progress,
            complete=summary_sources.complete and onboarding_production.complete,
            source_status=(
                "incomplete"
                if not (summary_sources.complete and onboarding_production.complete)
                else (
                    "complete" if summary_sources.candidates() or onboarding_production.candidates else "complete_zero"
                )
            ),
            eligibility_proof=summary_sources.eligibility_proof,
            model_cost_usd=summary_sources.model_cost_usd,
        )
    raw_payload = snapshot.to_dict() or {}
    payload: Dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}
    # A staged packet is an immutable producer artifact.  Missing identity is
    # not repaired from scheduler state: accepting it would let a stale packet
    # be restamped into a new account/source generation or timezone window.
    if not payload or payload.get("schema_version") != SCHEMA_VERSION or payload.get("uid") != uid:
        raise ValueError("daily sweep source packet owner mismatch")
    if payload.get("local_date") != local_date.isoformat():
        raise ValueError("daily sweep source packet local date mismatch")
    if payload.get("account_generation") != control.account_generation:
        raise ValueError("daily sweep source packet account generation mismatch")
    if payload.get("source_generation") != control.source_generation:
        raise ValueError("daily sweep source packet source generation mismatch")
    if payload.get("sweep_generation") != current_cursor.sweep_generation:
        raise ValueError("daily sweep source packet sweep generation mismatch")
    raw_timezone_name = payload.get("timezone_name")
    if not isinstance(raw_timezone_name, str) or not raw_timezone_name.strip():
        raise ValueError("daily sweep source packet timezone is required")
    if raw_timezone_name != timezone_name:
        raise ValueError("daily sweep source packet timezone mismatch")
    expected_window = completed_local_day_window(local_date, timezone_name)
    if (
        payload.get("complete") is not True
        or payload.get("window_id") != expected_window.window_id
        or payload.get("window_start_utc") != expected_window.start_utc
        or payload.get("window_end_utc") != expected_window.end_utc
    ):
        raise ValueError("daily sweep source packet is not an exact complete window")

    def parse(
        name: str,
        *,
        source_type: str,
        authority: SweepAuthority,
        trusted_direct: bool = False,
    ) -> Tuple[DailySweepCandidate, ...]:
        raw = payload.get(name, ())
        if not isinstance(raw, (list, tuple)):
            raise ValueError("daily sweep source channel must be a list")
        if len(raw) > MAX_CANDIDATES_PER_DAY:
            raise ValueError("daily sweep source packet exceeds candidate budget")
        return _bounded_candidate_channel(
            raw,
            source_type=source_type,
            authority=authority,
            trusted_direct=trusted_direct,
            max_candidates=MAX_CANDIDATES_PER_DAY,
        )

    trigger_repairs = list(
        parse(
            "existing_trigger_reconciliation",
            source_type="agent_conclusion",
            authority=SweepAuthority.agent_reusable_conclusion,
        )
    )
    # Reconcile only active, already-standing triggers whose strict compiled
    # representation differs from the stored payload. This is repeatable and
    # cannot invent a trigger from passive behavior.
    try:
        for item in _iter_active_standing_triggers(uid, db_client=db_client):
            if (
                item.status != MemoryItemStatus.active
                or item.kind != MemoryKind.trigger
                or item.write_reason != LedgerWriteReason.standing_trigger
                or not item.content
            ):
                continue
            try:
                normalized_condition = compile_trigger_condition(item.trigger_condition).as_condition()
            except Exception:
                continue
            if normalized_condition == item.trigger_condition:
                continue
            trigger_repairs.append(
                DailySweepCandidate(
                    candidate_id=f"trigger-repair-{item.memory_id}",
                    kind="trigger",
                    operation="repair",
                    content=item.content,
                    source_id=f"standing-trigger:{item.memory_id}",
                    source_type="agent_conclusion",
                    source_version="jit-trigger-compile.v1",
                    source_refs=(f"memory:{item.memory_id}",),
                    authority=SweepAuthority.agent_reusable_conclusion,
                    target_memory_id=item.memory_id,
                    slot=item.slot,
                    subject_scope=item.subject_scope,
                    subject_entity_id=item.subject_entity_id,
                    trigger_condition=normalized_condition,
                )
            )
            if len(trigger_repairs) >= MAX_WRITES_PER_DAY:
                break
    except ValueError:
        # Reconciliation is auxiliary, but a truncated authoritative query is
        # not equivalent to an empty set. The source remains unavailable and
        # the scheduler must not advance its cursor.
        raise
    parsed_daily_summary = parse("daily_summary", source_type="daily_summary", authority=SweepAuthority.sweep_inference)
    parsed_onboarding = parse(
        "onboarding_cold_start",
        source_type="onboarding",
        authority=SweepAuthority.direct_user_statement,
        trusted_direct=True,
    )
    raw_onboarding_source_keys = payload.get("onboarding_source_keys", ())
    if not isinstance(raw_onboarding_source_keys, (list, tuple)):
        raise ValueError("daily sweep onboarding source keys must be a list")
    onboarding_source_keys = tuple(
        sorted({item.strip() for item in raw_onboarding_source_keys if isinstance(item, str) and item.strip()})
    )
    if len(onboarding_source_keys) > MAX_CANDIDATES_PER_DAY or any(
        not item.startswith("onboarding:") for item in onboarding_source_keys
    ):
        raise ValueError("daily sweep onboarding source keys are invalid")
    raw_onboarding_progress = payload.get("onboarding_source_progress", {})
    if not isinstance(raw_onboarding_progress, Mapping):
        raise ValueError("daily sweep onboarding source progress is invalid")
    onboarding_source_progress = {
        key.strip(): int(value)
        for key, value in raw_onboarding_progress.items()
        if isinstance(key, str) and key.strip()
    }
    if len(onboarding_source_progress) > MAX_CANDIDATES_PER_DAY or any(
        not key.startswith("onboarding:") or value < 0 for key, value in onboarding_source_progress.items()
    ):
        raise ValueError("daily sweep onboarding source progress is invalid")
    all_candidates = parsed_daily_summary + parsed_onboarding + tuple(trigger_repairs)
    return DailySweepRuntimeSources(
        daily_summary=parsed_daily_summary,
        onboarding_cold_start=parsed_onboarding,
        existing_trigger_reconciliation=tuple(trigger_repairs),
        onboarding_source_keys=onboarding_source_keys,
        onboarding_source_progress=onboarding_source_progress,
        complete=True,
        source_status="complete" if all_candidates else "complete_zero",
    )


def daily_memory_sweep_authority_from_environment() -> SweepAuthorityState:
    """Resolve the backend-only activation seam; both switches default closed."""

    truthy = {"1", "true", "yes", "on"}
    return SweepAuthorityState(
        enabled=os.getenv(DAILY_MEMORY_SWEEP_ENABLED_ENV, "false").casefold() in truthy,
        kill_switch_active=os.getenv(DAILY_MEMORY_SWEEP_KILL_SWITCH_ENV, "false").casefold() in truthy,
    )


@dataclass(frozen=True)
class DailySweepSchedulerSummary:
    """Content-free scheduler receipt for bounded per-user runs."""

    attempted_users: int = 0
    committed_users: int = 0
    blocked_users: int = 0
    committed_candidates: int = 0
    idempotent_candidates: int = 0
    skipped_candidates: int = 0
    errors: Tuple[str, ...] = ()


def _pending_completed_dates(
    cursor: DailySweepCursor,
    *,
    timezone_name: str,
    now: datetime,
    max_days: int = MAX_CATCH_UP_DAYS,
) -> Tuple[date, ...]:
    local_today = now.astimezone(ZoneInfo(timezone_name)).date()
    eligible_through = local_today - timedelta(days=1)
    first_pending = (
        cursor.last_completed_local_date + timedelta(days=1)
        if cursor.last_completed_local_date is not None
        else eligible_through
    )
    if first_pending > eligible_through:
        return ()
    return tuple(
        day for day in (first_pending + timedelta(days=index) for index in range(max_days)) if day <= eligible_through
    )


def run_daily_memory_sweep_scheduler(
    *,
    db_client: Any,
    now: datetime,
    uid_inventory: Iterable[str],
    source_provider: Any,
    timezone_resolver: Any,
    authority: Optional[SweepAuthorityState] = None,
    cohort_authority: Optional[DailySweepCohortAuthority] = None,
    cohort_authorizer: Optional[Any] = None,
    max_users: int = 400,
) -> DailySweepSchedulerSummary:
    """Runtime producer/scheduler/adaptor behind the closed backend authority.

    The caller supplies a bounded registry page and a server-only
    ``source_provider(uid, completed_local_date, control)``.  The provider is
    where daily-summary extraction, onboarding cold-start, and existing-trigger
    reconciliation are joined; clients and passive observation streams never
    call this function.  No current writer is changed while the environment
    authority remains closed.
    """

    resolved_authority = authority or daily_memory_sweep_authority_from_environment()
    if not resolved_authority.may_write:
        return DailySweepSchedulerSummary()
    resolved_cohort = cohort_authority or daily_memory_sweep_cohort_authority_from_environment()
    if resolved_cohort.enabled and not resolved_cohort.cohort_name:
        return DailySweepSchedulerSummary(errors=("cohort_name_missing",))
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    bounded_uids = tuple(sorted({uid.strip() for uid in uid_inventory if uid.strip()}))[: max(1, min(400, max_users))]
    attempted = committed_users = blocked_users = 0
    committed = idempotent = skipped = 0
    errors: List[str] = []
    for uid in bounded_uids:
        attempted += 1
        try:
            if resolved_cohort.enabled:
                # This callback is intentionally read-only.  A PostHog client
                # can be supplied by the maintenance deployment, but no
                # identify/flag mutation is performed by this scheduler.
                if not callable(cohort_authorizer):
                    blocked_users += 1
                    continue
                try:
                    enrolled = cohort_authorizer(uid, resolved_cohort.cohort_name)
                except TypeError:
                    enrolled = cohort_authorizer(uid)
                if not bool(enrolled):
                    blocked_users += 1
                    continue
            control = ensure_canonical_apply_control_state(uid, db_client=db_client)
            timezone_name = str(timezone_resolver(uid) or "UTC")
            cursor = _read_cursor(db_client, uid, control)
            if cursor.last_completed_local_date is not None and cursor.timezone_name != timezone_name:
                raise ValueError("timezone_changed_requires_reconciliation")
            pending_dates = _pending_completed_dates(cursor, timezone_name=timezone_name, now=now)
            if not pending_dates:
                continue
            packets: Dict[date, DailySweepInput] = {}
            for local_date in pending_dates:
                try:
                    sources = source_provider(uid, local_date, control, timezone_name=timezone_name)
                except TypeError:
                    # Preserve the narrow three-argument provider contract for
                    # existing test/deployment adapters.
                    sources = source_provider(uid, local_date, control)
                if not isinstance(sources, DailySweepRuntimeSources):
                    raise ValueError("daily sweep source provider returned an invalid source bundle")
                packets[local_date] = build_daily_sweep_input(
                    uid,
                    local_date,
                    account_generation=control.account_generation,
                    source_generation=control.source_generation,
                    sweep_generation=cursor.sweep_generation,
                    timezone_name=timezone_name,
                    sources=sources,
                )
            output = run_daily_memory_sweep(
                uid,
                timezone_name,
                now,
                packets,
                db_client=db_client,
                authority=resolved_authority,
                claimant=f"scheduler:{uuid4().hex}",
            )
            committed += output.committed_count
            idempotent += output.idempotent_count
            skipped += output.skipped_count
            if output.status == "committed":
                committed_users += 1
            else:
                blocked_users += 1
                errors.append(f"uid={uid}:{output.blocked_reason or output.status}")
        except Exception as exc:
            blocked_users += 1
            errors.append(f"uid={uid}:{type(exc).__name__}")
    return DailySweepSchedulerSummary(
        attempted_users=attempted,
        committed_users=committed_users,
        blocked_users=blocked_users,
        committed_candidates=committed,
        idempotent_candidates=idempotent,
        skipped_candidates=skipped,
        errors=tuple(errors[:16]),
    )


__all__ = [
    "CURSOR_SCHEMA_VERSION",
    "DailySweepCandidate",
    "DailySweepInput",
    "DailySweepOutput",
    "DailySweepPlan",
    "DailySweepRuntimeSources",
    "DailySweepSchedulerSummary",
    "CompletedLocalDayWindow",
    "DailySweepSkip",
    "MAX_CANDIDATES_PER_DAY",
    "MAX_CATCH_UP_DAYS",
    "MAX_WRITES_PER_DAY",
    "MAX_COMPLETED_DAY_CONVERSATIONS",
    "MAX_COMPLETED_DAY_INPUT_CHARACTERS",
    "MAX_ONBOARDING_CONVERSATIONS",
    "DAILY_MEMORY_SWEEP_ENABLED_ENV",
    "DAILY_MEMORY_SWEEP_KILL_SWITCH_ENV",
    "DAILY_MEMORY_SWEEP_MODEL_ENABLED_ENV",
    "DAILY_MEMORY_SWEEP_MODEL_NAME_ENV",
    "DAILY_MEMORY_SWEEP_MAX_MODEL_CANDIDATES_ENV",
    "DAILY_MEMORY_SWEEP_MAX_MODEL_COST_USD_ENV",
    "DAILY_MEMORY_SWEEP_COHORT_ENABLED_ENV",
    "DAILY_MEMORY_SWEEP_COHORT_NAME_ENV",
    "DAILY_MEMORY_SWEEP_COHORT_FLAG_ENV",
    "DAILY_MEMORY_SWEEP_TIMEZONE_RECONCILIATION_ENV",
    "SCHEMA_VERSION",
    "SweepAuthority",
    "SweepAuthorityState",
    "DailySweepModelAuthority",
    "DailySweepCohortAuthority",
    "daily_memory_sweep_model_authority_from_environment",
    "daily_memory_sweep_cohort_authority_from_environment",
    "read_daily_memory_sweep_cohort_assignment",
    "plan_daily_memory_sweep",
    "build_daily_sweep_input",
    "produce_completed_day_daily_summary_sources",
    "produce_onboarding_seed_sources",
    "completed_local_day_window",
    "reconcile_daily_memory_sweep_timezone",
    "reconcile_daily_memory_sweep_timezones_for_maintenance",
    "daily_memory_sweep_authority_from_environment",
    "firestore_daily_sweep_source_provider",
    "run_daily_memory_sweep_scheduler",
    "run_daily_memory_sweep",
]
