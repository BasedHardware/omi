"""Bounded pusher disconnect retries, without a queue or a new worker."""

import asyncio
import logging
import threading
from typing import Iterable

from utils.conversations import speaker_resolution
from utils.executors import storage_executor, start_background_task, submit_with_context

logger = logging.getLogger(__name__)
MAX_LATE_IDENTITY_JOBS = 2
MAX_LATE_IDENTITY_CANDIDATES = 128
MAX_LATE_IDENTITY_PASSES = 8
_slots = threading.BoundedSemaphore(MAX_LATE_IDENTITY_JOBS)


def _retry_batch(uid: str, conversation_ids: tuple[str, ...]) -> None:
    attempted = 0
    for conversation_id in conversation_ids:
        if attempted >= MAX_LATE_IDENTITY_PASSES:
            break
        try:
            raw = speaker_resolution.conversations_db.get_conversation(uid, conversation_id)
            if not speaker_resolution.completed_identity_retry_eligible(raw):
                continue
            # Selection follows eligibility. Pass this snapshot into the CAS
            # path, avoiding a second read and retaining its revision fence.
            attempted += 1
            speaker_resolution.refresh_completed_speaker_identity(uid, conversation_id, candidate=raw)
        except Exception as error:
            logger.warning('event=speaker_identity_retry outcome=failed exception_type=%s', type(error).__name__)


def schedule_completed_identity_retries(uid: str, conversation_ids: Iterable[str]) -> bool:
    """At most two submitted/running batches process-wide, including cancelled waiters."""
    if not _slots.acquire(blocking=False):
        return False
    try:
        candidates = tuple(sorted(set(conversation_ids))[:MAX_LATE_IDENTITY_CANDIDATES])
        future = submit_with_context(storage_executor, _retry_batch, uid, candidates)
    except Exception:
        _slots.release()
        raise
    # Release only when the actual thread finishes. Cancelling the async waiter
    # cannot release a slot while blocking storage/model work is still running.
    future.add_done_callback(lambda _: _slots.release())

    async def wait_for_batch() -> None:
        await asyncio.shield(asyncio.wrap_future(future))

    start_background_task(wait_for_batch(), name='speaker_identity_late_audio')
    return True
