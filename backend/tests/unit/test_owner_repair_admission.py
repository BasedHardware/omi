"""Bounded ID-only deferral never admits a third storage worker or bypasses fresh policy."""

import asyncio
from concurrent.futures import Future
from types import SimpleNamespace
import threading

import pytest

from utils import executors
from utils.conversations import speaker_identity_retry as retry, speaker_resolution as stage
from utils.observability.owner_identity_retry import OWNER_IDENTITY_RETRY


def count(stage_name, reason):
    return OWNER_IDENTITY_RETRY.labels(**{'pass': 'late', 'stage': stage_name, 'reason': reason})._value.get()


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(retry, '_slots', threading.BoundedSemaphore(2))
    monkeypatch.setattr(retry, '_waiting_slots', threading.BoundedSemaphore(2))
    monkeypatch.setattr(retry, '_active', set())
    monkeypatch.setattr(retry, '_waiting', set())
    monkeypatch.setattr(retry, 'COMPLETION_RECHECK_DELAYS', ())
    monkeypatch.setattr(retry, 'time', SimpleNamespace(monotonic=lambda: 0))


async def settle():
    for _ in range(6):
        await asyncio.sleep(0)


async def finish(futures):
    for future in futures:
        if not future.done():
            future.set_result(retry.RetryRound((), 0))
    await settle()
    tasks = list(executors._background_tasks)
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def test_two_workers_two_waiters_coalesce_and_expire_without_any_reads(monkeypatch):
    futures = []
    ready, release = asyncio.Event(), asyncio.Event()

    def submit(*args):
        future = Future()
        futures.append(future)
        return future

    async def blocked_delay(*args):
        ready.set()
        await release.wait()

    monkeypatch.setattr(retry, 'submit_with_context', submit)
    monkeypatch.setattr(retry, 'ADMISSION_RECHECK_DELAYS', (0,))
    # Patch only the admission sleeper; keep the test event loop's sleep available.
    monkeypatch.setattr(
        retry,
        'asyncio',
        SimpleNamespace(
            sleep=blocked_delay,
            shield=asyncio.shield,
            wrap_future=asyncio.wrap_future,
        ),
    )
    monkeypatch.setattr(stage.conversations_db, 'get_conversation', lambda *a: pytest.fail('waiting read'))
    before = {
        name: count(*name)
        for name in [
            ('entry', 'candidate'),
            ('deferred', 'slot_limit'),
            ('skipped', 'slot_limit'),
            ('skipped', 'scan_limit'),
        ]
    }
    assert retry.schedule_completed_identity_retries('u', ['a'])
    assert retry.schedule_completed_identity_retries('u', ['b'])
    candidates = [f'c{i:03}' for i in range(129)]
    assert retry.schedule_completed_identity_retries('u', candidates)
    assert retry.schedule_completed_identity_retries('u', ['d'])
    assert retry.schedule_completed_identity_retries('u', candidates[:128])  # Deduplicated while waiting.
    assert not retry.schedule_completed_identity_retries('u', ['e', 'e'])
    await ready.wait()
    assert len(futures) == 2 and len(retry._active) == 2
    assert len(retry._waiting) == 129  # 128 + one; overflow was never retained.
    release.set()
    await settle()
    assert not retry._waiting and len(futures) == 2
    assert {name: count(*name) - value for name, value in before.items()} == {
        ('entry', 'candidate'): 133,
        ('deferred', 'slot_limit'): 129,
        ('skipped', 'slot_limit'): 130,
        ('skipped', 'scan_limit'): 1,
    }
    await finish(futures)
    assert not retry._active


