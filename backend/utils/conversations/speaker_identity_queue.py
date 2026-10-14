"""Process-local, bounded UID cohorts for late identity repair.

This queue is deliberately not durable: expiry, overflow and process shutdown
can lose work. Admission never raises worker concurrency or refreshes a cohort's
candidate/pass budget when another session submits IDs.
"""

import asyncio
from concurrent.futures import Future
from dataclasses import dataclass, field
from functools import partial
import threading
import time
from typing import Iterable, Optional

from utils.conversations import speaker_identity_retry as retry
from utils.executors import start_background_task
from utils.observability.owner_identity_retry import record_retry

MAX_QUEUED_UIDS = 16
_lock = threading.Lock()


@dataclass
class Cohort:
    pending: set[str] = field(default_factory=set)
    seen: set[str] = field(default_factory=set)
    deadline: float = 0
    acquired: bool = False
    initial_count: int = 0
    current: Optional[Future] = None
    unresolved: tuple[str, ...] = ()


_cohorts: dict[str, Cohort] = {}


def schedule(uid: str, conversation_ids: Iterable[str]) -> bool:
    known = sorted(set(conversation_ids))
    with _lock:
        cohort = _cohorts.get(uid)
        known = [cid for cid in known if cohort is None or cid not in cohort.seen]
        if not known:
            return True
        record_retry('late', 'entry', 'candidate', len(known))
        if cohort is None and len(_cohorts) >= MAX_QUEUED_UIDS:
            record_retry('late', 'skipped', 'queue_limit', len(known))
            return False
        created = cohort is None
        if cohort is None:
            cohort = Cohort(deadline=time.monotonic() + sum(retry.ADMISSION_RECHECK_DELAYS))
            _cohorts[uid] = cohort
        room = retry.MAX_LATE_IDENTITY_CANDIDATES - len(cohort.seen)
        candidates = known[:room]
        cohort.seen.update(candidates)
        cohort.pending.update(candidates)
        if created:
            cohort.initial_count = len(candidates)
    if len(known) > len(candidates):
        record_retry('late', 'skipped', 'scan_limit', len(known) - len(candidates))
    if not created:
        record_retry('late', 'deferred', 'coalesced', len(candidates))
        return bool(candidates)
    coro = _run(uid, cohort)
    try:
        task = start_background_task(coro, name='speaker_identity_coalesced')
    except Exception:
        coro.close()
        _release(uid, cohort, 'submission_error')
        raise

    # Runs even for cancellation before the coroutine starts. A running worker
    # retains both UID ownership and its slot until its shielded Future finishes.
    def finished(task):
        reason = 'cancelled' if task.cancelled() else 'submission_error'
        if cohort.current is not None and not cohort.current.done():
            cohort.current.add_done_callback(lambda _: _release(uid, cohort, reason))
        else:
            _release(uid, cohort, reason)

    task.add_done_callback(finished)
    return True


def _release(uid: str, cohort: Cohort, reason: str) -> None:
    with _lock:
        if _cohorts.get(uid) is not cohort:
            return
        unresolved = cohort.unresolved
        if cohort.current is not None:
            try:
                unresolved = cohort.current.result().pending
            except Exception:
                pass
        dropped = len(cohort.pending | set(unresolved))
        del _cohorts[uid]
        if cohort.acquired:
            retry._slots.release()
    if dropped:
        record_retry('late', 'skipped', reason, dropped)


async def _run(uid: str, cohort: Cohort) -> None:
    for delay in (0, *retry.ADMISSION_RECHECK_DELAYS):
        remaining = cohort.deadline - time.monotonic()
        if remaining < 0:
            break
        if delay:
            await asyncio.sleep(min(delay, remaining))
        if time.monotonic() <= cohort.deadline and retry._slots.acquire(blocking=False):
            cohort.acquired = True
            break
        if not delay:
            record_retry('late', 'deferred', 'slot_limit', cohort.initial_count)
    if not cohort.acquired:
        _release(uid, cohort, 'queue_expired')
        return

    remaining_passes = retry.MAX_LATE_IDENTITY_PASSES
    completion_deadline = time.monotonic() + sum(retry.COMPLETION_RECHECK_DELAYS)
    while True:
        with _lock:
            if not cohort.pending:
                # Remove atomically with the empty check: a concurrent submit
                # either joined this cohort or creates the next one.
                _cohorts.pop(uid)
                retry._slots.release()
                return
            candidates = tuple(sorted(cohort.pending))
            cohort.pending.clear()
        if not remaining_passes or time.monotonic() > completion_deadline:
            cohort.unresolved = candidates
            _release(uid, cohort, 'pass_limit' if not remaining_passes else 'queue_expired')
            return
        cohort.unresolved = candidates
        for delay in (0, *retry.COMPLETION_RECHECK_DELAYS):
            if delay:
                left = completion_deadline - time.monotonic()
                if left < 0:
                    break
                await asyncio.sleep(min(delay, left))
                if time.monotonic() > completion_deadline:
                    break
            cohort.current = retry.submit_with_context(
                retry.storage_executor,
                partial(retry._retry_batch, remaining_passes=remaining_passes),
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
