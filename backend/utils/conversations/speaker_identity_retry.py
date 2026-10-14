"""Bounded pusher retries that wait asynchronously for first finalization."""

import asyncio
import logging
import os
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass, field
from functools import partial
from typing import Iterable, Optional

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
    if os.getenv('OWNER_IDENTITY_RETRY_COALESCE_ENABLED', 'false').lower() == 'true':
        return _schedule_coalesced(uid, conversation_ids)
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


MAX_QUEUED_UIDS = 16
_coalescing_lock = threading.Lock()


@dataclass
class _RetryCohort:
    pending: set[str] = field(default_factory=set)
    seen: set[str] = field(default_factory=set)
    deadline: float = 0
    acquired: bool = False
    initial_count: int = 0
    current: Optional[Future] = None
    unresolved: tuple[str, ...] = ()
    carried: tuple[str, ...] = ()
    wake: asyncio.Event = field(default_factory=asyncio.Event)
    loop: Optional[asyncio.AbstractEventLoop] = None


_cohorts: dict[str, _RetryCohort] = {}


def _schedule_coalesced(uid: str, conversation_ids: Iterable[str]) -> bool:
    known = sorted(set(conversation_ids))
    with _coalescing_lock:
        cohort = _cohorts.get(uid)
        fresh = [cid for cid in known if cohort is None or cid not in cohort.seen]
        if cohort is not None:
            in_flight = cohort.pending | set(cohort.unresolved) | set(cohort.carried)
            duplicates = set(known) - set(fresh)
            pending_duplicates = len(duplicates & in_flight)
            terminal_duplicates = len(duplicates - in_flight)
            if pending_duplicates:
                # Still-owned IDs coalesce rather than drop; no entry or skip.
                record_retry('late', 'deferred', 'in_flight', pending_duplicates)
            if terminal_duplicates:
                # A suppressed terminal resubmission is its own accounted entry.
                record_retry('late', 'entry', 'candidate', terminal_duplicates)
                record_retry('late', 'skipped', 'cohort_seen', terminal_duplicates)
        known = fresh
        if not known:
            return True
        record_retry('late', 'entry', 'candidate', len(known))
        if cohort is None and len(_cohorts) >= MAX_QUEUED_UIDS:
            record_retry('late', 'skipped', 'queue_limit', len(known))
            return False
        created = cohort is None
        if cohort is None:
            cohort = _RetryCohort(
                deadline=time.monotonic() + sum(ADMISSION_RECHECK_DELAYS), loop=asyncio.get_running_loop()
            )
            _cohorts[uid] = cohort
        room = MAX_LATE_IDENTITY_CANDIDATES - len(cohort.seen)
        candidates = known[:room]
        cohort.seen.update(candidates)
        cohort.pending.update(candidates)
        if created:
            cohort.initial_count = len(candidates)
        elif cohort.acquired and candidates:
            _signal_cohort(cohort)
    if len(known) > len(candidates):
        record_retry('late', 'skipped', 'scan_limit', len(known) - len(candidates))
    if not created:
        record_retry('late', 'deferred', 'coalesced', len(candidates))
        return bool(candidates)
    coro = _run_cohort(uid, cohort)
    try:
        task = start_background_task(coro, name='speaker_identity_coalesced')
    except Exception:
        coro.close()
        _release_cohort(uid, cohort, 'submission_error')
        raise

    # Runs even for cancellation before the coroutine starts. A running worker
    # retains both UID ownership and its slot until its shielded Future finishes.
    def finished(task):
        reason = 'cancelled' if task.cancelled() else 'submission_error'
        if cohort.current is not None and not cohort.current.done():
            cohort.current.add_done_callback(lambda _: _release_cohort(uid, cohort, reason))
        else:
            _release_cohort(uid, cohort, reason)

    task.add_done_callback(finished)
    return True


def _release_cohort(uid: str, cohort: _RetryCohort, reason: str) -> None:
    with _coalescing_lock:
        if _cohorts.get(uid) is not cohort:
            return
        unresolved = cohort.unresolved
        if cohort.current is not None:
            try:
                unresolved = cohort.current.result().pending
            except Exception:
                pass
        dropped = len(cohort.pending | set(unresolved) | set(cohort.carried))
        _retire_cohort_locked(uid, cohort)
    if dropped:
        record_retry('late', 'skipped', reason, dropped)


def _signal_cohort(cohort: _RetryCohort) -> None:
    # Slot cleanup can run on the storage worker's thread.
    if cohort.loop is not None:
        try:
            cohort.loop.call_soon_threadsafe(cohort.wake.set)
        except RuntimeError:
            pass  # A closed loop cannot run remaining work during process shutdown.


def _wake_oldest_cohort_locked() -> None:
    for waiting in _cohorts.values():
        if not waiting.acquired:
            _signal_cohort(waiting)
            return


def _retire_cohort_locked(uid: str, cohort: _RetryCohort) -> None:
    del _cohorts[uid]
    if cohort.acquired:
        _slots.release()
    _wake_oldest_cohort_locked()


