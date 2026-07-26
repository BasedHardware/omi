"""Instrumented listener entrypoint for durable finalization scenarios.

The production FastAPI application and task construction remain real. Cloud
Tasks is the only external transport replaced; an opt-in gate merely
coordinates real route lookups for a deterministic concurrency scenario. A
separate opt-in selector can fail exactly one recording-session lifecycle
write before Firestore for persist-before-send regression coverage.
"""

import asyncio
import json
import os
from pathlib import Path
from threading import Barrier, BrokenBarrierError, Lock
from typing import Any

from testing.listen_pusher_stack.cloud_tasks import install_loopback_tasks_client

install_loopback_tasks_client()

from database import recording_sessions  # noqa: E402
from main import app  # noqa: E402
from routers.listen.conversations import LiveConversationController  # noqa: E402

RECORDING_LIFECYCLE_FAULT_ENV = 'OMI_STACK_RECORDING_LIFECYCLE_FAULT'
_RECORDING_LIFECYCLE_FAULT_KEYS = frozenset({'uid', 'recording_session_id', 'conversation_id', 'phase'})


def _install_recording_lifecycle_fault() -> None:
    """Fail one exact lifecycle write in this test-only listener process."""
    raw_selector = os.getenv(RECORDING_LIFECYCLE_FAULT_ENV, '')
    if not raw_selector:
        return
    try:
        selector = json.loads(raw_selector)
    except json.JSONDecodeError as error:
        raise RuntimeError(f'{RECORDING_LIFECYCLE_FAULT_ENV} must be valid JSON') from error
    if not isinstance(selector, dict) or set(selector) != _RECORDING_LIFECYCLE_FAULT_KEYS:
        raise RuntimeError(
            f'{RECORDING_LIFECYCLE_FAULT_ENV} must contain exactly ' + str(sorted(_RECORDING_LIFECYCLE_FAULT_KEYS))
        )
    if not all(isinstance(selector[key], str) and selector[key] for key in _RECORDING_LIFECYCLE_FAULT_KEYS):
        raise RuntimeError(f'{RECORDING_LIFECYCLE_FAULT_ENV} values must be non-empty strings')
    if selector['phase'] not in {'in_progress', 'processing', 'completed', 'failed', 'discarded'}:
        raise RuntimeError(f'{RECORDING_LIFECYCLE_FAULT_ENV} phase is unsupported')

    state_dir = Path(os.environ['OMI_STACK_STATE_DIR'])
    retry_file = state_dir / 'release-recording-lifecycle-retry'
    original_write = recording_sessions.record_lifecycle_event
    original_emit = LiveConversationController.emit_recording_lifecycle_event
    lock = Lock()
    armed = True
    fault_fired = False
    retry_claimed = False

    def fail_selected_write_once(
        uid: str,
        recording_session_id: str,
        conversation_id: str,
        phase: recording_sessions.RecordingPhase,
        *,
        firestore_client: Any = None,
    ) -> recording_sessions.RecordingSessionEvent:
        nonlocal armed, fault_fired
        operation = {
            'uid': uid,
            'recording_session_id': recording_session_id,
            'conversation_id': conversation_id,
            'phase': phase,
        }
        with lock:
            should_fail = armed and operation == selector
            if should_fail:
                armed = False
                fault_fired = True
                with (state_dir / 'recording_lifecycle_fault.jsonl').open('a', encoding='utf-8') as output:
                    output.write(json.dumps({'event': 'write_failed', **operation}, sort_keys=True) + '\n')
        if should_fail:
            raise RuntimeError('injected test-only recording lifecycle persistence fault')
        return original_write(
            uid,
            recording_session_id,
            conversation_id,
            phase,
            firestore_client=firestore_client,
        )

    recording_sessions.record_lifecycle_event = fail_selected_write_once

    if os.getenv('RECORDING_SESSION_MODE', '').strip().lower() != 'enforce':
        return

    async def emit_with_one_released_retry(
        self: LiveConversationController,
        conversation_id: str,
        phase: str,
    ) -> None:
        nonlocal retry_claimed
        await original_emit(self, conversation_id, phase)
        operation_matches = (
            self.host.request.uid == selector['uid']
            and selector['recording_session_id'] == self.host.recording_session_ids_by_conversation.get(conversation_id)
            and conversation_id == selector['conversation_id']
            and phase == selector['phase']
        )
        with lock:
            should_retry = fault_fired and operation_matches and not retry_claimed
            if should_retry:
                retry_claimed = True
        if not should_retry:
            return
        deadline = asyncio.get_running_loop().time() + 15.0
        while not retry_file.exists():
            if asyncio.get_running_loop().time() >= deadline:
                raise RuntimeError('timed out waiting to release recording lifecycle retry')
            await asyncio.sleep(0.05)
        await original_emit(self, conversation_id, phase)

    LiveConversationController.emit_recording_lifecycle_event = emit_with_one_released_retry


def _install_rest_finalization_race_barrier() -> None:
    """Force a bounded stale-read race before the real finalization transaction.

    The live gauntlet sends concurrent public REST calls, but scheduler timing
    alone cannot guarantee every handler reads ``in_progress`` before the
    winning Firestore transaction changes it to ``processing``. This opt-in
    harness seam gates only the first N target reads after they have used the
    production lookup. The route, auth, lifecycle transaction, and Cloud Tasks
    call therefore stay real while the intended named-task race is repeatable.
    """
    uid = os.getenv('OMI_STACK_FINALIZATION_RACE_UID', '')
    conversation_id = os.getenv('OMI_STACK_FINALIZATION_RACE_CONVERSATION_ID', '')
    raw_parties = os.getenv('OMI_STACK_FINALIZATION_RACE_PARTIES', '')
    if not any((uid, conversation_id, raw_parties)):
        return
    if not all((uid, conversation_id, raw_parties)):
        raise RuntimeError('REST finalization race barrier requires uid, conversation ID, and party count')
    try:
        parties = int(raw_parties)
    except ValueError as error:
        raise RuntimeError('REST finalization race barrier party count must be an integer') from error
    if parties < 2:
        raise RuntimeError('REST finalization race barrier needs at least two parties')

    from routers import conversations as conversations_router

    original_lookup = conversations_router._get_valid_conversation_by_id
    barrier = Barrier(parties)
    lock = Lock()
    remaining = parties

    def lookup_with_race_gate(request_uid: str, request_conversation_id: str):
        nonlocal remaining
        snapshot = original_lookup(request_uid, request_conversation_id)
        if request_uid != uid or request_conversation_id != conversation_id:
            return snapshot
        with lock:
            should_wait = remaining > 0
            if should_wait:
                remaining -= 1
        if not should_wait:
            return snapshot
        try:
            barrier.wait(timeout=10.0)
        except BrokenBarrierError as error:
            raise RuntimeError('REST finalization race barrier did not receive every request') from error
        return snapshot

    conversations_router._get_valid_conversation_by_id = lookup_with_race_gate


_install_recording_lifecycle_fault()
_install_rest_finalization_race_barrier()
