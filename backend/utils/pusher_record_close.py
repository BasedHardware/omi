"""Bounded close-v2 wire state; receipt/token proof remains in the audio drain."""

import json
import struct
import uuid
from dataclasses import dataclass, field
from collections import OrderedDict

VERSION = 2
CAPABILITY_OPCODE = 204
RESULT_OPCODE = 206
MAX_CLOSES = 128


def capability_frame():
    return struct.pack('<I', CAPABILITY_OPCODE) + b'{"type":"record_close_ack","version":2}'


def result_frame(cid, request_id, phase, status, watermark=0):
    return (
        struct.pack('<I', RESULT_OPCODE)
        + json.dumps(
            dict(
                type='record_close_result',
                version=VERSION,
                conversation_id=cid,
                request_id=request_id,
                phase=phase,
                status=status,
                watermark=watermark,
            )
        ).encode()
    )


@dataclass
class PendingClose:
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    socket: object = None
    prepared: bool = False
    frozen: bool = False
    base: int = 0
    sent: int = 0
    reported_fallbacks: set[str] = field(default_factory=set)


class PusherCloseState:
    def __init__(self, negotiated):
        self.negotiated = negotiated
        self.received: dict[str, int] = {}
        self.requests: dict[str, tuple[str, int]] = {}
        self.committed: set[str] = set()
        self.watermarks: dict[str, int] = {}
        self.completed: OrderedDict[str, tuple[str, int, int]] = OrderedDict()

    def audio(self, cid, size):
        if not self.negotiated or not cid:
            return
        if cid in self.committed:
            raise ValueError('audio follows committed recording boundary')
        if cid in self.received or len(self.received) < MAX_CLOSES:
            self.received[cid] = self.received.get(cid, 0) + size

    def prepare(self, cid, request_id, closing):
        if cid in self.completed:
            old_id, base, _ = self.completed[cid]
            return ('prepared', base) if old_id == request_id else ('conflict', 0)
        if cid in self.requests:
            old_id, base = self.requests[cid]
            return ('prepared', base) if old_id == request_id else ('conflict', 0)
        if len(set(self.requests) | closing | {cid}) > MAX_CLOSES:
            return 'capacity', 0
        if cid not in self.received and len(self.received) >= MAX_CLOSES:
            return 'capacity', 0
        base = self.received.setdefault(cid, 0)
        self.requests[cid] = request_id, base
        return 'prepared', base

    def commit(self, cid, request_id, watermark, *, accept=True):
        if cid in self.completed:
            old_id, _, target = self.completed[cid]
            if old_id != request_id:
                return 'unknown'
            return 'accepted' if watermark == target else 'invalid_watermark'
        if cid not in self.requests or self.requests[cid][0] != request_id:
            return 'unknown'
        if watermark < self.requests[cid][1]:
            return 'invalid_watermark'
        if self.received.get(cid, 0) < watermark:
            return 'watermark_pending'
        if accept:
            self.committed.add(cid)
            self.watermarks[cid] = watermark
        return 'accepted'

    def blocks(self, cid, active):
        return self.negotiated and cid not in self.committed and (active or cid in self.requests)

    def retire(self, cid):
        """Reclaim active wire slots only after the drain's terminal proof path.

        Recent terminal replies remain idempotent. An evicted old request must
        prepare anew and acquire its own producer fence, never inherit proof.
        """
        if cid not in self.committed or cid not in self.requests:
            return
        request_id, base = self.requests.pop(cid)
        self.completed[cid] = request_id, base, self.watermarks.pop(cid)
        self.received.pop(cid, None)
        while len(self.completed) > MAX_CLOSES:
            old, _ = self.completed.popitem(last=False)
            self.committed.discard(old)
