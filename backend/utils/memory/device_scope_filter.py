"""Device-scope filtering for memory retrieval (provenance only)."""

from __future__ import annotations

from typing import List, Literal, Optional

from models.product_memory import MemoryItem

DeviceScope = Literal["current", "all", "explicit"]


def memory_matches_device(item: MemoryItem, client_device_id: str) -> bool:
    target = (client_device_id or "").strip()
    if not target:
        return True

    if item.primary_capture_device == target:
        return True
    if target in (item.capture_device_ids or []):
        return True
    for evidence in item.evidence or []:
        if getattr(evidence, "client_device_id", None) == target:
            return True
    return False


def filter_items_by_device_scope(
    items: List[MemoryItem],
    *,
    device_scope: DeviceScope = "all",
    client_device_id: Optional[str] = None,
) -> List[MemoryItem]:
    if device_scope == "all" or not client_device_id:
        return items
    if device_scope not in ("current", "explicit"):
        return items
    return [item for item in items if memory_matches_device(item, client_device_id)]
