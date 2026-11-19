"""Invocation-scoped limits shared by staged objects and manifest source reads."""

from dataclasses import dataclass
import time


class ArtifactReadLimit(RuntimeError):
    pass


@dataclass
class ArtifactReadBudget:
    deadline: float
    max_bytes: int
    max_objects: int
    downloaded_bytes: int = 0
    objects: int = 0
    # Reservations can include a failed transfer. Count completed response
    # bodies separately; partial bytes from a failed SDK call are unknowable.
    received_bytes: int = 0

    def timeout(self, ceiling):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ArtifactReadLimit('artifact read deadline')
        return min(ceiling, remaining)

    def begin(self):
        self.timeout(30)
        if self.objects >= self.max_objects:
            raise ArtifactReadLimit('artifact object limit')
        self.objects += 1

    def reserve(self, size):
        self.timeout(60)
        if self.downloaded_bytes + size > self.max_bytes:
            raise ArtifactReadLimit('artifact byte limit')
        self.downloaded_bytes += size
