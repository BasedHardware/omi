"""Fail-closed search contract for ``knowledge_ledger.v1`` rows.

The ledger has two deliberately different retrieval surfaces:

* ``current`` searches open, intent-backed rows only.  Unslotted facts are
  searchable, but they are not profile inputs; documents expose their compact
  handle and triggers expose their description, never their private payload.
* ``history`` is an explicit, fact-only surface for closed rows and preserved
  generated legacy data.  Rejected rows are audit-only and must be requested
  explicitly.

This module is pure so the canonical reader, keyword projection, and vector
projection can share the same lifecycle and privacy gates.  Provider hits are
always candidates: callers still hydrate the authoritative row before
returning content.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Collection, FrozenSet, Mapping, Optional

from models.memory_evidence import SourceState
from models.product_memory import (
    RESTRICTED_SENSITIVITY_LABELS,
    LedgerWriteReason,
    MemoryItemStatus,
    MemoryKind,
    ProcessingState,
)

LEDGER_INDEX_VERSION = 1
LEDGER_SEARCH_KINDS: FrozenSet[str] = frozenset(kind.value for kind in MemoryKind)


class LedgerSearchSurface(str, Enum):
    current = "current"
    history = "history"


class LedgerRowIndexState(str, Enum):
    not_ledger = "not_ledger"
    open = "open"
    closed = "closed"


def _value(row: Any, name: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(name, default)
    return getattr(row, name, default)


def ledger_kind_value(row: Any) -> str:
    value = _value(row, "kind", "")
    return value.value if isinstance(value, MemoryKind) else str(value or "")


def ledger_schema_is_current(row: Any) -> bool:
    return _value(row, "ledger_schema_version") == "knowledge_ledger.v1"


def ledger_row_is_locked(row: Any) -> bool:
    if _value(row, "is_locked") is True:
        return True
    promotion = _value(row, "promotion") or {}
    return isinstance(promotion, Mapping) and promotion.get("is_locked") is True


def ledger_row_is_rejected(row: Any) -> bool:
    if _value(row, "user_review") is False:
        return True
    promotion = _value(row, "promotion") or {}
    return isinstance(promotion, Mapping) and promotion.get("user_review") is False


def ledger_row_has_restricted_sensitivity(row: Any) -> bool:
    labels = _value(row, "sensitivity_labels") or []
    return bool(set(labels).intersection(RESTRICTED_SENSITIVITY_LABELS))


def ledger_row_source_is_readable(row: Any) -> bool:
    source_state = _value(row, "source_state")
    if source_state in {SourceState.tombstoned, SourceState.purged, "tombstoned", "purged"}:
        return False
    # A generated MemoryItem that claims an active source must carry active
    # evidence unless it is a direct user assertion.  MemoryDB compatibility
    # rows do not carry evidence, so the absence of this field is permitted.
    evidence = _value(row, "evidence")
    if (
        source_state in {SourceState.active, "active"}
        and isinstance(evidence, list)
        and not _value(row, "user_asserted")
    ):
        return any(_value(entry, "source_state") in {SourceState.active, "active"} for entry in evidence)
    return True


def _is_active_status(row: Any) -> bool:
    status = _value(row, "status")
    if status is None:
        # MemoryDB is a compatibility projection.  Its lifecycle is carried by
        # invalid_at/superseded_by and is checked below.
        return _value(row, "invalid_at") is None and not _value(row, "superseded_by")
    return status in {MemoryItemStatus.active, MemoryItemStatus.active.value}


def _is_closed_status(row: Any) -> bool:
    status = _value(row, "status")
    return (
        status in {MemoryItemStatus.superseded, MemoryItemStatus.superseded.value}
        or _value(row, "invalid_at") is not None
        or _value(row, "valid_to") is not None
        or bool(_value(row, "superseded_by"))
    )


def _is_processed(row: Any) -> bool:
    state = _value(row, "processing_state")
    return state is None or state in {ProcessingState.processed, ProcessingState.processed.value}


def _is_hidden_or_tombstoned(row: Any) -> bool:
    status = _value(row, "status")
    return status in {
        MemoryItemStatus.hidden,
        MemoryItemStatus.hidden.value,
        MemoryItemStatus.tombstoned,
        MemoryItemStatus.tombstoned.value,
    }


def _is_legacy_migrated(row: Any) -> bool:
    reason = _value(row, "write_reason")
    reason_value = reason.value if isinstance(reason, LedgerWriteReason) else str(reason or "")
    return _value(row, "intent_backed") is not True and reason_value == LedgerWriteReason.legacy_migration.value


def is_ledger_row_admissible(
    row: Any,
    *,
    uid: Optional[str],
    surface: LedgerSearchSurface,
    kinds: Collection[str] = LEDGER_SEARCH_KINDS,
    include_rejected: bool = False,
) -> bool:
    """Return whether one authoritative row may enter a ledger search.

    The owner check is intentionally mandatory.  A missing owner, unknown
    schema/kind, malformed lifecycle, locked/restricted source, or rejected
    row on the default surface fails closed rather than being treated as a
    permissive compatibility case.
    """

    if not uid or _value(row, "uid") != uid:
        return False
    if not ledger_schema_is_current(row) or ledger_kind_value(row) not in set(kinds):
        return False
    if not (_value(row, "content") or "").strip():
        return False
    if ledger_row_is_locked(row) or ledger_row_has_restricted_sensitivity(row):
        return False
    if not ledger_row_source_is_readable(row) or not _is_processed(row) or _is_hidden_or_tombstoned(row):
        return False
    if surface is LedgerSearchSurface.current:
        if _value(row, "intent_backed") is not True or not _is_active_status(row):
            return False
        if _value(row, "valid_to") is not None or _value(row, "invalid_at") is not None:
            return False
        if _value(row, "superseded_by"):
            return False
        if ledger_row_is_rejected(row):
            return False
        # Playbook bodies are private progressive-disclosure data and are only
        # ever searchable for primary-user documents.  Facts may retain their
        # own subject scope; profile rendering applies the stricter primary
        # user scope separately.
        subject_scope = _value(row, "subject_scope")
        subject_scope_value = subject_scope.value if hasattr(subject_scope, "value") else subject_scope
        if ledger_kind_value(row) == MemoryKind.document.value and subject_scope_value != "primary_user":
            return False
        return True

    # History is intentionally narrower than the current surface: only facts
    # have a public historical wire representation today.  Preserved legacy
    # generated rows remain available as labelled history, but arbitrary
    # passive rows do not become searchable by accident.
    if ledger_kind_value(row) != MemoryKind.fact.value:
        return False
    if not (_value(row, "intent_backed") is True or _is_legacy_migrated(row)):
        return False
    if not include_rejected and ledger_row_is_rejected(row):
        return False
    return _is_legacy_migrated(row) or ledger_row_is_rejected(row) or _is_closed_status(row)


def ledger_row_index_state(row: Any) -> LedgerRowIndexState:
    """Classify metadata written to keyword/vector projections."""

    if not ledger_schema_is_current(row) or ledger_kind_value(row) not in LEDGER_SEARCH_KINDS:
        return LedgerRowIndexState.not_ledger
    return (
        LedgerRowIndexState.open
        if is_ledger_row_admissible(row, uid=_value(row, "uid"), surface=LedgerSearchSurface.current)
        else LedgerRowIndexState.closed
    )


def build_ledger_index_metadata(row: Any) -> dict[str, Any]:
    """Return non-content metadata shared by keyword and vector projections."""

    if not ledger_schema_is_current(row) or ledger_kind_value(row) not in LEDGER_SEARCH_KINDS:
        return {}
    slot = _value(row, "slot")
    subject_scope = _value(row, "subject_scope")
    return {
        "ledger_index_version": LEDGER_INDEX_VERSION,
        "ledger_schema_version": "knowledge_ledger.v1",
        "ledger_kind": ledger_kind_value(row),
        "ledger_row_state": ledger_row_index_state(row).value,
        "ledger_has_slot": bool(isinstance(slot, str) and slot.strip()),
        "ledger_subject_scope": subject_scope.value if hasattr(subject_scope, "value") else str(subject_scope or ""),
    }


def validate_ledger_kinds(kinds: Collection[str]) -> FrozenSet[str]:
    parsed = frozenset(str(kind).strip().casefold() for kind in kinds if str(kind).strip())
    if not parsed or not parsed.issubset(LEDGER_SEARCH_KINDS):
        raise ValueError("kinds must contain only fact, document, or trigger")
    return parsed


__all__ = [
    "LEDGER_INDEX_VERSION",
    "LEDGER_SEARCH_KINDS",
    "LedgerRowIndexState",
    "LedgerSearchSurface",
    "build_ledger_index_metadata",
    "is_ledger_row_admissible",
    "ledger_kind_value",
    "ledger_row_index_state",
    "ledger_schema_is_current",
    "validate_ledger_kinds",
]
