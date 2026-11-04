"""Exact, single-use write-boundary faults for test entrypoints only."""

from dataclasses import dataclass, field
from _thread import LockType
from threading import Lock


class InjectedLifecycleFault(RuntimeError):
    """One selected seal, registration, or admission attempt was interrupted."""


@dataclass
class BoundaryFault:
    boundary: str
    uid: str
    conversation_id: str
    fired: bool = False
    _lock: LockType = field(default_factory=Lock, repr=False)

    def __post_init__(self):
        if self.boundary not in {'seal', 'register', 'admit'} or not self.uid or not self.conversation_id:
            raise ValueError('exact seal/register/admit operation required')

    def check(self, boundary: str, uid: str, conversation_id: str) -> None:
        with self._lock:
            if self.fired or (boundary, uid, conversation_id) != (self.boundary, self.uid, self.conversation_id):
                return
            self.fired = True
        raise InjectedLifecycleFault('selected lifecycle boundary interrupted')
