"""
Unit tests for the Redis-backed audio_share_jobs module (#4586).

Mirrors the test_sync_v2 isolation pattern: the module is loaded via
importlib.util with database.redis_db stubbed out, so we don't pull a real
Redis client into the test process.
"""

import importlib.util
import json
import os
import sys
import time
import unittest
from unittest.mock import MagicMock


def _load_audio_share_jobs_module():
    """Load database/audio_share_jobs.py with database.redis_db.r faked.

    Mirrors test_sync_v2.TestSyncJobsRedis._load_sync_jobs_module: stub
    `database.redis_db` (and the `database` package itself, since pytest may
    have already imported it for sibling tests) before exec_module.
    """
    fake_r = _FakeRedis()
    saved_modules = {}
    modules_to_stub = {
        'database': MagicMock(),
        'database.redis_db': MagicMock(r=fake_r),
    }
    for mod, mock in modules_to_stub.items():
        saved_modules[mod] = sys.modules.get(mod)
        sys.modules[mod] = mock

    try:
        spec = importlib.util.spec_from_file_location(
            'audio_share_jobs',
            os.path.join(os.path.dirname(__file__), '..', '..', 'database', 'audio_share_jobs.py'),
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module, fake_r
    finally:
        for mod, original in saved_modules.items():
            if original is None:
                sys.modules.pop(mod, None)
            else:
                sys.modules[mod] = original


class _FakeRedis:
    """Minimal Redis stand-in: get/set/delete/expire with TTL bookkeeping."""

    def __init__(self):
        self._store: dict = {}
        self._ttl: dict = {}

    def _gc(self, key):
        ttl = self._ttl.get(key)
        if ttl is not None and time.time() > ttl:
            self._store.pop(key, None)
            self._ttl.pop(key, None)

    def get(self, key):
        self._gc(key)
        return self._store.get(key)

    def set(self, key, value, ex=None):
        if isinstance(value, str):
            value = value.encode('utf-8')
        self._store[key] = value
        if ex is not None:
            self._ttl[key] = time.time() + ex
        return True

    def delete(self, key):
        self._store.pop(key, None)
        self._ttl.pop(key, None)
        return 1

    def expire(self, key, seconds):
        if key in self._store:
            self._ttl[key] = time.time() + seconds
            return 1
        return 0


class TestAudioShareJobsLifecycle(unittest.TestCase):
    def setUp(self):
        self.mod, self.r = _load_audio_share_jobs_module()

    def test_create_persists_job_and_active_pointer(self):
        job = self.mod.create_audio_share_job(
            uid='u1',
            conversation_id='c1',
            audio_files=[{'id': 'a1', 'duration': 10.0}, {'id': 'a2', 'duration': 5.0}],
        )

        self.assertEqual(job['uid'], 'u1')
        self.assertEqual(job['conversation_id'], 'c1')
        self.assertEqual(job['status'], 'queued')
        self.assertEqual(job['progress_pct'], 0.0)
        self.assertEqual(len(job['audio_files']), 2)
        self.assertTrue(all(af['status'] == 'pending' for af in job['audio_files']))

        # Both keys present
        self.assertIsNotNone(self.r.get(f'audio_share_job:{job["job_id"]}'))
        self.assertEqual(self.mod.get_active_job_id('u1', 'c1'), job['job_id'])

    def test_get_returns_none_for_missing(self):
        self.assertIsNone(self.mod.get_audio_share_job('does-not-exist'))

    def test_mark_processing_sets_started_at(self):
        job = self.mod.create_audio_share_job('u1', 'c1', [{'id': 'a1'}])
        before = time.time()
        updated = self.mod.mark_processing(job['job_id'])
        self.assertEqual(updated['status'], 'processing')
        self.assertGreaterEqual(updated['started_at'], before)

    def test_update_audio_file_url_advances_progress(self):
        job = self.mod.create_audio_share_job('u1', 'c1', [{'id': 'a1'}, {'id': 'a2'}, {'id': 'a3'}])
        self.mod.mark_processing(job['job_id'])

        updated = self.mod.update_audio_file_url(job['job_id'], 'a1', 'https://example/a1', 33.3)
        self.assertEqual(updated['progress_pct'], 33.3)
        target = next(af for af in updated['audio_files'] if af['id'] == 'a1')
        self.assertEqual(target['status'], 'cached')
        self.assertEqual(target['signed_url'], 'https://example/a1')

        # Other files untouched
        for other_id in ('a2', 'a3'):
            af = next(af for af in updated['audio_files'] if af['id'] == other_id)
            self.assertEqual(af['status'], 'pending')
            self.assertIsNone(af['signed_url'])

    def test_mark_completed_clears_active_pointer(self):
        job = self.mod.create_audio_share_job('u1', 'c1', [{'id': 'a1'}])
        self.assertIsNotNone(self.mod.get_active_job_id('u1', 'c1'))

        self.mod.mark_completed(job['job_id'])

        # Active pointer is gone; job itself stays around for polling.
        self.assertIsNone(self.mod.get_active_job_id('u1', 'c1'))
        final = self.mod.get_audio_share_job(job['job_id'])
        self.assertEqual(final['status'], 'completed')
        self.assertEqual(final['progress_pct'], 100.0)

    def test_mark_failed_records_error_and_clears_pointer(self):
        job = self.mod.create_audio_share_job('u1', 'c1', [{'id': 'a1'}])
        self.mod.mark_failed(job['job_id'], 'merge blew up')

        self.assertIsNone(self.mod.get_active_job_id('u1', 'c1'))
        final = self.mod.get_audio_share_job(job['job_id'])
        self.assertEqual(final['status'], 'failed')
        self.assertEqual(final['error'], 'merge blew up')

    def test_idempotency_pointer_only_cleared_when_owner(self):
        """The active pointer must only be cleared if it still points at the
        job we're finishing — protects against a new job that started while
        we were finalizing."""
        job_a = self.mod.create_audio_share_job('u1', 'c1', [{'id': 'a1'}])
        # Simulate a second job that took the active slot
        job_b_id = 'job-b'
        self.r.set('audio_share_active:u1:c1', job_b_id, ex=3600)
        # Finishing job_a must NOT clear job_b's pointer
        self.mod.mark_completed(job_a['job_id'])
        self.assertEqual(self.mod.get_active_job_id('u1', 'c1'), job_b_id)

    def test_stale_safety_net_marks_failed(self):
        """A job that hasn't been touched within STALE_THRESHOLD_SECONDS must
        be auto-failed by get(). The threshold is generous (25 min) so genuine
        long merges aren't killed."""
        job = self.mod.create_audio_share_job('u1', 'c1', [{'id': 'a1'}])
        key = f'audio_share_job:{job["job_id"]}'
        stored = json.loads(self.r.get(key))
        stored['updated_at'] = time.time() - self.mod.STALE_THRESHOLD_SECONDS - 60
        self.r.set(key, json.dumps(stored), ex=3600)

        result = self.mod.get_audio_share_job(job['job_id'])
        self.assertEqual(result['status'], 'failed')
        self.assertIn('timed out', result['error'].lower())
        self.assertIsNone(self.mod.get_active_job_id('u1', 'c1'))

    def test_active_pointer_ttl_refreshed_on_progress(self):
        """Updating a non-terminal job must refresh the active-pointer TTL so
        long merges don't lose their idempotency anchor mid-run."""
        job = self.mod.create_audio_share_job('u1', 'c1', [{'id': 'a1'}])
        # Force the active-pointer TTL to nearly expire
        self.r._ttl['audio_share_active:u1:c1'] = time.time() + 1
        self.mod.update_audio_file_url(job['job_id'], 'a1', 'https://example/a1', 50.0)
        self.assertGreater(self.r._ttl['audio_share_active:u1:c1'], time.time() + 100)


if __name__ == '__main__':
    unittest.main()