@pytest.mark.parametrize('policy', [{'private_cloud_sync_enabled': False}, {'deleted': True}, {'is_locked': True}])
async def test_admission_uses_fresh_policy_and_does_not_repair_disallowed_rows(monkeypatch, policy):
    futures, reads = [], []
    release = asyncio.Event()
    started = asyncio.Event()

    async def pause(*args):
        started.set()
        await release.wait()

    def submit(_executor, fn, *args):
        future = Future()
        futures.append(future)
        if len(futures) > 2:
            future.set_result(fn(*args))
        return future

    monkeypatch.setattr(
        retry, 'asyncio', SimpleNamespace(sleep=pause, shield=asyncio.shield, wrap_future=asyncio.wrap_future)
    )
    monkeypatch.setattr(retry, 'ADMISSION_RECHECK_DELAYS', (0,))
    monkeypatch.setattr(retry, 'submit_with_context', submit)
    row = dict(id='c', status='completed', private_cloud_sync_enabled=True, updated_at='revision')

    def read(*args):
        reads.append(dict(row))
        return dict(row)

    monkeypatch.setattr(stage.conversations_db, 'get_conversation', read)
    monkeypatch.setattr(stage, 'refresh_completed_speaker_identity', lambda *a, **kw: pytest.fail('policy bypass'))
    assert retry.schedule_completed_identity_retries('u', ['a'])
    assert retry.schedule_completed_identity_retries('u', ['b'])
    assert retry.schedule_completed_identity_retries('u', ['c'])
    await started.wait()
    assert not reads and len(futures) == 2
    row.update(policy)
    futures[0].set_result(retry.RetryRound((), 0))
    await settle()
    release.set()
    await settle()
    assert len(futures) == 3 and reads == [row]
    await finish(futures)
    assert not retry._waiting and not retry._active


async def test_cancelled_before_start_releases_only_waiter_capacity(monkeypatch):
    futures = []
    before = count('skipped', 'slot_limit')

    def submit(*args):
        f = Future()
        futures.append(f)
        return f

    monkeypatch.setattr(retry, 'submit_with_context', submit)
    assert retry.schedule_completed_identity_retries('u', ['a'])
    assert retry.schedule_completed_identity_retries('u', ['b'])
    existing = set(executors._background_tasks)
    assert retry.schedule_completed_identity_retries('u', ['c'])
    waiter = next(iter(set(executors._background_tasks) - existing))
    waiter.cancel()
    await settle()
    assert not retry._waiting and len(retry._active) == 2
    assert count('skipped', 'slot_limit') == before + 1
    assert not retry._slots.acquire(blocking=False)
    assert retry._waiting_slots.acquire(blocking=False)
    assert retry._waiting_slots.acquire(blocking=False)
    assert not retry._waiting_slots.acquire(blocking=False)
    retry._waiting_slots.release()
    retry._waiting_slots.release()
    await finish(futures)


async def test_cancel_during_sleep_records_one_terminal_skip_and_propagates(monkeypatch):
    futures = []
    sleeping = asyncio.Event()

    def submit(*args):
        future = Future()
        futures.append(future)
        return future

    async def pause(*args):
        sleeping.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(retry, 'submit_with_context', submit)
    monkeypatch.setattr(
        retry, 'asyncio', SimpleNamespace(sleep=pause, shield=asyncio.shield, wrap_future=asyncio.wrap_future)
    )
    monkeypatch.setattr(stage.conversations_db, 'get_conversation', lambda *a: pytest.fail('waiting read'))
    assert retry.schedule_completed_identity_retries('u', ['a'])
    assert retry.schedule_completed_identity_retries('u', ['b'])
    existing = set(executors._background_tasks)
    before = count('skipped', 'slot_limit')
    assert retry.schedule_completed_identity_retries('u', ['c', 'd'])
    waiter = next(iter(set(executors._background_tasks) - existing))
    await sleeping.wait()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    await settle()
    assert waiter.cancelled() and not retry._waiting
    assert count('skipped', 'slot_limit') == before + 2
    assert len(futures) == 2 and retry._active == {('u', 'a'), ('u', 'b')}
    assert not retry._slots.acquire(blocking=False)
    assert retry._waiting_slots.acquire(blocking=False)
    assert retry._waiting_slots.acquire(blocking=False)
    assert not retry._waiting_slots.acquire(blocking=False)
    retry._waiting_slots.release()
    retry._waiting_slots.release()
    assert not waiter.cancel()
    await finish(futures)
    assert count('skipped', 'slot_limit') == before + 2


