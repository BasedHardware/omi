"""Canonical memory lineage resolution shared by default read surfaces."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from models.product_memory import MemoryItem, MemoryLayer


def canonical_lineage_root(item: MemoryItem, *, items_by_id: Dict[str, MemoryItem]) -> str:
    """Resolve an item to its canonical target without trusting alias cycles."""

    current = item
    path: List[str] = []
    position_by_id: Dict[str, int] = {}
    while True:
        cycle_start = position_by_id.get(current.memory_id)
        if cycle_start is not None:
            # A tail entering a cycle belongs to the cycle's stable
            # representative. Including the tail in the representative choice
            # would split one graph depending on which node traversal started
            # from (A→B→C→B used to resolve A→A but B/C→B).
            return min(path[cycle_start:])
        position_by_id[current.memory_id] = len(path)
        path.append(current.memory_id)
        # ``superseded_by`` was the production lineage edge before canonical
        # promotion began writing the explicit canonical id. Keep traversing
        # those authoritative rows so deletion and deduplication cover data
        # created before that rollout boundary.
        canonical_memory_id = (current.canonical_memory_id or current.superseded_by or "").strip()
        if not canonical_memory_id or canonical_memory_id == current.memory_id:
            return current.memory_id
        target = items_by_id.get(canonical_memory_id)
        if target is None:
            return canonical_memory_id
        current = target


def canonical_lineage_survivor_sort_key(
    item: MemoryItem,
    *,
    lineage_root: str,
) -> tuple[int, int, float, str]:
    """Prefer the Long-term canonical survivor, then the newest stable row."""

    tier_rank = 0 if item.tier == MemoryLayer.long_term else 1
    canonical_rank = 0 if item.memory_id == lineage_root else 1
    return (tier_rank, canonical_rank, -item.updated_at.timestamp(), item.memory_id)


def collapse_canonical_lineages(
    items: Iterable[MemoryItem],
    *,
    lineage_context: Optional[Iterable[MemoryItem]] = None,
    survivor_context: Optional[Iterable[MemoryItem]] = None,
) -> List[MemoryItem]:
    """Return at most one item per lineage while preserving first-match order.

    ``lineage_context`` may contain authoritative items that are not themselves
    visible. They are used only to traverse alias chains. ``survivor_context``
    contains eligible rows that may be returned even when they did not themselves
    match a query. Keeping these roles separate lets traversal cross a restricted
    intermediate without ever selecting that restricted row.
    """

    candidates = list(items)
    context = list(lineage_context) if lineage_context is not None else candidates
    survivors = list(survivor_context) if survivor_context is not None else context
    items_by_id = {item.memory_id: item for item in context}
    survivors_by_id = {item.memory_id: item for item in survivors}
    grouped: Dict[str, List[tuple[int, MemoryItem]]] = {}
    for position, item in enumerate(candidates):
        lineage_root = canonical_lineage_root(item, items_by_id=items_by_id)
        grouped.setdefault(lineage_root, []).append((position, item))

    selected: List[tuple[int, MemoryItem]] = []
    for lineage_root, entries in grouped.items():
        lineage_candidates = {item.memory_id: item for _, item in entries}
        canonical_item = survivors_by_id.get(lineage_root)
        if canonical_item is not None:
            lineage_candidates.setdefault(canonical_item.memory_id, canonical_item)
        survivor = min(
            lineage_candidates.values(),
            key=lambda item: canonical_lineage_survivor_sort_key(item, lineage_root=lineage_root),
        )
        selected.append((min(position for position, _ in entries), survivor))

    selected.sort(key=lambda entry: (entry[0], entry[1].memory_id))
    return [item for _, item in selected]


__all__ = [
    "canonical_lineage_root",
    "canonical_lineage_survivor_sort_key",
    "collapse_canonical_lineages",
]
