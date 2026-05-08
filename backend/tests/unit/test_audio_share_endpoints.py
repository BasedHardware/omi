"""
Structural tests for the async audio-share endpoints (#4586).

Verifies the new POST/GET /v1/sync/audio/{conv}/share endpoints exist with
the right shape: 202 on POST kickoff, idempotent rejoin via the active-job
pointer, default executor for the background worker (avoids the nested-pool
deadlock the v2 sync-local-files comments warn about), and await_upload=True
so the merge completes before the signed URL is generated.
"""

import os
import unittest


class TestAudioShareEndpointStructure(unittest.TestCase):
    @staticmethod
    def _read_sync_source():
        sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(sync_path) as f:
            return f.read()

    @staticmethod
    def _read_storage_source():
        storage_path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'other', 'storage.py')
        with open(storage_path) as f:
            return f.read()

    def test_post_share_endpoint_exists(self):
        source = self._read_sync_source()
        self.assertIn('"/v1/sync/audio/{conversation_id}/share"', source)
        self.assertIn('async def request_audio_share_endpoint', source)

    def test_get_share_status_endpoint_exists(self):
        source = self._read_sync_source()
        self.assertIn('"/v1/sync/audio/{conversation_id}/share/{job_id}"', source)
        self.assertIn('def get_audio_share_status_endpoint', source)

    def test_post_returns_202_with_job_id(self):
        source = self._read_sync_source()
        start = source.index('async def request_audio_share_endpoint')
        nxt = source.find('\n@router.', start + 1)
        body = source[start : nxt if nxt != -1 else len(source)]
        # 202 for the queued case, 200 for the cache-hit shortcut
        self.assertIn('status_code=202', body)
        self.assertIn('status_code=200', body)
        self.assertIn("'job_id'", body)
        self.assertIn("'poll_after_ms'", body)

    def test_post_uses_default_executor(self):
        """Worker must run on the default executor — the worker itself dispatches
        chunk downloads to storage_executor, and nesting both in the same pool
        risks deadlock (same constraint sync_v2 documents)."""
        source = self._read_sync_source()
        start = source.index('async def request_audio_share_endpoint')
        nxt = source.find('\n@router.', start + 1)
        body = source[start : nxt if nxt != -1 else len(source)]
        self.assertIn('run_in_executor(None,', body)
        self.assertIn('_share_audio_background', body)

    def test_post_is_idempotent(self):
        """POST must rejoin an in-flight job via the active-job pointer."""
        source = self._read_sync_source()
        start = source.index('async def request_audio_share_endpoint')
        nxt = source.find('\n@router.', start + 1)
        body = source[start : nxt if nxt != -1 else len(source)]
        self.assertIn('get_active_audio_share_job_id', body)
        self.assertIn('rejoin', body.lower())

    def test_post_fastpath_when_all_cached(self):
        """If every audio file has a valid cached signed URL, POST must short-
        circuit and return signed URLs immediately without creating a job."""
        source = self._read_sync_source()
        start = source.index('async def request_audio_share_endpoint')
        nxt = source.find('\n@router.', start + 1)
        body = source[start : nxt if nxt != -1 else len(source)]
        self.assertIn('all_cached', body)
        self.assertIn('get_merged_audio_signed_url', body)

    def test_get_status_validates_uid_and_conversation(self):
        """The poll endpoint must reject jobs that don't belong to the caller
        or to the conversation in the URL."""
        source = self._read_sync_source()
        start = source.index('def get_audio_share_status_endpoint')
        nxt = source.find('\n@router.', start + 1)
        body = source[start : nxt if nxt != -1 else len(source)]
        self.assertIn('status_code=403', body)
        self.assertIn('status_code=400', body)
        self.assertIn('status_code=404', body)

    def test_background_worker_uses_await_upload(self):
        """The race that broke /urls (#4586) — checking the cache before the
        fire-and-forget upload finishes — is closed by passing await_upload=True."""
        source = self._read_sync_source()
        start = source.index('def _share_audio_background')
        # Scan until next top-level def or @router
        nxt = min(
            (
                pos
                for pos in (
                    source.find('\n@router.', start + 1),
                    source.find('\nasync def ', start + 1),
                    source.find('\ndef ', start + 1),
                )
                if pos != -1
            ),
            default=len(source),
        )
        body = source[start:nxt]
        self.assertIn('await_upload=True', body)
        self.assertIn('mark_audio_share_processing', body)
        self.assertIn('update_audio_file_url', body)

    def test_storage_get_or_create_supports_await_upload(self):
        """storage.get_or_create_merged_audio must accept await_upload and
        call future.result() so the upload completes before returning."""
        source = self._read_storage_source()
        self.assertIn('await_upload: bool = False', source)
        # Inside the function: when await_upload is True, the upload future is
        # waited on. Look for the .result() pattern near a storage_executor.submit.
        start = source.index('def get_or_create_merged_audio')
        nxt = source.find('\ndef ', start + 1)
        body = source[start : nxt if nxt != -1 else len(source)]
        self.assertIn('if await_upload', body)
        self.assertIn('future.result()', body)


if __name__ == '__main__':
    unittest.main()
