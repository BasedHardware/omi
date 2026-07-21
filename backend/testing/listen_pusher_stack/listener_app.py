"""Instrumented listener entrypoint for durable finalization scenarios.

The production FastAPI application and task construction remain real. Cloud
Tasks is the only external transport replaced; an opt-in gate merely
coordinates real route lookups for a deterministic concurrency scenario.
"""

import os
from threading import Barrier, BrokenBarrierError, Lock

from testing.listen_pusher_stack.cloud_tasks import install_loopback_tasks_client

install_loopback_tasks_client()

from main import app  # noqa: E402


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


_install_rest_finalization_race_barrier()
