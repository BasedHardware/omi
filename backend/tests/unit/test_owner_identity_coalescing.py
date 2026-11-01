"""Exercise bounded UID ownership, budgets and cancellation on the real scheduler."""

import asyncio
from concurrent.futures import Future
import threading
from types import SimpleNamespace

import pytest

from utils import executors
from utils.conversations import speaker_identity_retry as retry, speaker_resolution as stage
from utils.observability.owner_identity_retry import OWNER_IDENTITY_RETRY


def count(stage, reason):
    return OWNER_IDENTITY_RETRY.labels(**{'pass': 'late', 'stage': stage, 'reason': reason})._value.get()


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv('OWNER_IDENTITY_RETRY_COALESCE_ENABLED', 'true')
    monkeypatch.setattr(retry, '_cohorts', {})
    monkeypatch.setattr(retry, 'time', SimpleNamespace(monotonic=lambda: 0))
    monkeypatch.setattr(retry, '_slots', threading.BoundedSemaphore(2))
    monkeypatch.setattr(retry, '_waiting_slots', threading.BoundedSemaphore(2))
    monkeypatch.setattr(retry, '_active', set())
    monkeypatch.setattr(retry, '_waiting', set())
    monkeypatch.setattr(retry, 'COMPLETION_RECHECK_DELAYS', ())


async def settle():
    for _ in range(24):
        await asyncio.sleep(0)


async def test_new_ids_merge_one_uid_worker_without_repeating_reads(monkeypatch):
    futures, calls = [], []

    def submit(pool, fn, uid, ids):
        calls.append((uid, ids))
        f = Future()
        futures.append(f)
        return f

    monkeypatch.setattr(retry, 'submit_with_context', submit)
    assert retry.schedule_completed_identity_retries('u', ['a'])
    await settle()
    assert retry.schedule_completed_identity_retries('u', ['a', 'b'])
    assert retry.schedule_completed_identity_retries('u', ['b', 'c'])
    assert calls == [('u', ('a',))]
    futures[0].set_result(retry.RetryRound((), 1))
    await settle()
    assert calls == [('u', ('a',)), ('u', ('b', 'c'))]
    assert retry.schedule_completed_identity_retries('u', ['a', 'b', 'c'])
    futures[1].set_result(retry.RetryRound((), 2))
    await settle()
    assert not retry._cohorts
    assert retry._slots.acquire(blocking=False) and retry._slots.acquire(blocking=False)


async def test_queue_uid_candidate_and_lifetime_pass_caps(monkeypatch):
    monkeypatch.setattr(retry, 'ADMISSION_RECHECK_DELAYS', ())
    monkeypatch.setattr(retry, 'submit_with_context', lambda *a: pytest.fail('waiting worker'))
    assert retry._slots.acquire(blocking=False) and retry._slots.acquire(blocking=False)
    before = count('skipped', 'scan_limit'), count('skipped', 'queue_limit')
    for i in range(retry.MAX_QUEUED_UIDS):
        assert retry.schedule_completed_identity_retries(str(i), [f'c{n:03}' for n in range(130)])
        assert not retry.schedule_completed_identity_retries(str(i), ['new'])
    assert not retry.schedule_completed_identity_retries('overflow', ['a'])
    assert len(retry._cohorts) == 16
    assert sum(len(c.seen) for c in retry._cohorts.values()) == 16 * 128
    assert count('skipped', 'scan_limit') - before[0] == 16 * 3
    assert count('skipped', 'queue_limit') - before[1] == 1
    await settle()
    assert not retry._cohorts


