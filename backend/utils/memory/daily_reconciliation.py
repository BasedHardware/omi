"""Bounded, review-only daily reconciliation planning.

Daily summary generation is an existing once-per-user-local-day seam, but its
LLM output is not a memory write authority.  This module accepts only explicit
reconciliation candidates, validates them, and returns passive review
proposals.  It deliberately has no database, model, or ledger-write calls.
"""

from __future__ import annotations

from datetime import date
from itertools import islice
import re
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from models.memory_contracts import deterministic_contract_id
from utils.memory.jit_trigger_contract import TriggerCondition

SCHEMA_VERSION = "daily_memory_reconciliation.v1"
MAX_CANDIDATES = 32
MAX_EVIDENCE_IDS = 16
MAX_SOURCE_REFS = 16
MAX_CONTENT_CHARS = 1_200
MAX_TRIGGER_CONDITION_KEYS = 16
MAX_TRIGGER_VALUE_CHARS = 300

_ID_RE = re.compile(r"[a-z0-9][a-z0-9._:-]{0,127}")


class ReconciliationCandidate(BaseModel):
    """An explicit candidate supplied by a daily-summary producer.

    Candidate data is untrusted planning input.  A candidate never carries
    server-owned patch IDs and cannot directly mutate a canonical row.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: Optional[str] = None
    kind: Literal["fact", "trigger"]
    operation: Literal["add", "amend", "add_evidence", "repair"]
    content: str
    evidence_ids: Tuple[str, ...] = ()
    source_refs: Tuple[str, ...] = ()
    target_memory_id: Optional[str] = None
    subject_entity_id: Optional[str] = None
    trigger_condition: Dict[str, Any] = Field(default_factory=dict)
    target_is_direct_user_asserted: bool = False

    @field_validator("candidate_id", "target_memory_id", "subject_entity_id")
    @classmethod
    def validate_optional_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized or not _ID_RE.fullmatch(normalized.casefold()):
            raise ValueError("identifiers must be canonical bounded ids")
        return normalized

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        normalized = " ".join((value or "").split())
        if not normalized:
            raise ValueError("candidate content is required")
        if len(normalized) > MAX_CONTENT_CHARS:
            raise ValueError("candidate content exceeds the reconciliation limit")
        return normalized

    @field_validator("evidence_ids", "source_refs")
    @classmethod
    def validate_refs(cls, value: Tuple[str, ...], info) -> Tuple[str, ...]:
        limit = MAX_EVIDENCE_IDS if info.field_name == "evidence_ids" else MAX_SOURCE_REFS
        normalized = tuple(sorted({ref.strip() for ref in value if ref and ref.strip()}))
        if len(normalized) > limit:
            raise ValueError(f"{info.field_name} exceeds the reconciliation limit")
        if any(len(ref) > 256 for ref in normalized):
            raise ValueError(f"{info.field_name} contains an oversized reference")
        return normalized

    @field_validator("trigger_condition")
    @classmethod
    def validate_trigger_condition(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        if not value:
            return {}
        return TriggerCondition.model_validate(value).model_dump(mode="json", by_alias=True)

    @model_validator(mode="after")
    def validate_operation(self):
        if self.operation in {"amend", "add_evidence", "repair"} and not self.target_memory_id:
            raise ValueError("repair operations require target_memory_id")
        if self.kind == "trigger" and not self.trigger_condition:
            raise ValueError("trigger candidates require trigger_condition")
        if self.kind == "fact" and self.trigger_condition:
            raise ValueError("fact candidates must not define trigger_condition")
        if len(self.trigger_condition) > MAX_TRIGGER_CONDITION_KEYS:
            raise ValueError("trigger_condition exceeds the reconciliation limit")
        for key, value in self.trigger_condition.items():
            if not key.strip() or len(key) > 64:
                raise ValueError("trigger_condition keys must be bounded strings")
            if isinstance(value, str) and len(value) > MAX_TRIGGER_VALUE_CHARS:
                raise ValueError("trigger_condition values are too large")
        return self


class ReconciliationProposal(BaseModel):
    """A passive proposal; every proposal requires later review and apply."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    proposal_id: str
    idempotency_key: str
    sweep_date: date
    kind: Literal["fact", "trigger"]
    operation: Literal["add", "amend", "add_evidence", "repair"]
    write_reason: Literal["daily_reconciliation"] = "daily_reconciliation"
    status: Literal["review"] = "review"
    requires_review: bool = True
    memory_text: str
    evidence_ids: Tuple[str, ...]
    source_refs: Tuple[str, ...] = ()
    target_memory_id: Optional[str] = None
    subject_entity_id: Optional[str] = None
    trigger_condition: Dict[str, Any] = Field(default_factory=dict)
    reason_code: Literal["new_candidate", "repair_candidate", "direct_user_statement_conflict"]


