"""Shared admission policy for explicit canonical-ledger history reads."""

from models.memories import MemoryDB
from models.product_memory import (
    LedgerWriteReason,
    MemoryItem,
    MemoryItemStatus,
    ProcessingState,
    RESTRICTED_SENSITIVITY_LABELS,
    SourceState,
)
from utils.memory.knowledge_ledger import LEDGER_SCHEMA_VERSION


def is_ledger_history_item(item: MemoryItem, row: MemoryDB) -> bool:
    """Return whether one canonical row belongs to the explicit history view."""

    if item.ledger_schema_version != LEDGER_SCHEMA_VERSION:
        return False
    is_preserved_legacy_history = not item.intent_backed and item.write_reason == LedgerWriteReason.legacy_migration
    if not item.intent_backed and not is_preserved_legacy_history:
        return False
    if item.status in {MemoryItemStatus.hidden, MemoryItemStatus.tombstoned}:
        return False
    if item.processing_state != ProcessingState.processed:
        return False
    if item.source_state in {SourceState.tombstoned, SourceState.purged}:
        return False
    if set(item.sensitivity_labels).intersection(RESTRICTED_SENSITIVITY_LABELS):
        return False
    if row.is_locked:
        return False
    # Admit only states the public MemoryDB wire shape can represent. A
    # status-only superseded row would otherwise serialize as current.
    return (
        is_preserved_legacy_history
        or row.user_review is False
        or row.invalid_at is not None
        or row.superseded_by is not None
    )