def _try_admit_cohort(cohort: _RetryCohort) -> bool:
    with _coalescing_lock:
        oldest = next((c for c in _cohorts.values() if not c.acquired), None)
        if oldest is not cohort or time.monotonic() > cohort.deadline or not _slots.acquire(blocking=False):
            return False
        cohort.acquired = True
        # A second free slot can admit the next arrival immediately.
        _wake_oldest_cohort_locked()
        return True


async def _wait_for_cohort_signal(cohort: _RetryCohort, seconds: float) -> bool:
    try:
        await asyncio.wait_for(cohort.wake.wait(), timeout=seconds)
        return True
    except asyncio.TimeoutError:
        return False


async def _admit_cohort(cohort: _RetryCohort) -> bool:
    for delay in (0, *ADMISSION_RECHECK_DELAYS):
        poll_at = min(cohort.deadline, time.monotonic() + delay)
        while time.monotonic() <= cohort.deadline:
            cohort.wake.clear()
            if _try_admit_cohort(cohort):
                return True
            if not delay:
                record_retry('late', 'deferred', 'slot_limit', cohort.initial_count)
            left = poll_at - time.monotonic()
            if left <= 0 or not await _wait_for_cohort_signal(cohort, left):
                break
            # Signals retry admission immediately without consuming a fallback
            # poll or extending the original deadline. FIFO gates every attempt.
    return _try_admit_cohort(cohort)


async def _wait_for_coalesced_pending(cohort: _RetryCohort, seconds: float) -> None:
    recheck_at = time.monotonic() + seconds
    while True:
        with _coalescing_lock:
            cohort.wake.clear()
            if cohort.pending:
                return
        left = recheck_at - time.monotonic()
        if left <= 0 or not await _wait_for_cohort_signal(cohort, left):
            return


async def _run_arrivals_before_recheck(
    uid: str, cohort: _RetryCohort, *, recheck_at: float, remaining_passes: int
) -> int:
    """Arrival wakes run fresh IDs only; the scheduled old-row recheck stays due."""
    while remaining_passes:
        left = recheck_at - time.monotonic()
        if left <= 0:
            break
        await _wait_for_coalesced_pending(cohort, left)
        with _coalescing_lock:
            if time.monotonic() >= recheck_at or not cohort.pending:
                break
            candidates = tuple(sorted(cohort.pending))
            cohort.pending.clear()
            cohort.wake.clear()
            # Cancellation while this worker runs must also retain/account the
            # older processing IDs that are waiting for their scheduled recheck.
            cohort.carried = cohort.unresolved
            cohort.unresolved = candidates
        cohort.current = submit_with_context(
            storage_executor, partial(_retry_batch, remaining_passes=remaining_passes), uid, candidates
        )
        result = await asyncio.shield(asyncio.wrap_future(cohort.current))
        with _coalescing_lock:
            cohort.unresolved = tuple(sorted(set(cohort.carried) | set(result.pending)))
            cohort.carried = ()
            cohort.current = None
        remaining_passes -= result.attempted
    return remaining_passes


async def _run_cohort(uid: str, cohort: _RetryCohort) -> None:
    if not await _admit_cohort(cohort):
        _release_cohort(uid, cohort, 'queue_expired')
        return

    remaining_passes = MAX_LATE_IDENTITY_PASSES
    completion_deadline = time.monotonic() + sum(COMPLETION_RECHECK_DELAYS)
    while True:
        with _coalescing_lock:
            if not cohort.pending:
                # Remove atomically with the empty check: a concurrent submit
                # either joined this cohort or creates the next one.
                _retire_cohort_locked(uid, cohort)
                return
            candidates = tuple(sorted(cohort.pending))
            cohort.pending.clear()
            cohort.wake.clear()
            cohort.unresolved = candidates
        if not remaining_passes or time.monotonic() > completion_deadline:
            cohort.unresolved = candidates
            _release_cohort(uid, cohort, 'pass_limit' if not remaining_passes else 'queue_expired')
            return
        cohort.unresolved = candidates
        for delay in (0, *COMPLETION_RECHECK_DELAYS):
            if delay:
                left = completion_deadline - time.monotonic()
                if left < 0:
                    break
                remaining_passes = await _run_arrivals_before_recheck(
                    uid,
                    cohort,
                    recheck_at=min(time.monotonic() + delay, completion_deadline),
                    remaining_passes=remaining_passes,
                )
                if not remaining_passes or time.monotonic() > completion_deadline:
                    break
            with _coalescing_lock:
                # Fresh arrivals join this round while older rows still wait
                # for completion. Neither deadline nor pass budget is reset.
                cohort.unresolved = tuple(sorted(set(cohort.unresolved) | cohort.pending))
                cohort.pending.clear()
                cohort.wake.clear()
            cohort.current = submit_with_context(
                storage_executor,
                partial(_retry_batch, remaining_passes=remaining_passes),
                uid,
                cohort.unresolved,
            )
            result = await asyncio.shield(asyncio.wrap_future(cohort.current))
            cohort.current = None
            cohort.unresolved = result.pending
            remaining_passes -= result.attempted
            if not result.pending:
                break
            if not remaining_passes:
                break
        if cohort.unresolved:
            record_retry(
                'late', 'skipped', 'pass_limit' if not remaining_passes else 'not_completed', len(cohort.unresolved)
            )
            cohort.unresolved = ()
