"""Bounded, receiver-only accepted-send proof. Never part of a storage schema."""

from dataclasses import dataclass, replace
from typing import Optional, Tuple


@dataclass(frozen=True)
class CaptureWindowProof:
    epoch: str
    window: Tuple[float, float]
    accepted_run: Tuple[float, float]

    def matches(self, window: Optional[Tuple[float, float]]) -> bool:
        return window == self.window and self.accepted_run[0] <= self.window[0] < self.window[1] <= self.accepted_run[1]

    def union(self, other: 'CaptureWindowProof') -> Optional['CaptureWindowProof']:
        if self.epoch != other.epoch:
            return None
        window = (min(self.window[0], other.window[0]), max(self.window[1], other.window[1]))
        # One snapshot must prove the entire union. Never stitch snapshots or
        # infer received silence from two translated word endpoints alone.
        for proof in (other, self):
            if proof.accepted_run[0] <= window[0] and window[1] <= proof.accepted_run[1]:
                return replace(proof, window=window)
        return None
