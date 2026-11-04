"""Optional write-boundary interception in the instrumented listener only."""

from database import record_audio
from testing.lifecycle_sim.faults import BoundaryFault
from utils.batch_pipeline import live
from utils.conversations import finalizer


def install_boundary_fault(selector: dict[str, str]) -> BoundaryFault:
    fault = BoundaryFault(selector['phase'], selector['uid'], selector['conversation_id'])
    seal, register, admit = record_audio.seal_record_audio, live.register_recording, live.admit_recording

    def seal_once(uid, conversation_id, **kwargs):
        fault.check('seal', uid, conversation_id)
        return seal(uid, conversation_id, **kwargs)

    def register_once(uid, conversation, **kwargs):
        fault.check('register', uid, conversation.get('id', ''))
        return register(uid, conversation, **kwargs)

    async def admit_once(store, pending, **kwargs):
        fault.check('admit', pending['owner_id'], pending['conversation_id'])
        return await admit(store, pending, **kwargs)

    record_audio.seal_record_audio = seal_once
    live.register_recording = register_once
    finalizer.register_recording = register_once
    live.admit_recording = admit_once
    return fault
