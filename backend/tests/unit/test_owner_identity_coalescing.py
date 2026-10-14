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
    for _ in range(12):
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
    monkeypatch.setattr(retry, 'ADMISSION_RECHECK_DELAYS', (1,))
    sleepers = asyncio.Event()
    wake = asyncio.Event()

    async def pause(delay):
        sleepers.set()
        await wake.wait()

    monkeypatch.setattr(
        retry, 'asyncio', SimpleNamespace(sleep=pause, shield=asyncio.shield, wrap_future=asyncio.wrap_future)
    )

    def submit(*args):
        f = Future()
        futures.append(f)
        return f

    monkeypatch.setattr(retry, 'submit_with_context', submit)
    before = count('deferred', 'slot_limit')
    for i in range(3):
        assert retry.schedule_completed_identity_retries(str(i), ['a'])
    await sleepers.wait()
    assert len(futures) == 2 and count('deferred', 'slot_limit') == before + 1
    futures[0].set_result(retry.RetryRound((), 1))
    await settle()
    wake.set()
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
