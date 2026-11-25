"""Event-loop-owned frame reservations for an ordered recording close.

Reservations start synchronously at dequeue, before archive/STT can yield. A
retired current binding maps subsequent frames to the existing unlinked custody
route until a successor exists. No byte buffer or background task lives here.
"""

from collections import Counter, OrderedDict
from dataclasses import dataclass


@dataclass
class AudioFrameLease:
    boundary: 'ListenRecordBoundary'
    conversation_id: str | None

    def __enter__(self):
        if self.conversation_id:
            self.boundary.inflight[self.conversation_id] += 1
        return self

    def __exit__(self, error_type, error, traceback):
        if error_type is not None:
            self.boundary.failed = True  # Unknown acceptance cannot certify a close.
        if self.conversation_id:
            self.boundary.inflight[self.conversation_id] -= 1
            if not self.boundary.inflight[self.conversation_id]:
                del self.boundary.inflight[self.conversation_id]


class ListenRecordBoundary:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.retired: OrderedDict[str, None] = OrderedDict()
        self.inflight: Counter[str] = Counter()
        self.failed = False
        self.retired_current: str | None = None

    def frame(self, conversation_id: str | None) -> AudioFrameLease:
        owner = None if conversation_id in self.retired or conversation_id == self.retired_current else conversation_id
        return AudioFrameLease(self, owner)

    def retire(self, conversation_id: str, *, current: str | None = None) -> None:
        if conversation_id == current:
            self.retired_current = conversation_id
        self.retired[conversation_id] = None
        self.retired.move_to_end(conversation_id)
        while len(self.retired) > self.capacity:
            self.retired.popitem(last=False)

    def ready(self, conversation_id: str) -> bool:
        return (
            (conversation_id in self.retired or conversation_id == self.retired_current)
            and not self.failed
            and not self.inflight.get(conversation_id)
        )
