"""Exact, single-use write-boundary faults for test entrypoints only."""

from dataclasses import dataclass, field
from _thread import LockType
from threading import Lock

BOUNDARY_PHASES = frozenset({'seal', 'register', 'admit'})
BOUNDARY_SELECTOR_KEYS = frozenset({'uid', 'conversation_id', 'phase'})
SESSION_SELECTOR_KEYS = BOUNDARY_SELECTOR_KEYS | {'recording_session_id'}


def validate_fault_selector(selector):
    if not isinstance(selector, dict):
        raise ValueError('recording lifecycle fault must be a selector object')
    if not all(isinstance(value, str) and value for value in selector.values()):
        raise ValueError('recording lifecycle fault values must be non-empty strings')
    keys = BOUNDARY_SELECTOR_KEYS if selector.get('phase') in BOUNDARY_PHASES else SESSION_SELECTOR_KEYS
    if set(selector) != keys:
        raise ValueError(f'recording lifecycle fault must contain exactly {sorted(keys)}')


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
        if self.boundary not in BOUNDARY_PHASES or not self.uid or not self.conversation_id:
            raise ValueError('exact seal/register/admit operation required')

    def check(self, boundary: str, uid: str, conversation_id: str) -> None:
        with self._lock:
            if self.fired or (boundary, uid, conversation_id) != (self.boundary, self.uid, self.conversation_id):
                return
            self.fired = True
        raise InjectedLifecycleFault('selected lifecycle boundary interrupted')
