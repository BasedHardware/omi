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


def scoped_device_id_required(device_scope: DeviceScope) -> bool:
    return device_scope in ("current", "explicit")


def device_scope_validation_error(device_scope: DeviceScope, client_device_id: Optional[str]) -> Optional[str]:
    """Return a client-facing error message when scoped filtering cannot run."""
    if not scoped_device_id_required(device_scope):
        return None
    if (client_device_id or "").strip():
        return None
    if device_scope == "current":
        return "device_scope=current requires X-App-Platform and X-Device-Id-Hash headers"
    return "device_scope=explicit requires client_device_id query parameter"


def filter_items_by_device_scope(
    items: List[MemoryItem],
    *,
    device_scope: DeviceScope = "all",
    client_device_id: Optional[str] = None,
) -> List[MemoryItem]:
    if device_scope == "all":
        return items
    if device_scope not in ("current", "explicit"):
        return items
    # Scoped filtering without a resolvable device id must not fall through to "all".
    # Return empty in-process; HTTP handlers should raise 400 via device_scope_validation_error().
    scoped_device_id = (client_device_id or "").strip()
    if not scoped_device_id:
        return []
    return [item for item in items if memory_matches_device(item, scoped_device_id)]