async def test_merged_work_shares_eight_pass_budget(monkeypatch):
    futures, budgets = [], []

    def submit(pool, fn, uid, ids):
        budgets.append(fn.keywords['remaining_passes'])
        f = Future()
        futures.append(f)
        return f

    monkeypatch.setattr(retry, 'submit_with_context', submit)
    assert retry.schedule_completed_identity_retries('u', ['a'])
    await settle()
    assert retry.schedule_completed_identity_retries('u', ['b'])
    futures[0].set_result(retry.RetryRound((), 7))
    await settle()
    assert budgets == [8, 1]
    assert retry.schedule_completed_identity_retries('u', ['c'])
    before = count('skipped', 'pass_limit')
    futures[1].set_result(retry.RetryRound((), 1))
    await settle()
    assert len(futures) == 2 and not retry._cohorts
    assert count('skipped', 'pass_limit') == before + 1


async def test_cancel_before_start_accounts_once_and_releases_metadata(monkeypatch):
    monkeypatch.setattr(retry, 'submit_with_context', lambda *a: pytest.fail('cancelled worker'))
    before = count('skipped', 'cancelled')
    existing = set(executors._background_tasks)
    assert retry.schedule_completed_identity_retries('u', ['a', 'b'])
    task = (executors._background_tasks - existing).pop()
    task.cancel()
    await settle()
    assert not retry._cohorts
    assert count('skipped', 'cancelled') == before + 2
    assert retry._slots.acquire(blocking=False) and retry._slots.acquire(blocking=False)


async def test_cancel_running_worker_retains_slot_uid_then_counts_only_unfinished(monkeypatch):
    f = Future()
    monkeypatch.setattr(retry, 'submit_with_context', lambda *a: f)
    before = count('skipped', 'cancelled')
    existing = set(executors._background_tasks)
    assert retry.schedule_completed_identity_retries('u', ['a', 'processing'])
    task = (executors._background_tasks - existing).pop()
    await settle()
    assert retry.schedule_completed_identity_retries('u', ['queued'])
    task.cancel()
    await settle()
    assert len(retry._cohorts) == 1 and not f.cancelled()
    assert retry._slots.acquire(blocking=False)
    assert not retry._slots.acquire(blocking=False)
    retry._slots.release()
    f.set_result(retry.RetryRound(('processing',), 1))
    await settle()
    assert not retry._cohorts
    assert count('skipped', 'cancelled') == before + 2
    assert retry._slots.acquire(blocking=False) and retry._slots.acquire(blocking=False)