async def test_expiry_removes_keys_before_terminal_record_and_keeps_same_turn_resubmit(monkeypatch):
    assert retry._slots.acquire(blocking=False)
    assert retry._slots.acquire(blocking=False)
    monkeypatch.setattr(retry, 'ADMISSION_RECHECK_DELAYS', (0,))
    monkeypatch.setattr(retry, 'submit_with_context', lambda *a, **kw: pytest.fail('waiting submission'))
    queued = []
    record = retry.record_retry
    before = count('entry', 'candidate')
    skipped_before = count('skipped', 'slot_limit')

    def resubmit_on_terminal(pass_name, stage_name, reason, amount=1):
        record(pass_name, stage_name, reason, amount)
        if stage_name == 'skipped' and reason == 'slot_limit':
            monkeypatch.setattr(retry, '_wait_for_admission', lambda u, c: queued.append((u, c)))
            retry.schedule_completed_identity_retries('u', ['c'])

    monkeypatch.setattr(retry, 'record_retry', resubmit_on_terminal)
    assert retry.schedule_completed_identity_retries('u', ['c'])
    await settle()
    assert queued == [('u', ('c',))]
    assert count('entry', 'candidate') == before + 2
    assert count('skipped', 'slot_limit') == skipped_before + 1
    assert retry._waiting == {('u', 'c')} and not retry._active
    # Only the old permit was released; the replacement still owns one.
    assert retry._waiting_slots.acquire(blocking=False)
    assert not retry._waiting_slots.acquire(blocking=False)
    retry._waiting_slots.release()
    retry._waiting.clear()
    retry._waiting_slots.release()


async def test_waiter_start_failure_releases_metadata_reservation(monkeypatch):
    monkeypatch.setattr(retry, '_slots', SimpleNamespace(acquire=lambda **kw: False))
    monkeypatch.setattr(
        retry, 'start_background_task', lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('synthetic'))
    )
    before = count('skipped', 'submission_error')
    with pytest.raises(RuntimeError, match='synthetic'):
        retry.schedule_completed_identity_retries('u', ['c'])
    assert not retry._waiting and not retry._active
    assert count('skipped', 'submission_error') == before + 1
    assert retry._waiting_slots.acquire(blocking=False)
    assert retry._waiting_slots.acquire(blocking=False)


async def test_handoff_cleanup_cannot_remove_a_new_waiter_for_the_same_key(monkeypatch):
    # Model an immediately finishing admitted worker and a competing new batch
    # before the first waiter's done callback runs.
    assert retry._slots.acquire(blocking=False)
    assert retry._slots.acquire(blocking=False)
    monkeypatch.setattr(retry, 'ADMISSION_RECHECK_DELAYS', (0,))
    queued = []
    skipped_before = count('skipped', 'slot_limit')

    def handoff(uid, candidates):
        retry._active.difference_update((uid, cid) for cid in candidates)
        retry._slots.release()
        assert retry._slots.acquire(blocking=False)  # Another worker takes the freed slot.
        monkeypatch.setattr(retry, '_wait_for_admission', lambda u, c: queued.append((u, c)))
        assert retry.schedule_completed_identity_retries(uid, candidates)

    monkeypatch.setattr(retry, '_start_batch', handoff)
    assert retry.schedule_completed_identity_retries('u', ['c'])
    retry._slots.release()
    await settle()
    assert queued == [('u', ('c',))]
    assert ('u', 'c') in retry._waiting
    assert count('skipped', 'slot_limit') == skipped_before
    # The fake replacement waiter owns its own reservation; test-local cleanup.
    retry._waiting.clear()
    retry._waiting_slots.release()


