"""Fail-closed low-priority admission from an explicitly sampled GPU pool budget.

Snapshot slots are supplied by the pool's exclusive worker/admission owner, after
reserving live traffic. This module does not infer slack from time of day or CPU.
"""

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class PoolCapacity:
    observed_at: float
    available_slots: int
    reserved_fresh_slots: int = 0
    shared_with_live: bool = False
    live_queue_age_seconds: float = 0.0
    gpu_utilization: float = 0.0
    memory_headroom_bytes: int = 0
    max_item_seconds: float = 7200.0
    gpu_id: str | None = None

    def limits(self, now: float, *, shared_live_enabled: bool) -> tuple[int, bool, float]:
        numbers = (now, self.observed_at, self.live_queue_age_seconds, self.gpu_utilization, self.max_item_seconds)
        if any(
            type(value) is not int
            for value in (self.available_slots, self.reserved_fresh_slots, self.memory_headroom_bytes)
        ):
            return 0, False, 0
        if self.memory_headroom_bytes < 0 or not 0 < self.max_item_seconds <= 7200:
            return 0, False, 0
        if not all(math.isfinite(value) for value in numbers):
            return 0, False, 0
        if not 0 <= now - self.observed_at <= 15 or not 0 <= self.gpu_utilization <= 1:
            return 0, False, 0
        if not 0 <= self.reserved_fresh_slots <= self.available_slots <= 32:
            return 0, False, 0
        if self.shared_with_live:
            # Conversation-size work never borrows live GPUs. The independent
            # live admission owner must grant an exclusive single short slot.
            safe = (
                shared_live_enabled
                and isinstance(self.gpu_id, str)
                and 0 < len(self.gpu_id) <= 128
                and self.available_slots == 1
                and self.reserved_fresh_slots == 0
                and self.live_queue_age_seconds == 0
                and self.gpu_utilization < 0.5
                and self.memory_headroom_bytes >= 8 * 1024**3
            )
            return (1, True, min(120.0, self.max_item_seconds)) if safe else (0, False, 0)
        return self.available_slots, self.available_slots > self.reserved_fresh_slots, self.max_item_seconds
