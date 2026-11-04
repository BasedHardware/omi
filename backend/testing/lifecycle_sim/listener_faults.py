"""Optional write-boundary interception in the instrumented listener only."""

import json
from pathlib import Path

from database import record_audio
from testing.lifecycle_sim.faults import BoundaryFault, InjectedLifecycleFault, validate_fault_selector
from utils.batch_pipeline import live
from utils.conversations import finalizer


def install_boundary_fault(selector: dict[str, str], *, state_dir: Path | None = None) -> BoundaryFault:
    # These operations own a conversation, not a recording-session write.
    # Reject a session selector rather than silently widening its scope.
    validate_fault_selector(selector)
    fault = BoundaryFault(selector['phase'], selector['uid'], selector['conversation_id'])
    seal, register, admit = record_audio.seal_record_audio, live.register_recording, live.admit_recording

    def check(boundary, uid, conversation_id):
        try:
            fault.check(boundary, uid, conversation_id)
        except InjectedLifecycleFault:
            if state_dir is not None:
                event = {'event': 'write_failed', 'scope': 'conversation', **selector}
                with (state_dir / 'recording_lifecycle_fault.jsonl').open('a', encoding='utf-8') as output:
                    output.write(json.dumps(event, sort_keys=True) + '\n')
            raise

    def seal_once(uid, conversation_id, **kwargs):
        check('seal', uid, conversation_id)
        return seal(uid, conversation_id, **kwargs)

    def register_once(uid, conversation, **kwargs):
        check('register', uid, conversation.get('id', ''))
        return register(uid, conversation, **kwargs)

    async def admit_once(store, pending, **kwargs):
        check('admit', pending['owner_id'], pending['conversation_id'])
        return await admit(store, pending, **kwargs)

    record_audio.seal_record_audio = seal_once
    live.register_recording = register_once
    finalizer.register_recording = register_once
    live.admit_recording = admit_once
    return fault
