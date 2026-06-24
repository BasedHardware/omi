"""Canonical memory domain vocabulary (WS-A).

This module defines the normative product-layer enums and the legal state-combination
validator. It introduces **no runtime behavior** — existing code continues to use
legacy types (e.g. ``MemoryTier`` in ``product_memory``) until later workstreams
rename call sites.

Terminology
-----------
**Conversation** — Persisted session record at ``users/{uid}/conversations``: processed
``transcript_segments``, session metadata (``structured``, ``apps_results``), audio/photo
linkage. Upstream of memory; never a memory layer.

**Capture session** — Ephemeral listen/recording window (WebSocket lifetime). For voice
paths, 1:1 with a Conversation stub created at listen start. Use when distinguishing
runtime capture from the persisted record.

**Workflow** — Action items (``action_items``) and goals (``goals``): task state, due
dates, integrations, progress. Downstream of extraction, parallel to Memories — **not**
a memory layer.

**Short-term / Long-term / Archive** — The three product lifecycle layers stored in the
unified Memories store, distinguished by the ``layer`` field on each record.

Non-layer concepts (see §1.1 / §1.3 in ``docs/memory/domain_model.md``):

- ``context_only`` is **not** a tier or layer — normalize to ``layer=archive`` or a
  non-default processing outcome.
- ``LifecycleState.working`` is an **in-flight extraction state** inside the pipeline;
  it is not a stored layer and resolves to a ``layer`` before the record is durable.
"""

from enum import Enum

from models.product_memory import MemoryTier


class MemoryLayer(str, Enum):
    """Product lifecycle layer on a Memories record."""

    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    ARCHIVE = "archive"


class MemoryRecordStatus(str, Enum):
    """Record lifecycle status; distinct from ``layer``."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    TOMBSTONED = "tombstoned"


# Physical ``MemoryItemStatus.hidden`` is a memory storage value with no §1.3 axis counterpart.
# Boundary-map to ``tombstoned`` (hard-excluded from default reads) for validation/materialization.
_PHYSICAL_TO_CANONICAL_STATUS: dict[str, MemoryRecordStatus] = {
    MemoryRecordStatus.ACTIVE.value: MemoryRecordStatus.ACTIVE,
    MemoryRecordStatus.SUPERSEDED.value: MemoryRecordStatus.SUPERSEDED,
    MemoryRecordStatus.TOMBSTONED.value: MemoryRecordStatus.TOMBSTONED,
    "hidden": MemoryRecordStatus.TOMBSTONED,
}


def physical_status_to_record_status(physical_status: str) -> MemoryRecordStatus:
    """Map physical ``MemoryItemStatus`` string to canonical ``MemoryRecordStatus``."""
    try:
        return _PHYSICAL_TO_CANONICAL_STATUS[physical_status]
    except KeyError as exc:
        raise ValueError(f"unknown physical memory status: {physical_status!r}") from exc


class MemoryProcessingState(str, Enum):
    """Internal pipeline processing state; never surfaced to clients."""

    PENDING = "pending"
    PROCESSED = "processed"
    BLOCKED = "blocked"


# Legal status sets per layer (§1.3).
_SHORT_TERM_STATUSES = frozenset(MemoryRecordStatus)
_LONG_TERM_STATUSES = frozenset(MemoryRecordStatus)
_ARCHIVE_STATUSES = frozenset({MemoryRecordStatus.ACTIVE, MemoryRecordStatus.TOMBSTONED})

_SHORT_TERM_PROCESSING = frozenset(MemoryProcessingState)
_LONG_TERM_PROCESSING = frozenset({MemoryProcessingState.PROCESSED})
_ARCHIVE_PROCESSING = frozenset({MemoryProcessingState.PROCESSED})


def is_legal_state_combination(
    layer: MemoryLayer,
    status: MemoryRecordStatus,
    processing_state: MemoryProcessingState,
) -> bool:
    """Return True iff (layer, status, processing_state) is legal per §1.3."""
    if layer is MemoryLayer.SHORT_TERM:
        return status in _SHORT_TERM_STATUSES and processing_state in _SHORT_TERM_PROCESSING
    if layer is MemoryLayer.LONG_TERM:
        return status in _LONG_TERM_STATUSES and processing_state in _LONG_TERM_PROCESSING
    if layer is MemoryLayer.ARCHIVE:
        return status in _ARCHIVE_STATUSES and processing_state in _ARCHIVE_PROCESSING
    return False


def assert_legal_state(
    layer: MemoryLayer,
    status: MemoryRecordStatus,
    processing_state: MemoryProcessingState,
) -> None:
    """Raise ValueError if the state combination is illegal."""
    if not is_legal_state_combination(layer, status, processing_state):
        raise ValueError(
            f"illegal memory state combination: layer={layer.value}, "
            f"status={status.value}, processing_state={processing_state.value}"
        )


# Product storage/API field remains ``tier`` on ``MemoryItem`` (bucket D — out of scope).
# ``models.product_memory.MemoryLayer`` is a type alias for ``MemoryTier`` (WS-G Wave 34).
# This module's ``MemoryLayer`` is the canonical validation enum (UPPER_CASE members).


def tier_to_layer(tier: MemoryTier) -> MemoryLayer:
    """Map legacy memory ``MemoryTier`` to canonical ``MemoryLayer`` (same semantics)."""
    return MemoryLayer(tier.value)


def layer_to_tier(layer: MemoryLayer) -> MemoryTier:
    """Map canonical ``MemoryLayer`` to legacy memory ``MemoryTier`` (same semantics)."""
    return MemoryTier(layer.value)
