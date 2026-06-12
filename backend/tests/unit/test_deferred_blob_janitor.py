"""
Tests for the deferred-deletion janitor (utils/other/deferred_delete.py).

One janitor thread + a due-time heap replace the previous per-file
time.sleep(480) on storage_executor, which parked ~70% of the pool's 128
threads as idle timers (#7531).

Behavioral tests exercise the real DeferredDeleter (the module has no heavy
imports). Structural tests verify the four former sleep-sites now use the
scheduler.
"""

import os
import threading
import time

from utils.other.deferred_delete import DeferredDeleter


def _read_source(rel_path):
    base = os.path.join(os.path.dirname(__file__), '..', '..')
    with open(os.path.join(base, rel_path), encoding='utf-8') as f:
        return f.read()


def _wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class TestDeferredDeleterBehavior:
    def test_deletes_after_delay(self):
        deleted = []
        d = DeferredDeleter(deleted.append)
        d.schedule('a.wav', 0.05)
        assert not deleted, 'must not delete before the delay elapses'
        assert _wait_for(lambda: deleted == ['a.wav'])
        assert d.pending_count() == 0

    def test_out_of_order_schedules_delete_in_due_order(self):
        deleted = []
        lock = threading.Lock()

        def record(path):
            with lock:
                deleted.append(path)

        d = DeferredDeleter(record)
        d.schedule('later.wav', 0.3)
        d.schedule('sooner.wav', 0.05)
        assert _wait_for(lambda: len(deleted) == 2)
        assert deleted == ['sooner.wav', 'later.wav']

    def test_earlier_schedule_interrupts_long_wait(self):
        """A near-term schedule arriving while the janitor waits on a far-future
        item must fire on time, not after the far-future wait."""
        deleted = []
        d = DeferredDeleter(deleted.append)
        d.schedule('far.wav', 30)
        d.schedule('near.wav', 0.05)
        assert _wait_for(lambda: 'near.wav' in deleted)
        assert 'far.wav' not in deleted
        assert d.pending_count() == 1

    def test_failing_delete_does_not_kill_janitor(self):
        deleted = []

        def flaky(path):
            if path == 'boom.wav':
                raise RuntimeError('gcs down')
            deleted.append(path)

        d = DeferredDeleter(flaky)
        d.schedule('boom.wav', 0.02)
        d.schedule('ok.wav', 0.05)
        assert _wait_for(lambda: deleted == ['ok.wav'])

    def test_single_thread_reused_across_schedules(self):
        d = DeferredDeleter(lambda path: None)
        d.schedule('a.wav', 0.01)
        first_thread = d._thread
        assert _wait_for(lambda: d.pending_count() == 0)
        d.schedule('b.wav', 0.01)
        assert d._thread is first_thread
        assert _wait_for(lambda: d.pending_count() == 0)

    def test_many_pending_use_one_thread(self):
        before = threading.active_count()
        d = DeferredDeleter(lambda path: None)
        for i in range(200):
            d.schedule(f'{i}.wav', 60)
        assert d.pending_count() == 200
        assert threading.active_count() <= before + 1, '200 pending deletions must cost exactly one thread'


class TestSleepPatternRemoved:
    def test_no_sleep_480_remains_in_backend(self):
        for rel in ('routers/sync.py', 'utils/chat.py'):
            assert 'time.sleep(480)' not in _read_source(rel), f'{rel} still parks threads as deletion timers'

    def test_sync_uses_scheduler(self):
        assert 'schedule_syncing_temporal_file_deletion(path)' in _read_source('routers/sync.py')

    def test_chat_uses_scheduler_at_all_three_sites(self):
        assert _read_source('utils/chat.py').count('schedule_syncing_temporal_file_deletion(path)') == 3

    def test_storage_defines_scheduler_with_480_default(self):
        src = _read_source('utils/other/storage.py')
        assert 'SYNCING_TEMPORAL_DELETE_DELAY_SECONDS = 480' in src
        assert 'def schedule_syncing_temporal_file_deletion' in src

    def test_precache_sem_restored(self):
        # 4 → 2 was load-shedding while the pool was full of sleepers (#7526)
        assert '_PRECACHE_FILE_SEM = threading.BoundedSemaphore(4)' in _read_source('utils/other/storage.py')
