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
from testing.lifecycle_sim.producers import CaptureRefused, begin_capture

preflight(Path(os.environ['OMI_STACK_STATE_DIR']))
_network_guard = block_outbound_network()
_network_guard.__enter__()

from testing.listen_pusher_stack.pusher_app import app  # noqa: E402
from utils.pusher_record_barrier import PusherRecordBarrier  # noqa: E402
from database import record_audio  # noqa: E402
from utils.executors import db_executor, run_blocking  # noqa: E402

_live_barriers: dict[str, PusherRecordBarrier] = {}


class BeginCapture(BaseModel):
    uid: str
    conversation_id: str


@app.post('/__lifecycle/begin')
async def begin(payload: BeginCapture):
    try:
        await begin_capture(_live_barriers, payload.uid, payload.conversation_id, make_barrier=PusherRecordBarrier)
    except CaptureRefused as error:
        raise HTTPException(400, str(error)) from error
    return {'pending': True}


@app.post('/__lifecycle/seal')
async def seal(payload: BeginCapture):
    # Exercise the real refusal transaction in the child whose lifetime the
    # simulator controls, rather than borrowing the parent's process memory.
    refusal = await run_blocking(db_executor, record_audio.seal_record_audio, payload.uid, payload.conversation_id)
    return {'refusal': refusal}