class ReconciliationSkip(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: Optional[str] = None
    reason_code: Literal[
        "invalid_candidate",
        "missing_evidence",
        "duplicate_candidate",
        "direct_user_statement_conflict",
    ]


class DailyReconciliationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION
    uid: str
    sweep_date: date
    sweep_idempotency_key: str
    status: Literal["planned", "already_swept", "blocked"]
    input_count: int = 0
    proposals: Tuple[ReconciliationProposal, ...] = ()
    skipped: Tuple[ReconciliationSkip, ...] = ()
    missed_days_ignored: int = 0
    blocked_reason: Optional[Literal["input_window_exceeded", "already_swept"]] = None


def _parse_date(value: date | str) -> date:
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("sweep_date must be YYYY-MM-DD") from exc
    return value


def _candidate_identity(candidate: ReconciliationCandidate) -> str:
    payload = {
        "candidate_id": candidate.candidate_id,
        "kind": candidate.kind,
        "operation": candidate.operation,
        "content": candidate.content,
        "evidence_ids": list(candidate.evidence_ids),
        "source_refs": list(candidate.source_refs),
        "target_memory_id": candidate.target_memory_id,
        "subject_entity_id": candidate.subject_entity_id,
        "trigger_condition": candidate.trigger_condition,
    }
    return deterministic_contract_id("daily-reconciliation-candidate", payload)


def _sweep_key(uid: str, sweep_date: date) -> str:
    return "daily-reconciliation:" + deterministic_contract_id(
        "daily-reconciliation-sweep", {"uid": uid, "sweep_date": sweep_date.isoformat()}
    )


def _invalid_skip(raw: Any) -> ReconciliationSkip:
    candidate_id = raw.get("candidate_id") if isinstance(raw, dict) else None
    return ReconciliationSkip(
        candidate_id=candidate_id if isinstance(candidate_id, str) else None,
        reason_code="invalid_candidate",
    )


def plan_daily_reconciliation(
    uid: str,
    sweep_date: date | str,
    candidates: Iterable[ReconciliationCandidate | Dict[str, Any]],
    *,
    last_swept_date: date | str | None = None,
) -> DailyReconciliationPlan:
    """Return at most one bounded current-day review plan.

    A missed prior day is recorded but never replayed.  This function only
    validates and plans; callers must route proposals through canonical apply
    after a separate review action.
    """

    normalized_uid = (uid or "").strip()
    if not normalized_uid:
        raise ValueError("uid is required")
    current_date = _parse_date(sweep_date)
    prior_date = _parse_date(last_swept_date) if last_swept_date is not None else None
    if prior_date is not None and prior_date > current_date:
        raise ValueError("last_swept_date cannot be after sweep_date")

    # Consume only one item past the admitted window. This keeps a hostile or
    # accidental unbounded iterator from exhausting memory before we fail
    # closed on input size.
    raw_candidates = list(islice(iter(candidates), MAX_CANDIDATES + 1))
    sweep_key = _sweep_key(normalized_uid, current_date)
    if prior_date == current_date:
        return DailyReconciliationPlan(
            uid=normalized_uid,
            sweep_date=current_date,
            sweep_idempotency_key=sweep_key,
            status="already_swept",
            input_count=0,
            blocked_reason="already_swept",
        )
    if len(raw_candidates) > MAX_CANDIDATES:
        return DailyReconciliationPlan(
            uid=normalized_uid,
            sweep_date=current_date,
            sweep_idempotency_key=sweep_key,
            status="blocked",
            input_count=len(raw_candidates),
            blocked_reason="input_window_exceeded",
            missed_days_ignored=max((current_date - prior_date).days - 1, 0) if prior_date else 0,
        )

    proposals: List[ReconciliationProposal] = []
    skipped: List[ReconciliationSkip] = []
    seen: set[str] = set()
    for raw in raw_candidates:
        try:
            candidate = raw if isinstance(raw, ReconciliationCandidate) else ReconciliationCandidate.model_validate(raw)
        except Exception:
            skipped.append(_invalid_skip(raw))
            continue
        identity = _candidate_identity(candidate)
        if identity in seen:
            skipped.append(ReconciliationSkip(candidate_id=candidate.candidate_id, reason_code="duplicate_candidate"))
            continue
        seen.add(identity)
        if not candidate.evidence_ids:
            skipped.append(ReconciliationSkip(candidate_id=candidate.candidate_id, reason_code="missing_evidence"))
            continue
        reason_code: Literal["new_candidate", "repair_candidate", "direct_user_statement_conflict"]
        if candidate.target_is_direct_user_asserted:
            # Never silently rewrite a direct user statement.  Keep the
            # proposal passive and make the conflict explicit for review.
            reason_code = "direct_user_statement_conflict"
        elif candidate.operation == "add":
            reason_code = "new_candidate"
        else:
            reason_code = "repair_candidate"
        proposal_id = (
            "recon_"
            + deterministic_contract_id(
                "daily-reconciliation-proposal",
                {"sweep": sweep_key, "candidate": identity},
            )[:32]
        )
        proposals.append(
            ReconciliationProposal(
                proposal_id=proposal_id,
                idempotency_key=f"{sweep_key}:{identity}",
                sweep_date=current_date,
                kind=candidate.kind,
                operation=candidate.operation,
                memory_text=candidate.content,
                evidence_ids=candidate.evidence_ids,
                source_refs=candidate.source_refs,
                target_memory_id=candidate.target_memory_id,
                subject_entity_id=candidate.subject_entity_id,
                trigger_condition=candidate.trigger_condition,
                reason_code=reason_code,
            )
        )

    proposals.sort(key=lambda proposal: proposal.proposal_id)
    skipped.sort(key=lambda item: (item.reason_code, item.candidate_id or ""))
    return DailyReconciliationPlan(
        uid=normalized_uid,
        sweep_date=current_date,
        sweep_idempotency_key=sweep_key,
        status="planned",
        input_count=len(raw_candidates),
        proposals=tuple(proposals),
        skipped=tuple(skipped),
        missed_days_ignored=max((current_date - prior_date).days - 1, 0) if prior_date else 0,
    )


__all__ = [
    "DailyReconciliationPlan",
    "MAX_CANDIDATES",
    "MAX_CONTENT_CHARS",
    "MAX_EVIDENCE_IDS",
    "MAX_SOURCE_REFS",
    "MAX_TRIGGER_CONDITION_KEYS",
    "ReconciliationCandidate",
    "ReconciliationProposal",
    "ReconciliationSkip",
    "SCHEMA_VERSION",
    "plan_daily_reconciliation",
]
