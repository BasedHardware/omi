"""Bounded close-v2 wire state; receipt/token proof remains in the audio drain."""

import json
import struct
import uuid
from dataclasses import dataclass, field

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


class PusherCloseState:
    def __init__(self, negotiated):
        self.negotiated = negotiated
        self.received: dict[str, int] = {}
        self.requests: dict[str, tuple[str, int]] = {}
        self.committed: set[str] = set()

    def audio(self, cid, size):
        if not self.negotiated or not cid:
            return
        if cid in self.committed:
            raise ValueError('audio follows committed recording boundary')
        if cid in self.received or len(self.received) < MAX_CLOSES:
            self.received[cid] = self.received.get(cid, 0) + size

    def prepare(self, cid, request_id, closing):
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
        if cid not in self.requests or self.requests[cid][0] != request_id:
            return 'unknown'
        if self.received.get(cid, 0) < watermark:
            return 'watermark_pending'
        if accept:
            self.committed.add(cid)
        return 'accepted'

    def blocks(self, cid, active):
        return self.negotiated and cid not in self.committed and (active or cid in self.requests)
