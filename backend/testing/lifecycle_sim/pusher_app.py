"""Real stack pusher plus a local driver for a live custody token.

The driver enters the production barrier before any frames are accepted. The
parent kills the actual ASGI process while this token remains live. This avoids
depending on an audio uploader's scheduling to hit the process-death boundary.
"""

import os
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel

from testing.hermetic_network import block_outbound_network
from testing.lifecycle_sim.preflight import preflight

preflight(Path(os.environ['OMI_STACK_STATE_DIR']))
_network_guard = block_outbound_network()
_network_guard.__enter__()

from testing.listen_pusher_stack.pusher_app import app  # noqa: E402
from utils.pusher_record_barrier import PusherRecordBarrier  # noqa: E402

_live_barriers: dict[str, PusherRecordBarrier] = {}


class BeginCapture(BaseModel):
    uid: str
    conversation_id: str


@app.post('/__lifecycle/begin')
async def begin(payload: BeginCapture):
    if not payload.uid.startswith('synthetic-lifecycle-') or len(_live_barriers) >= 4:
        raise HTTPException(400, 'bounded synthetic captures required')
    barrier = PusherRecordBarrier(payload.uid)
    await barrier.begin_recording(payload.conversation_id)
    if payload.conversation_id not in barrier.upload_sessions:
        raise HTTPException(500, 'custody token was not persisted')
    _live_barriers[payload.conversation_id] = barrier
    return {'pending': True}
