"""Bounded grace for tiny transition tails; capture boundary checks stay in the sink."""

import time

from utils.observability.held_content import record_transition_tail

TINY_SECONDS = 0.25
GRACE_SECONDS = 1.0


class TailGrace:
    def __init__(self) -> None:
        self.opened: dict[tuple, float] = {}
        self.deferred: set[tuple] = set()

    def appended(self, key: tuple) -> None:
        self.opened.setdefault(key, time.monotonic())
        if key in self.deferred:
            self.deferred.remove(key)
            record_transition_tail('coalesced')

    def queued(self, key: tuple) -> None:
        self.opened.pop(key, None)
        if key in self.deferred:
            self.deferred.remove(key)
            record_transition_tail('sealed')

    def expired(self) -> bool:
        return any(time.monotonic() - self.opened[key] >= GRACE_SECONDS for key in self.deferred)

    def ready(self, key: tuple, seconds: float, bound: float, *, force: bool, final: bool) -> bool:
        age = time.monotonic() - self.opened[key]
        if not final and 0 < seconds < TINY_SECONDS and age < GRACE_SECONDS:
            if force:
                self.deferred.add(key)
            return False
        return final or force or age >= bound or key in self.deferred
