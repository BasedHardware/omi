"""Bounded pusher retries that wait asynchronously for first finalization."""

import asyncio
import logging
import threading
import time
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
MAX_LATE_IDENTITY_WAITERS = 2
ADMISSION_RECHECK_DELAYS = (5, 15, 30, 60, 120)
COMPLETION_RECHECK_DELAYS = (5, 15, 30, 60, 120)
_slots = threading.BoundedSemaphore(MAX_LATE_IDENTITY_JOBS)
_waiting_slots = threading.BoundedSemaphore(MAX_LATE_IDENTITY_WAITERS)
_active_lock = threading.Lock()
_active: set[tuple[str, str]] = set()
_waiting: set[tuple[str, str]] = set()


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
    """Two active batches plus two bounded, ID-only admission waiters.

    Waiters read no conversations/audio and borrow no executor thread. Each
    admitted batch retains the existing 128-candidate and eight-pass ceilings.
    Overlapping submissions coalesce across both active and waiting work.
    """
    known = sorted(set(conversation_ids))
    with _active_lock:
        known = [cid for cid in known if (uid, cid) not in _active and (uid, cid) not in _waiting]
        if not known:
            return True
        record_retry('late', 'entry', 'candidate', len(known))
        candidates = tuple(known[:MAX_LATE_IDENTITY_CANDIDATES])
        keys = {(uid, cid) for cid in candidates}
        if _slots.acquire(blocking=False):
            _active.update(keys)
            deferred = False
        elif _waiting_slots.acquire(blocking=False):
            _waiting.update(keys)
            deferred = True
        else:
            record_retry('late', 'skipped', 'slot_limit', len(known))
            return False
    if len(known) > len(candidates):
        record_retry('late', 'skipped', 'scan_limit', len(known) - len(candidates))
    if deferred:
        record_retry('late', 'deferred', 'slot_limit', len(candidates))
        _wait_for_admission(uid, candidates)
    else:
        _start_batch(uid, candidates)
    return True


def _wait_for_admission(uid: str, candidates: tuple[str, ...]) -> None:
    keys = {(uid, cid) for cid in candidates}
    handed_off = False
    released = False
    deadline = time.monotonic() + sum(ADMISSION_RECHECK_DELAYS)

    def discard_waiter(reason: str) -> None:
        nonlocal released
        with _active_lock:
            if handed_off or released:
                return
            # Terminal accounting can trigger a same-turn resubmit. It must see
            # this reservation removed, and later cleanup must leave it alone.
            _waiting.difference_update(keys)
            released = True
        record_retry('late', 'skipped', reason, len(candidates))

    def release_waiter() -> None:
        # Also accounts for cancellation before wait() ever starts.
        discard_waiter('slot_limit')
        with _active_lock:
            _waiting_slots.release()

    async def wait() -> None:
        nonlocal handed_off
        try:
            for delay in ADMISSION_RECHECK_DELAYS:
                remaining = deadline - time.monotonic()
                if remaining < 0:
                    break
                await asyncio.sleep(min(delay, remaining))
                with _active_lock:
                    admitted = time.monotonic() <= deadline and _slots.acquire(blocking=False)
                    if admitted:
                        # Atomic handoff: overlapping submissions always see the keys.
                        _active.update(keys)
                        _waiting.difference_update(keys)
                        handed_off = True
                if admitted:
                    # Eligibility and the revision fence use a fresh snapshot here.
                    _start_batch(uid, candidates)
                    return
        finally:
            # Cancellation propagates after one terminal skip; handed-off work
            # has its own terminal verdict and must not be counted here.
            discard_waiter('slot_limit')

    coro = wait()
    try:
        task = start_background_task(coro, name='speaker_identity_admission')
    except Exception:
        coro.close()
        discard_waiter('submission_error')
        release_waiter()
        raise
    # Also releases a waiter cancelled before its coroutine ever starts.
    task.add_done_callback(lambda _: release_waiter())


def _start_batch(uid: str, candidates: tuple[str, ...]) -> None:
    """Caller owns one active slot and has registered the candidate keys."""
    keys = {(uid, cid) for cid in candidates}

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