async def test_waiting_work_recovers_after_release_with_fresh_revision_and_eight_pass_cap(monkeypatch):
    futures, reads, repairs = [], [], []
    ready, release = asyncio.Event(), asyncio.Event()
    revision = ['before']

    async def pause(*args):
        ready.set()
        await release.wait()

    def submit(_executor, fn, *args):
        future = Future()
        futures.append(future)
        if len(futures) > 2:
            future.set_result(fn(*args))
        return future

    def read(uid, cid):
        reads.append(cid)
        return dict(id=cid, status='completed', private_cloud_sync_enabled=True, updated_at=revision[0])

    def repair(uid, cid, *, candidate):
        repairs.append((cid, candidate['updated_at']))
        return True

    monkeypatch.setattr(retry, 'ADMISSION_RECHECK_DELAYS', (0,))
    monkeypatch.setattr(
        retry, 'asyncio', SimpleNamespace(sleep=pause, shield=asyncio.shield, wrap_future=asyncio.wrap_future)
    )
    monkeypatch.setattr(retry, 'submit_with_context', submit)
    monkeypatch.setattr(stage.conversations_db, 'get_conversation', read)
    monkeypatch.setattr(stage, 'refresh_completed_speaker_identity', repair)
    assert retry.schedule_completed_identity_retries('u', ['a'])
    assert retry.schedule_completed_identity_retries('u', ['b'])
    assert retry.schedule_completed_identity_retries('u', [f'c{i:02}' for i in range(10)])
    await ready.wait()
    assert not reads and not repairs and len(futures) == 2
    revision[0] = 'after'
    futures[0].set_result(retry.RetryRound((), 0))
    await settle()
    release.set()
    await settle()
    assert len(futures) == 3
    assert reads == [f'c{i:02}' for i in range(8)]
    assert repairs == [(cid, 'after') for cid in reads]
    assert futures[2].result().attempted == retry.MAX_LATE_IDENTITY_PASSES == 8
    await finish(futures)
    assert not retry._active and not retry._waiting


async def test_deadline_includes_time_before_waiter_starts(monkeypatch):
    clock = [0]
    monkeypatch.setattr(retry, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(retry, '_slots', SimpleNamespace(acquire=lambda **kw: False))
    monkeypatch.setattr(retry, 'submit_with_context', lambda *a, **kw: pytest.fail('expired submission'))
    before = count('skipped', 'slot_limit')
    assert retry.schedule_completed_identity_retries('u', ['c'])
    clock[0] = sum(retry.ADMISSION_RECHECK_DELAYS) + 1
    await settle()
    assert not retry._waiting and not retry._active
    assert count('skipped', 'slot_limit') == before + 1


async def test_worker_submission_failure_after_handoff_releases_both_reservations(monkeypatch):
    futures = []
    ready, release = asyncio.Event(), asyncio.Event()

    async def pause(*args):
        ready.set()
        await release.wait()

    def submit(*args):
        if len(futures) == 2:
            raise RuntimeError('synthetic')
        future = Future()
        futures.append(future)
        return future

    monkeypatch.setattr(retry, 'ADMISSION_RECHECK_DELAYS', (0,))
    monkeypatch.setattr(
        retry, 'asyncio', SimpleNamespace(sleep=pause, shield=asyncio.shield, wrap_future=asyncio.wrap_future)
    )
    monkeypatch.setattr(retry, 'submit_with_context', submit)
    before = count('skipped', 'submission_error')
    skipped_before = count('skipped', 'slot_limit')
    assert retry.schedule_completed_identity_retries('u', ['a'])
    assert retry.schedule_completed_identity_retries('u', ['b'])
    assert retry.schedule_completed_identity_retries('u', ['c'])
    await ready.wait()
    futures[0].set_result(retry.RetryRound((), 0))
    await settle()
    release.set()
    await settle()
    assert count('skipped', 'submission_error') == before + 1
    assert count('skipped', 'slot_limit') == skipped_before
    assert retry._active == {('u', 'b')} and not retry._waiting
    assert retry._slots.acquire(blocking=False)
    assert not retry._slots.acquire(blocking=False)
    retry._slots.release()
    assert retry._waiting_slots.acquire(blocking=False)
    assert retry._waiting_slots.acquire(blocking=False)
    retry._waiting_slots.release()
    retry._waiting_slots.release()
    await finish(futures)
