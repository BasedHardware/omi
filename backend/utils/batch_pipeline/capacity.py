"""Fail-closed low-priority admission from an explicitly sampled GPU pool budget.

Snapshot slots are supplied by the pool's exclusive worker/admission owner, after
reserving live traffic. This module does not infer slack from time of day or CPU.
"""

from dataclasses import dataclass
import math

# One canonical 16 kHz frame. Admitted durations are differences of epoch
# clocks, so a frame-exact one-hour unit can read 3600.0000005 seconds.
FRAME_SECONDS = 1 / 16000


def within_unit_ceiling(duration_seconds: float, ceiling_seconds: float) -> bool:
    """Compare at frame resolution: float noise must never park an owner's FIFO."""
    return duration_seconds <= ceiling_seconds + FRAME_SECONDS / 2


@dataclass(frozen=True)
class PoolCapacity:
    observed_at: float
    available_slots: int
    reserved_fresh_slots: int = 0
    max_item_seconds: float = 7200.0

    def limits(self, now: float) -> tuple[int, bool, float]:
        numbers = (now, self.observed_at, self.max_item_seconds)
        if any(type(value) is not int for value in (self.available_slots, self.reserved_fresh_slots)):
            return 0, False, 0
        if not 0 < self.max_item_seconds <= 7200:
            return 0, False, 0
        if not all(math.isfinite(value) for value in numbers):
            return 0, False, 0
        if not 0 <= now - self.observed_at <= 15:
            return 0, False, 0
        if not 0 <= self.reserved_fresh_slots <= self.available_slots <= 32:
            return 0, False, 0
        return self.available_slots, self.available_slots > self.reserved_fresh_slots, self.max_item_seconds
