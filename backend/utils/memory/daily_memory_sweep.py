"""Dark, bounded once-per-local-day automatic memory sweep.

This module is an authority seam, not a scheduler.  It accepts a server-built
daily input, writes through the canonical ledger boundary, and stays completely
inert until an explicit backend authority opens it.  The current daily-summary
producer is intentionally unchanged; a later integration may adapt its
structured output to :class:`DailySweepInput`.

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
from dataclasses import dataclass
import os
import re
from typing import Any, Dict, Iterable, List, Literal, Mapping, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from google.cloud import firestore
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status
from database.account_deletion_projection_fence import read_account_deletion_projection_fence
from database.memory_collections import MemoryCollections
from models.memory_apply import MemoryControlState
from models.memory_contracts import deterministic_contract_id
from models.product_memory import (
    LedgerWriteReason,
    MemoryItem,
    MemoryItemStatus,
    MemoryKind,
    MemorySubjectScope,
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
from utils.memory.product_memory_read_service import iter_authoritative_product_memory_items

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


class SweepFenceBlocked(RuntimeError):
    """A durable deletion or generation fence closed during a transaction."""


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
        if self.authority == SweepAuthority.direct_user_statement and self.source_type != "explicit_user_statement":
            raise ValueError("direct authority requires an explicit-user-statement source")
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
    timezone_name: Optional[str] = None
    candidates: Tuple[DailySweepCandidate, ...] = ()

    @field_validator("uid")
    @classmethod
    def validate_uid(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("uid is required")
        return normalized

    @field_validator("account_generation", "source_generation")
    @classmethod
    def validate_generations(cls, value: int) -> int:
        if value < 0:
            raise ValueError("generation must be nonnegative")
        return value

    @field_validator("candidates")
    @classmethod
    def validate_candidate_count(cls, value: Tuple[DailySweepCandidate, ...]) -> Tuple[DailySweepCandidate, ...]:
        if len(value) > MAX_CANDIDATES_PER_DAY:
            raise ValueError("daily sweep candidate window exceeded")
        return value

    @model_validator(mode="after")
    def validate_schema(self) -> "DailySweepInput":
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported daily sweep input schema")
        if self.timezone_name is not None:
            try:
                ZoneInfo(self.timezone_name)
            except ZoneInfoNotFoundError as exc:
                raise ValueError("input timezone must be an installed IANA timezone") from exc
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


def _receipt_id(uid: str, local_date: date, candidate: DailySweepCandidate) -> str:
    return (
        "receipt_"
        + deterministic_contract_id(
            "daily-memory-sweep-receipt",
            {"uid": uid, "local_date": local_date.isoformat(), "source_key": candidate.source_key},
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
    if (
        cursor.uid != uid
        or cursor.account_generation != control.account_generation
        or cursor.source_generation != control.source_generation
    ):
        raise RuntimeError("daily sweep cursor owner or generation mismatch")
    return cursor


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
) -> Literal["claimed", "idempotent", "conflict"]:
    receipt_ref = _receipt_ref(db_client, uid, _receipt_id(uid, local_date, candidate))
    digest = candidate.digest()

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
            ):
                return "conflict"
            if existing.get("receipt_state") == "committed":
                return "idempotent"
            prior_claimant = existing.get("claimant")
            if prior_claimant and prior_claimant != claimant:
                return "conflict"
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
                "claimant": claimant,
                "receipt_state": "pending",
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
) -> None:
    receipt_ref = _receipt_ref(db_client, uid, _receipt_id(uid, local_date, candidate))

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
            or existing.get("claimant") not in {None, claimant}
        ):
            raise RuntimeError("daily sweep receipt changed while completing")
        payload: Dict[str, Any] = {
            "schema_version": RECEIPT_SCHEMA_VERSION,
            "receipt_state": "committed",
            "source_generation": source_generation,
            "claimant": claimant,
            "outcome": outcome,
            "completed_at": datetime.now(timezone.utc),
        }
        if memory_id:
            payload["memory_id"] = memory_id
        if skip_reason:
            payload["skip_reason"] = skip_reason
        transaction.set(receipt_ref, payload, merge=True)

    transaction = db_client.transaction()
    firestore.transactional(finish)(transaction)


def _target_for_candidate(uid: str, candidate: DailySweepCandidate, *, db_client: Any) -> Optional[MemoryItem]:
    if not candidate.target_memory_id:
        return None
    return read_canonical_memory_item(uid, candidate.target_memory_id, db_client=db_client)


def _target_authority(item: MemoryItem) -> int:
    reason = item.write_reason
    if reason == LedgerWriteReason.direct_user_statement:
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
    """Find one deterministic active canonical occupant for add candidates.

    The read is bounded and only used to prevent cross-day duplicate profile
    slots.  A minimal fake without a collection stream is treated as an empty
    store for backwards-compatible unit seams; production canonical reads are
    authoritative and validated by ``MemoryItem``.
    """

    if candidate.kind != "fact":
        return None
    try:
        items: List[MemoryItem] = []
        for index, item in enumerate(iter_authoritative_product_memory_items(uid, db_client=db_client)):
            if index >= 128:
                break
            if item.status != MemoryItemStatus.active or item.kind != MemoryKind.fact:
                continue
            if item.subject_scope != candidate.subject_scope or item.subject_entity_id != candidate.subject_entity_id:
                continue
            if candidate.slot and item.slot == candidate.slot:
                items.append(item)
            elif not candidate.slot and (item.content or "").casefold() == candidate.content.casefold():
                items.append(item)
        return sorted(items, key=lambda item: item.memory_id)[0] if items else None
    except (AttributeError, TypeError):
        return None


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
    reason = LedgerWriteReason.standing_trigger if candidate.kind == "trigger" else candidate.authority.ledger_reason
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
    if first_pending > eligible_through:
        return _blocked_output(normalized_uid, "no_completed_local_day", status="not_due")
    dates = [first_pending + timedelta(days=index) for index in range(max_catch_up_days)]
    dates = [item for item in dates if item <= eligible_through]

    completed: List[date] = []
    committed_count = 0
    idempotent_count = 0
    skipped_count = 0
    current_cursor = cursor
    receipt_claimant = claimant or _plan_id(normalized_uid, eligible_through)
    for local_date in dates:
        packet = inputs_by_date.get(local_date)
        if packet is None:
            return _blocked_output(normalized_uid, f"missing_input:{local_date.isoformat()}")
        if packet.local_date != local_date:
            return _blocked_output(normalized_uid, "input_date_mismatch")
        if (
            packet.account_generation != control.account_generation
            or packet.source_generation != control.source_generation
        ):
            return _blocked_output(normalized_uid, "input_generation_mismatch")
        if packet.timezone_name is not None and packet.timezone_name != timezone_name:
            return _blocked_output(normalized_uid, "input_timezone_mismatch")
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
            )
            if claim == "conflict":
                return _blocked_output(normalized_uid, "source_idempotency_conflict")
            if claim == "idempotent":
                idempotent_count += 1
                continue
            memory_id, skip_reason = _apply_candidate(
                normalized_uid,
                local_date,
                candidate,
                db_client=db_client,
            )
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
                )
            except SweepFenceBlocked:
                return _blocked_output(normalized_uid, "receipt_completion_fence_closed")
            committed_count += 1
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

    @classmethod
    def from_iterables(
        cls,
        *,
        daily_summary: Iterable[DailySweepCandidate] = (),
        onboarding_cold_start: Iterable[DailySweepCandidate] = (),
        existing_trigger_reconciliation: Iterable[DailySweepCandidate] = (),
    ) -> "DailySweepRuntimeSources":
        return cls(
            daily_summary=tuple(daily_summary),
            onboarding_cold_start=tuple(onboarding_cold_start),
            existing_trigger_reconciliation=tuple(existing_trigger_reconciliation),
        )

    def candidates(self) -> Tuple[DailySweepCandidate, ...]:
        return self.daily_summary + self.onboarding_cold_start + self.existing_trigger_reconciliation


def build_daily_sweep_input(
    uid: str,
    local_date: date,
    *,
    account_generation: int,
    source_generation: int,
    timezone_name: str,
    sources: DailySweepRuntimeSources,
) -> DailySweepInput:
    """Adapt typed daily-summary/onboarding/trigger sources into one packet."""

    return DailySweepInput(
        uid=uid,
        local_date=local_date,
        account_generation=account_generation,
        source_generation=source_generation,
        timezone_name=timezone_name,
        candidates=sources.candidates(),
    )


def firestore_daily_sweep_source_provider(
    uid: str, local_date: date, control: MemoryControlState, *, db_client: Any
) -> DailySweepRuntimeSources:
    """Read one bounded backend-produced source packet for the scheduler.

    The document is intentionally a staging/adaptor record, not a second
    memory authority.  Existing daily-summary, onboarding-cold-start, and
    standing-trigger reconciliation producers may write this typed packet;
    canonical memory remains the only durable output authority.
    """

    ref = db_client.document(f"{MemoryCollections(uid=uid).daily_memory_sweep_sources}/{local_date.isoformat()}")
    snapshot = ref.get()
    if not getattr(snapshot, "exists", False):
        return DailySweepRuntimeSources()
    payload = snapshot.to_dict() or {}
    if not isinstance(payload, dict) or payload.get("uid") not in {None, uid}:
        raise ValueError("daily sweep source packet owner mismatch")
    if payload.get("account_generation", control.account_generation) != control.account_generation:
        raise ValueError("daily sweep source packet account generation mismatch")
    if payload.get("source_generation", control.source_generation) != control.source_generation:
        raise ValueError("daily sweep source packet source generation mismatch")

    def parse(name: str) -> Tuple[DailySweepCandidate, ...]:
        raw = payload.get(name, ())
        if not isinstance(raw, (list, tuple)):
            raise ValueError("daily sweep source channel must be a list")
        if len(raw) > MAX_CANDIDATES_PER_DAY:
            raise ValueError("daily sweep source packet exceeds candidate budget")
        return tuple(
            item if isinstance(item, DailySweepCandidate) else DailySweepCandidate.model_validate(item) for item in raw
        )

    trigger_repairs = list(parse("existing_trigger_reconciliation"))
    # Reconcile only active, already-standing triggers whose strict compiled
    # representation differs from the stored payload. This is repeatable and
    # cannot invent a trigger from passive behavior.
    try:
        for index, item in enumerate(iter_authoritative_product_memory_items(uid, db_client=db_client)):
            if index >= 128:
                break
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
    except (AttributeError, TypeError, ValueError):
        # A missing collection seam is equivalent to no reconciliation input;
        # malformed canonical rows are handled by the canonical read boundary.
        pass
    return DailySweepRuntimeSources(
        daily_summary=parse("daily_summary"),
        onboarding_cold_start=parse("onboarding_cold_start"),
        existing_trigger_reconciliation=tuple(trigger_repairs),
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


def run_daily_memory_sweep_scheduler(
    *,
    db_client: Any,
    now: datetime,
    uid_inventory: Iterable[str],
    source_provider: Any,
    timezone_resolver: Any,
    authority: Optional[SweepAuthorityState] = None,
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
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    bounded_uids = tuple(sorted({uid.strip() for uid in uid_inventory if uid.strip()}))[: max(1, min(400, max_users))]
    attempted = committed_users = blocked_users = 0
    committed = idempotent = skipped = 0
    errors: List[str] = []
    for uid in bounded_uids:
        attempted += 1
        try:
            control = ensure_canonical_apply_control_state(uid, db_client=db_client)
            timezone_name = str(timezone_resolver(uid) or "UTC")
            local_date = now.astimezone(ZoneInfo(timezone_name)).date() - timedelta(days=1)
            sources = source_provider(uid, local_date, control)
            if not isinstance(sources, DailySweepRuntimeSources):
                raise ValueError("daily sweep source provider returned an invalid source bundle")
            packet = build_daily_sweep_input(
                uid,
                local_date,
                account_generation=control.account_generation,
                source_generation=control.source_generation,
                timezone_name=timezone_name,
                sources=sources,
            )
            output = run_daily_memory_sweep(
                uid,
                timezone_name,
                now,
                {local_date: packet},
                db_client=db_client,
                authority=resolved_authority,
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
    "DAILY_MEMORY_SWEEP_ENABLED_ENV",
    "DAILY_MEMORY_SWEEP_KILL_SWITCH_ENV",
    "SCHEMA_VERSION",
    "SweepAuthority",
    "SweepAuthorityState",
    "plan_daily_memory_sweep",
    "build_daily_sweep_input",
    "completed_local_day_window",
    "daily_memory_sweep_authority_from_environment",
    "firestore_daily_sweep_source_provider",
    "run_daily_memory_sweep_scheduler",
    "run_daily_memory_sweep",
]