async def test_submission_error_accounts_and_releases(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('synthetic')

    monkeypatch.setattr(retry, 'start_background_task', fail)
    before = count('skipped', 'submission_error')
    with pytest.raises(RuntimeError):
        retry.schedule_completed_identity_retries('u', ['a'])
    assert not retry._cohorts and count('skipped', 'submission_error') == before + 1


@pytest.mark.parametrize('value', [None, 'false', 'invalid'])
async def test_flag_off_uses_exact_legacy_two_batches_two_waiters(monkeypatch, value):
    if value is None:
        monkeypatch.delenv('OWNER_IDENTITY_RETRY_COALESCE_ENABLED', raising=False)
    else:
        monkeypatch.setenv('OWNER_IDENTITY_RETRY_COALESCE_ENABLED', value)
    monkeypatch.setattr(retry, '_start_batch', lambda *a: None)
    monkeypatch.setattr(retry, '_wait_for_admission', lambda *a: None)
    assert retry.schedule_completed_identity_retries('u', ['a'])
    assert retry.schedule_completed_identity_retries('u', ['b'])
    assert retry.schedule_completed_identity_retries('u', ['c'])
    assert retry.schedule_completed_identity_retries('u', ['d'])
    assert not retry.schedule_completed_identity_retries('u', ['e'])
    assert not retry._cohorts
    assert len(retry._active) == len(retry._waiting) == 2


async def test_coalesced_admission_reads_fresh_revision_and_policy(monkeypatch):
    f = Future()
    calls, repairs = [], []
    row = dict(id='queued', status='completed', private_cloud_sync_enabled=True, updated_at='old')

    def submit(pool, fn, uid, ids):
        if not calls:
            calls.append(ids)
            return f
        calls.append(ids)
        result = Future()
        result.set_result(fn(uid, ids))
        return result

    monkeypatch.setattr(retry, 'submit_with_context', submit)
    monkeypatch.setattr(stage.conversations_db, 'get_conversation', lambda *a: dict(row))
    monkeypatch.setattr(
        stage, 'refresh_completed_speaker_identity', lambda *a, candidate: repairs.append(candidate['updated_at'])
    )
    assert retry.schedule_completed_identity_retries('u', ['active'])
    await settle()
    assert retry.schedule_completed_identity_retries('u', ['queued'])
    row['updated_at'] = 'fresh'
    f.set_result(retry.RetryRound((), 1))
    await settle()
    assert repairs == ['fresh'] and not retry._cohorts
    row['deleted'] = True
    assert retry.schedule_completed_identity_retries('u', ['queued'])
    await settle()
    assert repairs == ['fresh'] and not retry._cohorts


async def test_cancel_during_completion_sleep_counts_pending_once(monkeypatch):
    f = Future()
    f.set_result(retry.RetryRound(('a',), 0))
    monkeypatch.setattr(retry, 'submit_with_context', lambda *a: f)
    monkeypatch.setattr(retry, 'COMPLETION_RECHECK_DELAYS', (60,))
    before = count('skipped', 'cancelled')
    existing = set(executors._background_tasks)
    assert retry.schedule_completed_identity_retries('u', ['a'])
    task = (executors._background_tasks - existing).pop()
    await settle()
    assert retry.schedule_completed_identity_retries('u', ['b'])
    task.cancel()
    await settle()
    assert not retry._cohorts and count('skipped', 'cancelled') == before + 2
    assert retry._slots.acquire(blocking=False) and retry._slots.acquire(blocking=False)


async def test_new_submissions_do_not_extend_admission_deadline(monkeypatch):
    clock = [0]
    monkeypatch.setattr(retry, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    assert retry._slots.acquire(blocking=False) and retry._slots.acquire(blocking=False)
    before = count('skipped', 'queue_expired')
    assert retry.schedule_completed_identity_retries('u', ['a'])
    clock[0] = sum(retry.ADMISSION_RECHECK_DELAYS) + 1
    assert retry.schedule_completed_identity_retries('u', ['b'])
    await settle()
    assert not retry._cohorts and count('skipped', 'queue_expired') == before + 2


async def test_coalesced_pending_cannot_reset_completion_deadline(monkeypatch):
    clock = [0]
    monkeypatch.setattr(retry, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(retry, 'COMPLETION_RECHECK_DELAYS', (5,))
    f = Future()
    monkeypatch.setattr(retry, 'submit_with_context', lambda *a: f)
    before = count('skipped', 'queue_expired')
    assert retry.schedule_completed_identity_retries('u', ['a'])
    await settle()
    assert retry.schedule_completed_identity_retries('u', ['b'])
    clock[0] = 6
    f.set_result(retry.RetryRound((), 1))
    await settle()
    assert not retry._cohorts and count('skipped', 'queue_expired') == before + 1


async def test_two_workers_and_queued_uid_recover_without_extra_thread(monkeypatch):
    futures = []
    # Polling cannot account for progress within this test's event-loop turns.
    monkeypatch.setattr(retry, 'ADMISSION_RECHECK_DELAYS', (60,))

    def submit(*args):
        f = Future()
        futures.append(f)
        return f

    monkeypatch.setattr(retry, 'submit_with_context', submit)
    before = count('deferred', 'slot_limit')
    for i in range(3):
        assert retry.schedule_completed_identity_retries(str(i), ['a'])
    await settle()
    assert len(futures) == 2 and count('deferred', 'slot_limit') == before + 1
    futures[0].set_result(retry.RetryRound((), 1))
    await settle()
    assert len(futures) == 3
    for f in futures[1:]:
        f.set_result(retry.RetryRound((), 1))
    await settle()
    assert not retry._cohorts
    assert retry._slots.acquire(blocking=False) and retry._slots.acquire(blocking=False)


async def test_worker_submission_failure_releases_acquired_slot(monkeypatch):
    def fail(*args):
        raise RuntimeError('synthetic')

    monkeypatch.setattr(retry, 'submit_with_context', fail)
    before = count('skipped', 'submission_error')
    assert retry.schedule_completed_identity_retries('u', ['a', 'b'])
    await settle()
    assert not retry._cohorts and count('skipped', 'submission_error') == before + 2
    assert retry._slots.acquire(blocking=False) and retry._slots.acquire(blocking=False)


async def test_merged_completed_arrival_runs_while_previous_row_remains_processing(monkeypatch):
    monkeypatch.setattr(retry, 'COMPLETION_RECHECK_DELAYS', (60, 60))
    rounds, repairs = [], []

    def read(uid, cid):
        return dict(
            id=cid,
            status='processing' if cid == 'older' else 'completed',
            private_cloud_sync_enabled=True,
            updated_at='fresh',
        )

    def submit(pool, fn, uid, ids):
        rounds.append(ids)
        f = Future()
        f.set_result(fn(uid, ids))
        return f

    monkeypatch.setattr(retry, 'submit_with_context', submit)
    monkeypatch.setattr(stage.conversations_db, 'get_conversation', read)
    monkeypatch.setattr(stage, 'refresh_completed_speaker_identity', lambda uid, cid, **kw: repairs.append(cid))
    existing = set(executors._background_tasks)
    assert retry.schedule_completed_identity_retries('u', ['older'])
    task = (executors._background_tasks - existing).pop()
    await settle()
    assert rounds == [('older',)]
    assert retry.schedule_completed_identity_retries('u', ['arrival'])
    await settle()
    assert rounds == [('older',), ('arrival',)]
    assert repairs == ['arrival']
    assert retry._cohorts['u'].unresolved == ('older',)
    task.cancel()
    await settle()
    assert not retry._cohorts


async def test_fifo_admission_even_if_background_tasks_start_in_reverse(monkeypatch):
    monkeypatch.setattr(retry, 'ADMISSION_RECHECK_DELAYS', (60,))
    coros, tasks, calls, futures = [], [], [], []
    start = retry.start_background_task

    def defer(coro, **kw):
        # A Future supplies the same done-callback seam without starting work.
        task = asyncio.get_running_loop().create_future()
        tasks.append(task)
        coros.append(coro)
        return task

    def submit(pool, fn, uid, ids):
        calls.append(uid)
        f = Future()
        futures.append(f)
        return f

    monkeypatch.setattr(retry, 'start_background_task', defer)
    monkeypatch.setattr(retry, 'submit_with_context', submit)
    for i in range(4):
        assert retry.schedule_completed_identity_retries(str(i), ['a'])
    live = [start(coro, name='fifo_test') for coro in reversed(coros)]
    await settle()
    assert calls == ['0', '1']  # Arrival order, independent of task start order.
    futures[1].set_result(retry.RetryRound((), 1))
    await settle()
    assert calls == ['0', '1', '2']
    futures[0].set_result(retry.RetryRound((), 1))
    await settle()
    assert calls == ['0', '1', '2', '3']
    for f in futures[2:]:
        f.set_result(retry.RetryRound((), 1))
    await asyncio.gather(*live)
    for task in tasks:
        task.set_result(None)
    await settle()
    assert not retry._cohorts


async def test_waiting_cancellation_wakes_next_arrival(monkeypatch):
    monkeypatch.setattr(retry, 'ADMISSION_RECHECK_DELAYS', (60,))
    assert retry._slots.acquire(blocking=False) and retry._slots.acquire(blocking=False)
    tasks, futures, calls = [], [], []

    def submit(pool, fn, uid, ids):
        calls.append(uid)
        f = Future()
        futures.append(f)
        return f

    monkeypatch.setattr(retry, 'submit_with_context', submit)
    for uid in ['oldest', 'next']:
        existing = set(executors._background_tasks)
        assert retry.schedule_completed_identity_retries(uid, ['a'])
        tasks.append((executors._background_tasks - existing).pop())
    await settle()
    retry._slots.release()  # A free slot alone cannot let the younger waiter bypass FIFO.
    assert not retry._try_admit_cohort(retry._cohorts['next'])
    tasks[0].cancel()
    await settle()
    assert calls == ['next']
    futures[0].set_result(retry.RetryRound((), 1))
    await settle()
    assert not retry._cohorts
    retry._slots.release()


async def test_slot_release_from_worker_thread_wakes_oldest_waiter(monkeypatch):
    monkeypatch.setattr(retry, 'ADMISSION_RECHECK_DELAYS', (60,))
    futures, calls, tasks = [], [], []

    def submit(pool, fn, uid, ids):
        calls.append(uid)
        f = Future()
        futures.append(f)
        return f

    monkeypatch.setattr(retry, 'submit_with_context', submit)
    for uid in ['active', 'other', 'waiting']:
        existing = set(executors._background_tasks)
        assert retry.schedule_completed_identity_retries(uid, ['a'])
        tasks.append((executors._background_tasks - existing).pop())
    await settle()
    tasks[0].cancel()
    await settle()
    worker = threading.Thread(target=futures[0].set_result, args=(retry.RetryRound((), 1),))
    worker.start()
    worker.join()
    await settle()
    assert calls == ['active', 'other', 'waiting']
    for f in futures[1:]:
        f.set_result(retry.RetryRound((), 1))
    await settle()
    assert not retry._cohorts


@pytest.mark.parametrize('reason', ['read_error', 'processing_error', 'not_completed'])
async def test_resubmits_after_transient_exit_are_observed_without_resetting_budget(monkeypatch, reason):
    monkeypatch.setattr(retry, 'COMPLETION_RECHECK_DELAYS', (60,))

    def read(uid, cid):
        if cid == 'exited' and reason == 'read_error':
            raise RuntimeError('synthetic')
        return dict(
            id=cid,
            status='processing' if cid == 'pending' else 'failed',
            private_cloud_sync_enabled=True,
            updated_at='fresh',
        )

    skip = stage.completed_identity_retry_skip_reason

    def classify(raw):
        if raw['id'] == 'exited' and reason == 'processing_error':
            raise RuntimeError('synthetic')
        return skip(raw)

    def submit(pool, fn, uid, ids):
        f = Future()
        f.set_result(fn(uid, ids))
        return f

    monkeypatch.setattr(stage.conversations_db, 'get_conversation', read)
    monkeypatch.setattr(stage, 'completed_identity_retry_skip_reason', classify)
    monkeypatch.setattr(retry, 'submit_with_context', submit)
    existing = set(executors._background_tasks)
    before = count('skipped', reason), count('skipped', 'cohort_seen'), count('entry', 'candidate')
    assert retry.schedule_completed_identity_retries('u', ['exited', 'pending'])
    task = (executors._background_tasks - existing).pop()
    await settle()
    assert count('skipped', reason) == before[0] + 1
    assert retry.schedule_completed_identity_retries('u', ['exited'])
    assert count('skipped', 'cohort_seen') == before[1] + 1
    assert count('entry', 'candidate') == before[2] + 3
    assert len(retry._cohorts['u'].seen) == 2 and not retry._cohorts['u'].pending
    task.cancel()
    await settle()
    assert not retry._cohorts


async def test_admission_poll_fallback_recovers_when_release_signal_is_missing(monkeypatch):
    assert retry._slots.acquire(blocking=False) and retry._slots.acquire(blocking=False)
    futures, delays = [], []

    async def timeout_without_signal(cohort, seconds):
        delays.append(seconds)
        retry._slots.release()
        return False

    def submit(*args):
        f = Future()
        futures.append(f)
        return f

    monkeypatch.setattr(retry, '_wait_for_cohort_signal', timeout_without_signal)
    monkeypatch.setattr(retry, 'submit_with_context', submit)
    assert retry.schedule_completed_identity_retries('u', ['a'])
    await settle()
    assert delays == [5] and len(futures) == 1
    futures[0].set_result(retry.RetryRound((), 1))
    await settle()
    assert not retry._cohorts
    retry._slots.release()


@pytest.mark.parametrize('complete_at_deadline', [True, False])
async def test_arrival_wakes_preserve_all_scheduled_old_row_rechecks(monkeypatch, complete_at_deadline):
    clock, arrivals, reads, repairs = [0.0], list(range(1, 7)), [], []
    monkeypatch.setattr(retry, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(retry, 'COMPLETION_RECHECK_DELAYS', (5, 15, 30, 60, 120))

    async def next_event(cohort, seconds):
        due = clock[0] + seconds
        if arrivals and arrivals[0] < due:
            clock[0] = arrivals.pop(0)
            assert retry.schedule_completed_identity_retries('u', [f'arrival{int(clock[0])}'])
        else:
            clock[0] = due

    def read(uid, cid):
        reads.append((cid, clock[0]))
        completed = cid != 'older' or (complete_at_deadline and clock[0] >= 230)
        return dict(
            id=cid,
            status='completed' if completed else 'processing',
            private_cloud_sync_enabled=True,
            updated_at='fresh',
        )

    def submit(pool, fn, uid, ids):
        f = Future()
        f.set_result(fn(uid, ids))
        return f

    monkeypatch.setattr(retry, '_wait_for_coalesced_pending', next_event)
    monkeypatch.setattr(stage.conversations_db, 'get_conversation', read)
    monkeypatch.setattr(stage, 'refresh_completed_speaker_identity', lambda uid, cid, **kw: repairs.append(cid))
    monkeypatch.setattr(retry, 'submit_with_context', submit)
    existing = set(executors._background_tasks)
    before = count('skipped', 'not_completed')
    assert retry.schedule_completed_identity_retries('u', ['older'])
    task = (executors._background_tasks - existing).pop()
    await asyncio.wait_for(task, 1)
    await settle()
    assert [when for cid, when in reads if cid == 'older'] == [0, 5, 20, 50, 110, 230]
    assert repairs[:6] == [f'arrival{i}' for i in range(1, 7)]
    assert ('older' in repairs) == complete_at_deadline
    assert count('skipped', 'not_completed') == before + (not complete_at_deadline)
    assert clock[0] == 230 and not retry._cohorts


@pytest.mark.parametrize('fresh_still_processing', [True, False])
async def test_cancel_arrival_worker_accounts_carried_ids_and_in_flight_resubmits(monkeypatch, fresh_still_processing):
    monkeypatch.setattr(retry, 'COMPLETION_RECHECK_DELAYS', (60,))
    first, fresh = Future(), Future()
    first.set_result(retry.RetryRound(('older',), 0))
    futures = iter([first, fresh])
    monkeypatch.setattr(retry, 'submit_with_context', lambda *a: next(futures))
    existing = set(executors._background_tasks)
    assert retry.schedule_completed_identity_retries('u', ['older'])
    task = (executors._background_tasks - existing).pop()
    await settle()
    assert retry.schedule_completed_identity_retries('u', ['fresh'])
    await settle()
    assert retry._cohorts['u'].carried == ('older',)
    assert retry._cohorts['u'].unresolved == ('fresh',)
    before = count('skipped', 'cohort_seen'), count('deferred', 'in_flight'), count('entry', 'candidate')
    assert retry.schedule_completed_identity_retries('u', ['older', 'fresh'])
    assert count('skipped', 'cohort_seen') == before[0]
    assert count('deferred', 'in_flight') == before[1] + 2
    assert count('entry', 'candidate') == before[2]
    assert retry.schedule_completed_identity_retries('u', ['queued'])
    cancelled_before = count('skipped', 'cancelled')
    task.cancel()
    await settle()
    assert not fresh.cancelled() and retry._cohorts
    fresh.set_result(retry.RetryRound(('fresh',) if fresh_still_processing else (), int(not fresh_still_processing)))
    await settle()
    assert count('skipped', 'cancelled') == cancelled_before + 2 + fresh_still_processing
    assert not retry._cohorts
    assert retry._slots.acquire(blocking=False) and retry._slots.acquire(blocking=False)


async def test_in_flight_duplicates_are_coalescing_and_terminal_duplicates_match_entries(monkeypatch):
    f = Future()
    monkeypatch.setattr(retry, 'submit_with_context', lambda *a: f)
    existing = set(executors._background_tasks)
    assert retry.schedule_completed_identity_retries('u', ['terminal', 'older'])
    task = (executors._background_tasks - existing).pop()
    monkeypatch.setattr(retry, 'COMPLETION_RECHECK_DELAYS', (60,))
    await settle()
    before = count('entry', 'candidate'), count('skipped', 'cohort_seen'), count('deferred', 'in_flight')
    assert retry.schedule_completed_identity_retries('u', ['terminal', 'terminal', 'older'])
    assert count('entry', 'candidate') == before[0]
    assert count('skipped', 'cohort_seen') == before[1]
    assert count('deferred', 'in_flight') == before[2] + 2
    f.set_result(retry.RetryRound(('older',), 0))
    await settle()
    assert retry.schedule_completed_identity_retries('u', ['terminal', 'older'])
    assert count('entry', 'candidate') == before[0] + 1
    assert count('skipped', 'cohort_seen') == before[1] + 1
    assert count('deferred', 'in_flight') == before[2] + 3
    task.cancel()
    await settle()
    assert not retry._cohorts


async def test_arrival_only_rounds_share_original_eight_pass_budget(monkeypatch):
    clock, arrivals, attempts = [0.0], list(range(1, 9)), []
    monkeypatch.setattr(retry, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(retry, 'COMPLETION_RECHECK_DELAYS', (5, 15, 30, 60, 120))

    async def next_event(cohort, seconds):
        due = clock[0] + seconds
        if arrivals and arrivals[0] < due:
            clock[0] = arrivals.pop(0)
            assert retry.schedule_completed_identity_retries('u', [f'arrival{int(clock[0])}'])
        else:
            clock[0] = due

    def read(uid, cid):
        return dict(
            id=cid,
            status='processing' if cid == 'older' else 'completed',
            private_cloud_sync_enabled=True,
            updated_at='fresh',
        )

    def submit(pool, fn, uid, ids):
        f = Future()
        f.set_result(fn(uid, ids))
        return f

    monkeypatch.setattr(retry, '_wait_for_coalesced_pending', next_event)
    monkeypatch.setattr(stage.conversations_db, 'get_conversation', read)
    monkeypatch.setattr(stage, 'refresh_completed_speaker_identity', lambda uid, cid, **kw: attempts.append(cid))
    monkeypatch.setattr(retry, 'submit_with_context', submit)
    existing = set(executors._background_tasks)
    before = count('skipped', 'pass_limit'), count('skipped', 'not_completed')
    assert retry.schedule_completed_identity_retries('u', ['older'])
    task = (executors._background_tasks - existing).pop()
    await asyncio.wait_for(task, 1)
    await settle()
    assert attempts == [f'arrival{i}' for i in range(1, 9)]
    assert clock[0] == 8 and not retry._cohorts
    assert count('skipped', 'pass_limit') == before[0] + 1
    assert count('skipped', 'not_completed') == before[1]
