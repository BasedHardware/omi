"""Bounded pusher retries that wait asynchronously for first finalization."""

import asyncio
import logging
import threading
from dataclasses import dataclass
from functools import partial
from typing import Iterable

from utils.conversations import speaker_resolution
from utils.executors import storage_executor, start_background_task, submit_with_context
from utils.observability.owner_identity_retry import record_retry

logger = logging.getLogger(__name__)
MAX_LATE_IDENTITY_JOBS = 2
MAX_LATE_IDENTITY_CANDIDATES = 128
MAX_LATE_IDENTITY_PASSES = 8
COMPLETION_RECHECK_DELAYS = (5, 15, 30, 60, 120)
_slots = threading.BoundedSemaphore(MAX_LATE_IDENTITY_JOBS)
_active_lock = threading.Lock()
_active: set[tuple[str, str]] = set()


@dataclass(frozen=True)
class RetryRound:
    pending: tuple[str, ...]
    attempted: int


def _retry_batch(
    uid: str, conversation_ids: tuple[str, ...], *, remaining_passes: int = MAX_LATE_IDENTITY_PASSES
) -> RetryRound:
    attempted = 0
    pending: list[str] = []
    for index, conversation_id in enumerate(conversation_ids):
        if attempted >= remaining_passes:
            record_retry('late', 'skipped', 'pass_limit', len(conversation_ids) - index)
            break
        failure = 'read_error'
        try:
            raw = speaker_resolution.conversations_db.get_conversation(uid, conversation_id)
            failure = 'processing_error'
            skip = speaker_resolution.completed_identity_retry_skip_reason(raw)
            if skip == 'not_completed' and raw is not None and raw.get('status') in ('processing', 'in_progress'):
                # Keep the attempt open. Finalization runs in another process;
                # only a fresh completed snapshot can enter identity repair.
                pending.append(conversation_id)
                continue
            if skip is not None:
                record_retry('late', 'skipped', skip)
                continue
            # Selection follows eligibility. Pass this snapshot into the CAS
            # path, avoiding a second read and retaining its revision fence.
            attempted += 1
            speaker_resolution.refresh_completed_speaker_identity(uid, conversation_id, candidate=raw)
        except Exception as error:
            record_retry('late', 'skipped', failure)
            logger.warning('event=speaker_identity_retry outcome=failed exception_type=%s', type(error).__name__)
    return RetryRound(tuple(pending), attempted)


def schedule_completed_identity_retries(uid: str, conversation_ids: Iterable[str]) -> bool:
    """Two batches, 128 distinct candidates and eight passes, including all rechecks.

    A waiting batch retains its slot, but no executor thread. Overlapping drain
    submissions coalesce while active; each candidate enters repair at most once
    in this batch, even when finalization and upload drain race.
    """
    known = sorted(set(conversation_ids))
    with _active_lock:
        known = [cid for cid in known if (uid, cid) not in _active]
        if not known:
            return True
        record_retry('late', 'entry', 'candidate', len(known))
        if not _slots.acquire(blocking=False):
            record_retry('late', 'skipped', 'slot_limit', len(known))
            return False
        candidates = tuple(known[:MAX_LATE_IDENTITY_CANDIDATES])
        keys = {(uid, cid) for cid in candidates}
        _active.update(keys)
    if len(known) > len(candidates):
        record_retry('late', 'skipped', 'scan_limit', len(known) - len(candidates))

    def release() -> None:
        with _active_lock:
            _active.difference_update(keys)
            _slots.release()

    try:
        future = submit_with_context(storage_executor, _retry_batch, uid, candidates)
    except Exception:
        record_retry('late', 'skipped', 'submission_error', len(candidates))
        release()
        raise
    current = [future]

    async def wait_for_batch() -> None:
        result = await asyncio.shield(asyncio.wrap_future(current[0]))
        remaining = MAX_LATE_IDENTITY_PASSES - result.attempted
        for delay in COMPLETION_RECHECK_DELAYS:
            if not result.pending:
                return
            if not remaining:
                record_retry('late', 'skipped', 'pass_limit', len(result.pending))
                return
            await asyncio.sleep(delay)
            try:
                current[0] = submit_with_context(
                    storage_executor, partial(_retry_batch, remaining_passes=remaining), uid, result.pending
                )
            except Exception:
                record_retry('late', 'skipped', 'submission_error', len(result.pending))
                raise
            result = await asyncio.shield(asyncio.wrap_future(current[0]))
            remaining -= result.attempted
        if result.pending:
            record_retry('late', 'skipped', 'pass_limit' if not remaining else 'not_completed', len(result.pending))

    # A task done callback runs even if cancelled before its coroutine starts.
    # The current worker still owns admission until it actually finishes; while
    # sleeping, its completed Future releases immediately on cancellation.
    coro = wait_for_batch()
    try:
        task = start_background_task(coro, name='speaker_identity_late_audio')
    except Exception:
        coro.close()
        current[0].add_done_callback(lambda _: release())
        raise
    task.add_done_callback(lambda _: current[0].add_done_callback(lambda _: release()))

    return True
