"""Shared admission policy for explicit canonical-ledger history reads."""

from datetime import datetime, timezone

from models.memories import MemoryDB
from models.product_memory import (
    MemoryAccessPolicy,
    LedgerWriteReason,
    MemoryItem,
    MemoryItemStatus,
    MemoryLayer,
    ProcessingState,
    RESTRICTED_SENSITIVITY_LABELS,
    SourceState,
    is_archive_access_eligible,
    is_default_access_eligible,
)

# Keep this policy module dependency-free from the knowledge-ledger writer.  The
# writer imports the canonical adapter, while the adapter imports this policy;
# importing the writer here would create a partial-module cycle during backend
# startup.  The discriminator is part of the canonical wire contract and is
# intentionally duplicated as a literal at this read-policy boundary.
LEDGER_SCHEMA_VERSION = "knowledge_ledger.v1"


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


def is_temporal_history_access_eligible(
    item: MemoryItem,
    policy: MemoryAccessPolicy,
    *,
    now: datetime | None = None,
    include_archive: bool = False,
) -> bool:
    """Apply the shared read fences for an explicit temporal history query.

    History can inspect retained active and superseded versions, but it does
    not weaken the normal privacy, processing, source, visibility, consumer,
    or tier checks.  A superseded item is copied as an active read candidate
    only for evaluating those shared checks; the canonical object is never
    mutated and its lifecycle status remains available to the caller.
    """

    clock = now or datetime.now(timezone.utc)
    if item.status not in {MemoryItemStatus.active, MemoryItemStatus.superseded}:
        return False
    if item.processing_state != ProcessingState.processed:
        return False
    promotion = item.promotion or {}
    if promotion.get('is_locked') is True:
        return False
    if item.source_state in {SourceState.tombstoned, SourceState.purged}:
        return False
    if set(item.sensitivity_labels).intersection(RESTRICTED_SENSITIVITY_LABELS):
        return False
    if item.tier == MemoryLayer.archive:
        return (
            include_archive
            and is_archive_access_eligible(
                item.model_copy(update={'status': MemoryItemStatus.active}),
                policy,
                now=clock,
            ).allowed
        )
    if item.tier not in {MemoryLayer.short_term, MemoryLayer.long_term}:
        return False
    candidate = item
    if item.status == MemoryItemStatus.superseded:
        candidate = item.model_copy(update={'status': MemoryItemStatus.active})
    return is_default_access_eligible(candidate, policy, now=clock).allowed
