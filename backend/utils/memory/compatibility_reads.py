# LIFECYCLE: permanent
"""Request-local evidence and ordering for mixed canonical/historical reads."""

from datetime import timezone
from typing import Dict, Set

from database.memory_list_index import MemoryListIndexState
from models.memories import MemoryDB
from models.product_memory import MemoryItemStatus


class CompatibilityReadState:
    """Reuse metadata and status evidence only within one admitted list read."""

    def __init__(self, uid: str) -> None:
        self.index = MemoryListIndexState(uid)
        self.statuses: Dict[str, MemoryItemStatus] = {}
        self.status_ids_read: Set[str] = set()


def memory_sort_key(memory: MemoryDB) -> tuple[float, str]:
    value = getattr(memory, "updated_at", None) or getattr(memory, "created_at", None)
    if value is None:
        timestamp = float("-inf")
    else:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        timestamp = value.timestamp()
    return (-timestamp, memory.id)


def next_historical_scan_limit(current: int, *, step: int, max_window: int) -> int:
    """Grow the adaptive historical scan at least geometrically.

    Every expansion round re-reads the whole newest-first prefix from the
    start, so a linear step makes one page cost O(rounds x prefix): a fully
    suppressed account at window=500 stepped 500, 1000, ... 5000 and read
    27,500 documents over 55 queries for a single page. Doubling keeps the
    light case identical (the first expansion is still ``current + step``)
    and bounds the heavy case to a logarithmic number of rescans.
    """
    grown = max(current + max(1, int(step)), current * 2)
    return min(max_window, grown)
