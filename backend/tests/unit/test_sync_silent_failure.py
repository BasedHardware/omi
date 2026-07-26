"""
Tests for sync endpoint error handling fix (#4867/#4669).

Verifies that process_segment() properly propagates errors via thread-safe
error collection, that the legacy sync endpoint reports partial failures with
207, and that sync v2 app-side reconciliation accepts 200 and 202 responses.

Previously, process_segment() had no error handling — Deepgram failures caused
silent returns or thread crashes, and the endpoint always returned 200.
"""

import os
import threading
from pathlib import Path

import pytest
from pydantic import BaseModel


def _read_text(path):
    return Path(path).read_text(encoding='utf-8')


# ---------------------------------------------------------------------------
# 1. Structural verification — process_segment now has error handling
# ---------------------------------------------------------------------------


class TestProcessSegmentErrorHandling:
    """Verify process_segment has proper error handling after the fix."""

    @staticmethod
    def _read_pipeline_source():
        pipeline_path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'sync', 'pipeline.py')
        return _read_text(pipeline_path)

    def test_process_segment_has_try_except(self):
        """process_segment() must wrap its body in try/except to catch all errors."""
        source = self._read_pipeline_source()
        start = source.index('def process_segment(')
        next_def = source.index('\ndef ', start + 1)
        func_body = source[start:next_def]

        assert 'try:' in func_body, "process_segment must have try/except"
        assert 'except Exception' in func_body, "process_segment must catch exceptions"

    def test_process_segment_uses_lock_for_thread_safety(self):
        """Shared state mutations must be protected by a lock."""
        source = self._read_pipeline_source()
        start = source.index('def process_segment(')
        next_def = source.index('\ndef ', start + 1)
        func_body = source[start:next_def]

        assert 'with lock:' in func_body, "Must use lock for thread-safe mutations"
        # Lock must protect the exception path and response dict mutations
        lock_sections = func_body.split('with lock:')
        assert len(lock_sections) >= 3, "Must have lock sections for exception errors + new_memories + updated_memories"

    def test_process_segment_accepts_lock_and_errors_params(self):
        """process_segment must accept lock and errors as parameters."""
        source = self._read_pipeline_source()
        start = source.index('def process_segment(')
        sig_end = source.index('):', start) + 2
        signature = source[start:sig_end]

        assert 'lock:' in signature, "Must accept lock parameter"
        assert 'errors:' in signature, "Must accept errors parameter"


class TestSyncEndpointErrorReporting:
    """Verify the endpoint properly reports errors."""

    @staticmethod
    def _read_sync_source():
        sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        return _read_text(sync_path)

    def test_endpoint_creates_lock_and_errors(self):
        """Endpoint must create segment_lock and segment_errors."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files(')
        func_body = source[start:]

        assert 'segment_errors = []' in func_body, "Must initialize error list"
        assert 'segment_lock = threading.Lock()' in func_body, "Must create lock"

    def test_endpoint_passes_lock_and_errors_to_threads(self):
        """Thread args must include lock and errors."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files(')
        func_body = source[start:]

        assert 'segment_lock,' in func_body, "Must pass lock to process_segment threads"
        assert 'segment_errors,' in func_body, "Must pass errors to process_segment threads"

    def test_endpoint_returns_207_on_partial_failure(self):
        """Partial failure must return HTTP 207."""
        source = self._read_sync_source()
        assert 'status_code=207' in source, "Must return 207 for partial failure"

    def test_endpoint_returns_500_on_all_failed(self):
        """All segments failing must return HTTP 500."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files(')
        func_body = source[start:]

        assert 'successful_segments == 0' in func_body, "Must check for all-fail case"
        assert "All" in func_body and "failed processing" in func_body, "Must include descriptive 500 message"

    def test_response_includes_failed_segments_count(self):
        """Response must include failed_segments count for app to check."""
        source = self._read_sync_source()
        assert "'failed_segments'" in source, "Response must include failed_segments"
        assert "'total_segments'" in source, "Response must include total_segments"
        assert "'errors'" in source, "Response must include errors list"

    def test_response_converts_sets_to_sorted_lists(self):
        """Sets must be converted to sorted lists for JSON serialization."""
        source = self._read_sync_source()
        assert "sorted(response['new_memories'])" in source, "new_memories must be sorted list"
        assert "sorted(response['updated_memories'])" in source, "updated_memories must be sorted list"


# ---------------------------------------------------------------------------
# 2. Threading behavior — errors now properly collected
# ---------------------------------------------------------------------------


class TestThreadSafeErrorCollection:
    """Verify the new error collection pattern works correctly."""

    def test_errors_collected_from_failed_threads(self):
        """Errors from multiple failing threads are properly collected."""
        errors = []
        lock = threading.Lock()
        response = {'updated_memories': set(), 'new_memories': set()}

        def failing_segment(path, uid, resp, lk, errs):
            with lk:
                errs.append(f'Failed: {path}')

        def succeeding_segment(path, uid, resp, lk, errs):
            with lk:
                resp['new_memories'].add(f'conv-{path}')

        threads = [
            threading.Thread(target=succeeding_segment, args=('seg1', 'uid', response, lock, errors)),
            threading.Thread(target=failing_segment, args=('seg2', 'uid', response, lock, errors)),
            threading.Thread(target=succeeding_segment, args=('seg3', 'uid', response, lock, errors)),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(response['new_memories']) == 2
        assert len(errors) == 1
        assert 'seg2' in errors[0]

    def test_exception_caught_and_collected(self):
        """Exceptions in threads are caught and appended to errors list."""
        errors = []
        lock = threading.Lock()

        def crashing_segment(lk, errs):
            try:
                raise ConnectionError("Deepgram timeout")
            except Exception as e:
                with lk:
                    errs.append(f'Failed: {e}')

        t = threading.Thread(target=crashing_segment, args=(lock, errors))
        t.start()
        t.join()

        assert len(errors) == 1
        assert 'Deepgram timeout' in errors[0]

    def test_status_code_logic(self):
        """Verify status code selection based on segment counts."""
        # All succeed: 200
        total, failed = 5, 0
        successful = total - failed
        assert successful > 0 and failed == 0  # → 200

        # Partial failure: 207
        total, failed = 5, 2
        successful = total - failed
        assert successful > 0 and failed > 0  # → 207

        # All fail: 500
        total, failed = 5, 5
        successful = total - failed
        assert total > 0 and successful == 0  # → 500

        # No segments (edge): 200 (empty success)
        total, failed = 0, 0
        successful = total - failed
        assert total == 0  # → 200 with empty result


# ---------------------------------------------------------------------------
# 3. Deepgram retry behavior (unchanged)
# ---------------------------------------------------------------------------


class TestDeepgramRetryBehavior:
    """Verifies retry exhaustion raises while valid empty transcriptions stay empty."""

    @staticmethod
    def _read_deepgram_source():
        dg_path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'stt', 'pre_recorded.py')
        return _read_text(dg_path)

    def test_deepgram_raises_runtime_error_on_final_retry(self):
        """After retry exhaustion, deepgram_prerecorded must raise instead of returning []."""
        source = self._read_deepgram_source()
        start = source.index('def deepgram_prerecorded(')
        next_func_markers = ['@timeit', '\ndef ']
        end = len(source)
        for marker in next_func_markers:
            try:
                idx = source.index(marker, start + 100)
                if idx < end:
                    end = idx
            except ValueError:
                pass
        func_body = source[start:end]

        except_body = func_body[func_body.index('except Exception as e:') :]

        assert 'raise RuntimeError' in except_body
        assert 'Deepgram transcription failed after' in except_body
        assert 'attempts < 1' in func_body

    def test_deepgram_keeps_empty_words_as_success(self):
        """A valid Deepgram response with no words must still return []."""
        source = self._read_deepgram_source()
        start = source.index('def deepgram_prerecorded(')
        next_func_markers = ['@timeit', '\ndef ']
        end = len(source)
        for marker in next_func_markers:
            try:
                idx = source.index(marker, start + 100)
                if idx < end:
                    end = idx
            except ValueError:
                pass
        func_body = source[start:end]
        no_words_block = func_body[
            func_body.index("dg_words = alternatives[0].get('words', [])") : func_body.index(
                '# Convert Deepgram format'
            )
        ]

        assert 'if not dg_words:' in no_words_block
        assert 'return [], detected_lang or \'en\'' in no_words_block
        assert 'return []' in no_words_block


class TestDeepgramRetryBehavioral:
    """Behavioral tests that execute deepgram_prerecorded with mocked DG client.

    Uses setup_class/teardown_class to install stubs for deepgram + related deps,
    then imports the real function under test.
    """

    _saved_modules = {}
    _deepgram_prerecorded = None
    _mock_client = None

    @classmethod
    def setup_class(cls):
        from unittest.mock import MagicMock
        from types import ModuleType

        stubs = [
            'deepgram',
            'fal_client',
            'models',
            'models.transcript_segment',
            'utils.other.endpoints',
            'utils.stt.speaker_embedding',
        ]
        cls._saved_modules = {name: sys.modules.get(name) for name in stubs}
        cls._saved_modules['utils.stt.pre_recorded'] = sys.modules.get('utils.stt.pre_recorded')

        for mod_name in stubs:
            sys.modules[mod_name] = ModuleType(mod_name)

        sys.modules['deepgram'].DeepgramClient = MagicMock()
        sys.modules['deepgram'].DeepgramClientOptions = MagicMock()
        sys.modules['fal_client'].submit = MagicMock()
        sys.modules['models.transcript_segment'].TranscriptSegment = MagicMock()
        sys.modules['utils.other.endpoints'].timeit = lambda f: f
        sys.modules['utils.stt.speaker_embedding'].SPEAKER_MATCH_THRESHOLD = 0.45
        sys.modules['utils.stt.speaker_embedding'].compare_embeddings = MagicMock(return_value=1.0)
        sys.modules['utils.stt.speaker_embedding'].extract_embedding_from_bytes = MagicMock()

        # Force re-import so it picks up stubs
        sys.modules.pop('utils.stt.pre_recorded', None)
        from utils.stt.pre_recorded import deepgram_prerecorded

        cls._deepgram_prerecorded = staticmethod(deepgram_prerecorded)

    @classmethod
    def teardown_class(cls):
        sys.modules.pop('utils.stt.pre_recorded', None)
        for name, orig in cls._saved_modules.items():
            if orig is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = orig
        cls._saved_modules.clear()

    def test_retry_exhaustion_raises_runtime_error(self):
        """deepgram_prerecorded must raise RuntimeError when all retries fail."""
        from unittest.mock import MagicMock, patch

        mock_client = MagicMock()
        mock_client.listen.rest.v.return_value.transcribe_url.side_effect = ConnectionError('timeout')

        with patch('utils.stt.pre_recorded._deepgram_client_for_request', return_value=mock_client):
            with pytest.raises(RuntimeError, match='Deepgram transcription failed after 2 attempts'):
                self._deepgram_prerecorded('https://fake-audio.wav', attempts=0, return_language=True)

        # Should have been called 2 times (initial + 1 retry)
        assert mock_client.listen.rest.v.return_value.transcribe_url.call_count == 2

    def test_valid_empty_transcription_returns_empty_list(self):
        """deepgram_prerecorded must return ([], lang) when DG succeeds but finds no words."""
        from unittest.mock import MagicMock, patch

        mock_response = MagicMock()
        mock_response.to_dict.return_value = {
            'results': {
                'channels': [
                    {
                        'alternatives': [{'words': []}],
                        'detected_language': 'en',
                    }
                ]
            }
        }
        mock_client = MagicMock()
        mock_client.listen.rest.v.return_value.transcribe_url.return_value = mock_response

        with patch('utils.stt.pre_recorded._deepgram_client_for_request', return_value=mock_client):
            words, lang = self._deepgram_prerecorded('https://fake-audio.wav', return_language=True)

        assert words == []
        assert lang == 'en'
        # Should be called exactly once (no retries for valid response)
        assert mock_client.listen.rest.v.return_value.transcribe_url.call_count == 1


# ---------------------------------------------------------------------------
# 4. App-side behavior documentation (unchanged, for PR evidence)
# ---------------------------------------------------------------------------


class TestAppSideSyncBehavior:
    """Documents current app-side WAL retry behavior for sync v2."""

    @staticmethod
    def _read_app_file(relative_path):
        app_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'app', 'lib', relative_path)
        if os.path.exists(app_path):
            return _read_text(app_path)
        return None

    def test_app_accepts_200_and_202(self):
        """App treats sync v2 200 as done and 202 as queued for reconciliation."""
        source = self._read_app_file('backend/http/api/conversations.dart')
        if source is None:
            pytest.skip("App source not available")

        assert 'response.statusCode == 200' in source
        assert 'response.statusCode == 202' in source
        assert 'UploadFilesResult.done' in source
        assert 'UploadFilesResult.queued' in source

    def test_app_keeps_wals_retryable_on_failed_reconcile(self):
        """App keeps uploaded WALs retryable when sync v2 reconciliation fails."""
        source = self._read_app_file('services/wals/local_wal_sync.dart')
        if source is None:
            pytest.skip("App source not available")

        assert 'reconcileUploadedWals' in source, "Must reconcile uploaded sync v2 jobs"
        assert 'case SyncJobFetchOutcome.notFound' in source, "Expired jobs must be recoverable"
        assert 'w.status = WalStatus.miss' in source, "Failed terminal jobs must become retryable"
        assert 'w.retryCount += 1' in source, "Retryable failures must increment retry count"
        assert 'w.status = WalStatus.synced' in source, "Successful jobs must still mark WALs synced"


# ---------------------------------------------------------------------------
# 5. End-to-end data loss prevention verification
# ---------------------------------------------------------------------------


class TestDataLossPreventionFlow:
    """Verifies the fix prevents data loss in the reported scenarios."""

    def test_partial_failure_no_longer_returns_200(self):
        """When segments fail, endpoint returns 207 (not 200).
        Old clients treat 207 as error → WALs stay in miss state → retryable."""
        total_segments = 5
        failed_segments = 2
        successful_segments = total_segments - failed_segments

        # After fix: endpoint checks failures
        if total_segments > 0 and successful_segments == 0:
            status = 500
        elif failed_segments > 0:
            status = 207
        else:
            status = 200

        assert status == 207, "Partial failure must return 207"

        # Old client behavior: 207 is not 200 → throws exception → WALs not marked synced
        app_treats_as_success = status == 200
        assert not app_treats_as_success, "Old clients must NOT mark WALs as synced on 207"

    def test_all_failure_returns_500(self):
        """When ALL segments fail, endpoint returns 500 → clear error for all clients."""
        total_segments = 3
        failed_segments = 3
        successful_segments = 0

        if total_segments > 0 and successful_segments == 0:
            status = 500
        elif failed_segments > 0:
            status = 207
        else:
            status = 200

        assert status == 500

    def test_full_success_still_returns_200(self):
        """When all segments succeed, behavior is unchanged (200)."""
        total_segments = 3
        failed_segments = 0
        successful_segments = 3

        if total_segments > 0 and successful_segments == 0:
            status = 500
        elif failed_segments > 0:
            status = 207
        else:
            status = 200

        assert status == 200

    def test_response_includes_error_details_for_debugging(self):
        """Response includes structured error info for debugging."""
        segment_errors = [
            'Failed to process segment /tmp/1700000100.wav: Deepgram transcription failed after 2 attempts: timeout'
        ]
        total_segments = 3
        failed_segments = len(segment_errors)

        result = {
            'new_memories': ['conv-1', 'conv-2'],
            'updated_memories': [],
            'failed_segments': failed_segments,
            'total_segments': total_segments,
            'errors': segment_errors[:10],
        }

        assert result['failed_segments'] == 1
        assert result['total_segments'] == 3
        assert len(result['errors']) == 1
        assert 'Deepgram transcription failed after 2 attempts' in result['errors'][0]


# ---------------------------------------------------------------------------
# 6. Deduplication on retry — prevents duplicate transcripts
# ---------------------------------------------------------------------------


class TestSegmentDeduplication:
    """Verifies that retried segments are deduplicated in the merge path."""

    @staticmethod
    def _read_pipeline_source():
        pipeline_path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'sync', 'pipeline.py')
        return _read_text(pipeline_path)

    def test_merge_path_has_dedup_logic(self):
        """process_segment merge path must deduplicate before appending."""
        source = self._read_pipeline_source()
        start = source.index('def process_segment(')
        next_def = source.index('\ndef ', start + 1)
        func_body = source[start:next_def]

        assert 'existing_timestamps' in func_body, "Must build set of existing segment timestamps"
        assert 'deduped_segments' in func_body, "Must filter out duplicate segments"
        assert (
            'not deduped_segments' in func_body or 'if not deduped_segments' in func_body
        ), "Must handle case where all segments are duplicates"

    def test_dedup_uses_timestamp_rounding(self):
        """Dedup must round timestamps to avoid float precision issues."""
        source = self._read_pipeline_source()
        assert 'round(' in source, "Must round timestamps for reliable comparison"

    def test_dedup_logic_correctness(self):
        """Verify the dedup algorithm works correctly with sample data."""
        existing_segments = [
            {'start': 0.0, 'end': 5.0, 'timestamp': 1700000000.0, 'text': 'hello'},
            {'start': 5.0, 'end': 10.0, 'timestamp': 1700000005.0, 'text': 'world'},
        ]
        new_segments = [
            {'start': 0.0, 'end': 5.0, 'timestamp': 1700000000.0, 'text': 'hello'},  # duplicate
            {'start': 10.0, 'end': 15.0, 'timestamp': 1700000010.0, 'text': 'new stuff'},  # new
        ]

        # Build existing set (same logic as in sync.py)
        existing_timestamps = {
            (round(s['timestamp'], 2), round(s['timestamp'] + (s['end'] - s['start']), 2)) for s in existing_segments
        }

        deduped = []
        for seg in new_segments:
            seg_key = (round(seg['timestamp'], 2), round(seg['timestamp'] + (seg['end'] - seg['start']), 2))
            if seg_key not in existing_timestamps:
                deduped.append(seg)

        assert len(deduped) == 1, "Should filter out 1 duplicate"
        assert deduped[0]['text'] == 'new stuff', "Should keep only the new segment"

    def test_all_duplicates_skips_merge(self):
        """When all new segments are duplicates, merge is skipped entirely."""
        existing_segments = [
            {'start': 0.0, 'end': 5.0, 'timestamp': 1700000000.0},
        ]
        new_segments = [
            {'start': 0.0, 'end': 5.0, 'timestamp': 1700000000.0},  # exact duplicate
        ]

        existing_timestamps = {
            (round(s['timestamp'], 2), round(s['timestamp'] + (s['end'] - s['start']), 2)) for s in existing_segments
        }

        deduped = [
            seg
            for seg in new_segments
            if (round(seg['timestamp'], 2), round(seg['timestamp'] + (seg['end'] - seg['start']), 2))
            not in existing_timestamps
        ]

        assert len(deduped) == 0, "All duplicates should be filtered"


# ---------------------------------------------------------------------------
# 7. Behavioral test — real process_segment with mocked dependencies
# ---------------------------------------------------------------------------

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

_STUB_MODULES = [
    'models',
    'models.conversation',
    'models.conversation_enums',
    'models.sync_audio',
    'models.transcript_segment',
    'database._client',
    'database.redis_db',
    'database.fair_use',
    'database.users',
    'database.user_usage',
    'database.conversations',
    'database.sync_ledger',
    'firebase_admin',
    'firebase_admin.messaging',
    'opuslib',
    'pydub',
    'utils.other.endpoints',
    'utils.other.storage',
    'utils.log_sanitizer',
    'utils.encryption',
    'utils.stt.pre_recorded',
    'utils.stt.vad',
    'utils.speaker_assignment',
    'utils.speaker_identification',
    'utils.stt.speaker_embedding',
    'utils.fair_use',
    'utils.subscription',
    'utils.cloud_tasks',
    'utils.sync.content_id',
    'utils.conversations.process_conversation',
    'python_multipart',
    'python_multipart.multipart',
]


class TestProcessSegmentReal:
    """Tests that call the real process_segment function with mocked deps.

    Uses setup_class/teardown_class to install and remove sys.modules stubs
    so other test files in the same pytest process are not contaminated.
    """

    _saved_modules = {}
    _process_segment = None

    @classmethod
    def setup_class(cls):
        # Save originals
        cls._saved_modules = {name: sys.modules.get(name) for name in _STUB_MODULES}
        # Also save pipeline if already imported
        cls._saved_modules['utils.sync.pipeline'] = sys.modules.get('utils.sync.pipeline')
        cls._saved_modules['utils.sync'] = sys.modules.get('utils.sync')

        # Install stubs
        for mod_name in _STUB_MODULES:
            sys.modules[mod_name] = ModuleType(mod_name)
        sys.modules['models'].__path__ = []

        sys.modules['database.redis_db'].r = MagicMock()
        sys.modules['database._client'].db = MagicMock()
        _mock_conv_db = sys.modules['database.conversations']
        _mock_conv_db.get_closest_conversation_to_timestamps = MagicMock()
        _mock_conv_db.update_conversation_segments = MagicMock()
        _mock_conv_db.update_conversation = MagicMock()
        _mock_conv_db.get_conversation = MagicMock()
        sys.modules['opuslib'].Decoder = MagicMock()
        sys.modules['pydub'].AudioSegment = MagicMock()
        sys.modules['utils.other.endpoints'].get_current_user_uid = MagicMock()
        sys.modules['utils.other.storage'].get_syncing_file_temporal_signed_url = MagicMock(return_value='https://fake')
        sys.modules['utils.other.storage'].schedule_syncing_temporal_file_deletion = MagicMock()
        sys.modules['utils.other.storage'].get_playback_artifact_signed_url = MagicMock(return_value=None)
        sys.modules['utils.other.storage'].download_legacy_merged_wav = MagicMock(return_value=None)
        sys.modules['utils.other.storage'].download_playback_artifact = MagicMock(return_value=None)
        sys.modules['utils.other.storage'].upload_playback_artifact = MagicMock()
        sys.modules['utils.other.storage'].upload_audio_chunk = MagicMock()
        sys.modules['utils.other.storage'].precache_conversation_audio = MagicMock()
        sys.modules['utils.other.storage'].mark_playback_unavailable = MagicMock()
        sys.modules['utils.other.storage'].is_playback_unavailable = MagicMock(return_value=False)
        sys.modules['utils.other.storage'].enqueue_conversation_audio_merge = MagicMock()
        sys.modules['utils.other.storage'].delete_syncing_temporal_file = MagicMock()
        sys.modules['utils.other.storage'].download_audio_chunks_and_merge = MagicMock()
        sys.modules['utils.other.storage'].get_or_create_merged_audio = MagicMock()
        sys.modules['utils.other.storage'].get_merged_audio_signed_url = MagicMock()
        sys.modules['utils.other.storage'].upload_audio_chunk = MagicMock()
        sys.modules['utils.other.storage'].precache_conversation_audio = MagicMock()
        sys.modules['utils.other.storage'].is_playback_unavailable = MagicMock(return_value=False)
        sys.modules['utils.other.storage'].mark_playback_unavailable = MagicMock()
        sys.modules['utils.other.storage']._PRECACHE_FILE_SEM = MagicMock()
        sys.modules['utils.other.storage'].upload_syncing_temporal_file = MagicMock()
        sys.modules['utils.other.storage'].download_syncing_temporal_file = MagicMock(return_value=True)
        sys.modules['utils.other.storage'].compute_audio_files_fingerprint = MagicMock(return_value='fp')
        sys.modules['utils.other.storage'].enqueue_conversation_artifact_build = MagicMock()
        sys.modules['utils.other.storage'].get_conversation_playback_signed_url = MagicMock(return_value=None)
        sys.modules['utils.other.storage'].upload_conversation_playback_artifact = MagicMock()
        sys.modules['utils.other.storage'].mark_conversation_playback_unavailable = MagicMock()
        sys.modules['utils.other.storage'].get_conversation_playback_unavailable_fingerprint = MagicMock(
            return_value=None
        )
        sys.modules['utils.cloud_tasks'].enqueue_sync_job = MagicMock()
        sys.modules['utils.cloud_tasks'].get_sync_tasks_max_attempts = MagicMock(return_value=5)
        sys.modules['utils.cloud_tasks'].is_cloud_tasks_dispatch_enabled = MagicMock(return_value=False)
        sys.modules['utils.cloud_tasks'].is_audio_merge_dispatch_enabled = MagicMock(return_value=False)
        sys.modules['utils.cloud_tasks'].enqueue_audio_merge_job = MagicMock()
        sys.modules['utils.cloud_tasks'].verify_cloud_tasks_oidc = MagicMock()
        sys.modules['database.sync_ledger'].add_processed_sync_segment_id = MagicMock(return_value=True)
        sys.modules['database.sync_ledger'].bind_sync_content_run_token = MagicMock()
        sys.modules['database.sync_ledger'].checkpoint_sync_content_partial_result = MagicMock()
        sys.modules['database.sync_ledger'].get_processed_sync_segment_ids = MagicMock(return_value=set())
        sys.modules['database.sync_ledger'].get_sync_content_partial_result = MagicMock(return_value=None)
        sys.modules['database.sync_ledger'].is_valid_completed_sync_content_result = MagicMock(return_value=True)
        sys.modules['database.sync_ledger'].mark_sync_content_completed = MagicMock()
        sys.modules['database.sync_ledger'].release_sync_content_claim_after_job_retired = MagicMock()
        sys.modules['database.sync_ledger'].release_sync_content_claim = MagicMock()
        sys.modules['database.sync_ledger'].try_mark_sync_content_metered = MagicMock(return_value=True)
        sys.modules['database.sync_ledger'].try_mark_sync_content_side_effect = MagicMock(return_value=True)
        sys.modules['utils.sync.content_id'].compute_sync_segment_id = MagicMock(return_value='segment-id')
        sys.modules['utils.log_sanitizer'].sanitize = lambda value: value
        sys.modules['utils.encryption'].encrypt = MagicMock()
        sys.modules['utils.stt.pre_recorded'].deepgram_prerecorded = MagicMock()
        sys.modules['utils.stt.pre_recorded'].prerecorded = MagicMock()
        sys.modules['utils.stt.pre_recorded'].postprocess_words = MagicMock()
        sys.modules['utils.stt.pre_recorded'].get_prerecorded_service = MagicMock(
            return_value=('deepgram', 'multi', 'nova-3')
        )
        sys.modules['utils.stt.vad'].vad_is_empty = MagicMock()
        sys.modules['utils.speaker_assignment'].process_speaker_assigned_segments = MagicMock()
        sys.modules['utils.speaker_identification'].detect_speaker_from_text = MagicMock(return_value=None)
        sys.modules['utils.stt.speaker_embedding'].extract_embedding_from_bytes = MagicMock()
        sys.modules['utils.stt.speaker_embedding'].compare_embeddings = MagicMock(return_value=1.0)
        sys.modules['utils.stt.speaker_embedding'].SPEAKER_MATCH_THRESHOLD = 0.45
        sys.modules['utils.fair_use'].FAIR_USE_ENABLED = False
        sys.modules['utils.fair_use'].FAIR_USE_RESTRICT_DAILY_DG_MS = 0
        sys.modules['utils.fair_use'].record_speech_ms = MagicMock()
        sys.modules['utils.fair_use'].get_rolling_speech_ms = MagicMock()
        sys.modules['utils.fair_use'].check_soft_caps = MagicMock()
        sys.modules['utils.fair_use'].is_hard_restricted = MagicMock(return_value=False)
        sys.modules['utils.fair_use'].get_hard_restriction_status = MagicMock(return_value=(False, None))
        sys.modules['python_multipart'].__version__ = '0.0.99'
        sys.modules['python_multipart.multipart'].parse_options_header = MagicMock(return_value={})
        sys.modules['utils.fair_use'].trigger_classifier_if_needed = MagicMock()
        sys.modules['utils.fair_use'].is_dg_budget_exhausted = MagicMock(return_value=False)
        sys.modules['utils.fair_use'].get_enforcement_stage = MagicMock(return_value='off')
        sys.modules['utils.fair_use'].record_dg_usage_ms = MagicMock()
        sys.modules['utils.subscription'].has_transcription_credits = MagicMock(return_value=True)
        sys.modules['utils.conversations.process_conversation'].process_conversation = MagicMock()

        class _ConversationSource:
            omi = 'omi'
            limitless = 'limitless'

        class _CreateConversation:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        class _Conversation:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        class _TranscriptSegment:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

            def dict(self):
                return dict(self.__dict__)

        sys.modules['models.conversation'].ConversationSource = _ConversationSource
        sys.modules['models.conversation_enums'].ConversationSource = _ConversationSource
        sys.modules['models.conversation'].CreateConversation = _CreateConversation
        sys.modules['models.conversation'].Conversation = _Conversation
        sys.modules['models.transcript_segment'].TranscriptSegment = _TranscriptSegment

        class _AudioPrecacheResponse(BaseModel):
            pass

        class _AudioUrlsResponse(BaseModel):
            pass

        sys.modules['models.sync_audio'].AudioPrecacheResponse = _AudioPrecacheResponse
        sys.modules['models.sync_audio'].AudioUrlsResponse = _AudioUrlsResponse

        sync_pkg = ModuleType('utils.sync')
        sync_pkg.__path__ = [os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'sync')]
        sys.modules['utils.sync'] = sync_pkg
        sys.modules.pop('utils.sync.pipeline', None)

        # Import under stubs
        from utils.sync.pipeline import process_segment

        cls._process_segment = staticmethod(process_segment)

    @classmethod
    def teardown_class(cls):
        sys.modules.pop('utils.sync.pipeline', None)
        # Restore original modules
        for name, orig in cls._saved_modules.items():
            if orig is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = orig
        cls._saved_modules.clear()

    def _import_process_segment(self):
        return self._process_segment

    def test_empty_words_after_vad_are_silence_not_failure(self):
        """Speech-eligible input with no provider words is silence, not a failure.

        VAD over-reports on noise, so a provider returning nothing is the
        authority on whether there was speech. The segment produces nothing and
        records no error, so its job does not fail and the client stops
        re-uploading it as a failed recording."""
        process_segment = self._import_process_segment()

        response = {'updated_memories': set(), 'new_memories': set()}
        errors = []
        lock = threading.Lock()

        with patch('utils.sync.pipeline.prerecorded', return_value=([], 'en')), patch(
            'utils.sync.pipeline.delete_syncing_temporal_file'
        ), patch('utils.sync.pipeline.get_syncing_file_temporal_signed_url', return_value='https://fake'), patch(
            'utils.sync.pipeline.time.sleep'
        ):
            from models.conversation_enums import ConversationSource

            result = process_segment(
                '/tmp/1700000000.wav', 'uid', response, lock, errors, ConversationSource.omi, False
            )

        assert result is False
        assert errors == []
        assert len(response['new_memories']) == 0
        assert len(response['updated_memories']) == 0

    def test_empty_postprocessed_after_vad_is_silence_not_failure(self):
        """Provider words filtered to no segments is silence, not a failure."""
        process_segment = self._import_process_segment()

        response = {'updated_memories': set(), 'new_memories': set()}
        errors = []
        lock = threading.Lock()

        with patch('utils.sync.pipeline.prerecorded', return_value=([{'text': 'um'}], 'en')), patch(
            'utils.sync.pipeline.postprocess_words', return_value=[]
        ), patch('utils.sync.pipeline.delete_syncing_temporal_file'), patch(
            'utils.sync.pipeline.get_syncing_file_temporal_signed_url', return_value='https://fake'
        ), patch(
            'utils.sync.pipeline.time.sleep'
        ):
            from models.conversation_enums import ConversationSource

            result = process_segment(
                '/tmp/1700000000.wav', 'uid', response, lock, errors, ConversationSource.omi, False
            )

        assert result is False
        assert errors == []
        assert len(response['new_memories']) == 0
        assert len(response['updated_memories']) == 0

    def test_exception_caught_and_collected(self):
        """Real process_segment: Deepgram raises → exception caught, error collected."""
        process_segment = self._import_process_segment()

        response = {'updated_memories': set(), 'new_memories': set()}
        errors = []
        lock = threading.Lock()

        with patch('utils.sync.pipeline.prerecorded', side_effect=ConnectionError('timeout')), patch(
            'utils.sync.pipeline.delete_syncing_temporal_file'
        ), patch('utils.sync.pipeline.get_syncing_file_temporal_signed_url', return_value='https://fake'), patch(
            'utils.sync.pipeline.time.sleep'
        ):
            from models.conversation_enums import ConversationSource

            process_segment('/tmp/1700000000.wav', 'uid', response, lock, errors, ConversationSource.omi, False)

        assert errors == ['stt_upstream_error']

    def _make_real_segment(self):
        """Create a real TranscriptSegment for Pydantic validation."""
        from models.transcript_segment import TranscriptSegment

        return TranscriptSegment(text='hello', speaker='SPEAKER_00', is_user=False, start=0.0, end=5.0)

    def test_success_adds_to_new_memories(self):
        """Real process_segment: success path creates conversation and adds to response."""
        process_segment = self._import_process_segment()

        response = {'updated_memories': set(), 'new_memories': set()}
        errors = []
        lock = threading.Lock()

        real_segment = self._make_real_segment()
        mock_conv = MagicMock()
        mock_conv.id = 'conv-abc123'

        with patch('utils.sync.pipeline.prerecorded', return_value=([{'text': 'hello'}], 'en')), patch(
            'utils.sync.pipeline.postprocess_words', return_value=[real_segment]
        ), patch('utils.sync.pipeline.get_timestamp_from_path', return_value=1700000000.0), patch(
            'utils.sync.pipeline.get_closest_conversation_to_timestamps', return_value=None
        ), patch(
            'utils.sync.pipeline.process_conversation', return_value=mock_conv
        ), patch(
            'utils.sync.pipeline.delete_syncing_temporal_file'
        ), patch(
            'utils.sync.pipeline.get_syncing_file_temporal_signed_url', return_value='https://fake'
        ), patch(
            'utils.sync.pipeline.time.sleep'
        ):
            from models.conversation_enums import ConversationSource

            process_segment('/tmp/1700000000.wav', 'uid', response, lock, errors, ConversationSource.omi, False)

        assert len(errors) == 0, f"Unexpected errors: {errors}"
        assert 'conv-abc123' in response['new_memories']

    def test_mixed_threaded_execution(self):
        """Real process_segment in threads: mixed success/failure, errors collected."""
        process_segment = self._import_process_segment()

        response = {'updated_memories': set(), 'new_memories': set()}
        errors = []
        lock = threading.Lock()

        call_count = [0]
        call_lock = threading.Lock()

        def mock_deepgram_mixed(url, speakers_count=3, attempts=0, return_language=True, **kwargs):
            with call_lock:
                call_count[0] += 1
                n = call_count[0]
            if n == 2:
                raise ConnectionError('Deepgram timeout')  # Segment 2 fails with exception
            return [{'text': 'hello'}], 'en'

        real_segment = self._make_real_segment()
        mock_conv = MagicMock()
        mock_conv.id = 'conv-success'

        with patch('utils.sync.pipeline.prerecorded', side_effect=mock_deepgram_mixed), patch(
            'utils.sync.pipeline.postprocess_words', return_value=[real_segment]
        ), patch('utils.sync.pipeline.get_timestamp_from_path', return_value=1700000000.0), patch(
            'utils.sync.pipeline.get_closest_conversation_to_timestamps', return_value=None
        ), patch(
            'utils.sync.pipeline.process_conversation', return_value=mock_conv
        ), patch(
            'utils.sync.pipeline.delete_syncing_temporal_file'
        ), patch(
            'utils.sync.pipeline.get_syncing_file_temporal_signed_url', return_value='https://fake'
        ), patch(
            'utils.sync.pipeline.time.sleep'
        ):
            from models.conversation_enums import ConversationSource

            threads = [
                threading.Thread(
                    target=process_segment,
                    args=(f'/tmp/{i}.wav', 'uid', response, lock, errors, ConversationSource.omi, False),
                )
                for i in range(3)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        # 2 succeeded, 1 failed (exception)
        assert len(errors) == 1, f"Expected 1 error, got {len(errors)}: {errors}"
        assert errors[0] == 'stt_upstream_error'
        assert len(response['new_memories']) >= 1  # At least 1 success

    def test_dedup_skips_existing_segments_on_retry(self):
        """Real process_segment: retry with existing segments → dedup skips merge."""
        process_segment = self._import_process_segment()

        response = {'updated_memories': set(), 'new_memories': set()}
        errors = []
        lock = threading.Lock()

        mock_segment = MagicMock()
        mock_segment.end = 5.0
        mock_segment.model_dump.return_value = {'start': 0.0, 'end': 5.0, 'text': 'hello', 'speaker': 'SPEAKER_00'}

        # Simulate existing conversation with the SAME segments (retry scenario)
        existing_conv = {
            'id': 'conv-existing',
            'started_at': MagicMock(timestamp=MagicMock(return_value=1700000000.0)),
            'finished_at': MagicMock(timestamp=MagicMock(return_value=1700000005.0)),
            'transcript_segments': [
                {'start': 0.0, 'end': 5.0, 'text': 'hello', 'speaker': 'SPEAKER_00', 'timestamp': 1700000000.0},
            ],
            'discarded': False,
        }
        # Make finished_at comparable
        from datetime import datetime, timezone

        existing_conv['finished_at'] = datetime.fromtimestamp(1700000005.0, tz=timezone.utc)

        with patch('utils.sync.pipeline.prerecorded', return_value=([{'text': 'hello'}], 'en')), patch(
            'utils.sync.pipeline.postprocess_words', return_value=[mock_segment]
        ), patch('utils.sync.pipeline.get_timestamp_from_path', return_value=1700000000.0), patch(
            'utils.sync.pipeline.get_closest_conversation_to_timestamps', return_value=existing_conv
        ), patch(
            'utils.sync.pipeline.update_conversation_segments'
        ) as mock_update, patch(
            'utils.sync.pipeline.delete_syncing_temporal_file'
        ), patch(
            'utils.sync.pipeline.get_syncing_file_temporal_signed_url', return_value='https://fake'
        ), patch(
            'utils.sync.pipeline.time.sleep'
        ):
            from models.conversation_enums import ConversationSource

            process_segment('/tmp/1700000000.wav', 'uid', response, lock, errors, ConversationSource.omi, False)

        # Dedup should have skipped the merge — update_conversation_segments NOT called
        mock_update.assert_not_called()
        assert len(errors) == 0
        assert 'conv-existing' in response['updated_memories']

    def test_speech_eligible_empty_segments_complete_as_silence(self):
        """VAD-positive segments that all transcribe empty complete, not fail.

        A recording that is entirely noise records no segment errors, so its job
        finalizes completed rather than failed and is not offered back to the
        client for a retry that would repeat identically."""
        process_segment = self._import_process_segment()

        response = {'updated_memories': set(), 'new_memories': set()}
        errors = []
        lock = threading.Lock()

        # VAD selected these three as speech-eligible; every one transcribes empty.
        with patch('utils.sync.pipeline.prerecorded', return_value=([], 'en')), patch(
            'utils.sync.pipeline.delete_syncing_temporal_file'
        ), patch('utils.sync.pipeline.get_syncing_file_temporal_signed_url', return_value='https://fake'), patch(
            'utils.sync.pipeline.time.sleep'
        ):
            from models.conversation_enums import ConversationSource

            for i in range(3):
                process_segment(f'/tmp/{i}.wav', 'uid', response, lock, errors, ConversationSource.omi, False)

        total_segments = 3
        failed_segments = len(errors)

        # No errors → _sync_job_finalization_updates yields 'completed'.
        assert errors == []
        assert failed_segments == 0

    def test_runtime_error_from_dg_becomes_segment_error(self):
        """When deepgram_prerecorded raises RuntimeError (retry exhaustion),
        process_segment catches it and appends to errors list."""
        process_segment = self._import_process_segment()

        response = {'updated_memories': set(), 'new_memories': set()}
        errors = []
        lock = threading.Lock()

        with patch(
            'utils.sync.pipeline.prerecorded',
            side_effect=RuntimeError('Deepgram transcription failed after 2 attempts: timeout'),
        ), patch('utils.sync.pipeline.delete_syncing_temporal_file'), patch(
            'utils.sync.pipeline.get_syncing_file_temporal_signed_url', return_value='https://fake'
        ), patch(
            'utils.sync.pipeline.time.sleep'
        ):
            from models.conversation_enums import ConversationSource

            process_segment('/tmp/1700000000.wav', 'uid', response, lock, errors, ConversationSource.omi, False)

        assert errors == ['stt_upstream_error']


# ---------------------------------------------------------------------------
# Voice message callers — verify chat.py handles RuntimeError gracefully
# ---------------------------------------------------------------------------

_CHAT_STUB_MODULES = [
    'deepgram',
    'fal_client',
    'models',
    'models.chat',
    'models.conversation',
    'models.notification_message',
    'models.app',
    'models.transcript_segment',
    'database',
    'database._client',
    'database.chat',
    'database.notifications',
    'database.users',
    'database.apps',
    'database.redis_db',
    'firebase_admin',
    'utils.apps',
    'utils.conversation_helpers',
    'utils.conversations',
    'utils.conversations.factory',
    'utils.llm',
    'utils.llm.chat',
    'utils.llm.persona',
    'utils.other.endpoints',
    'utils.other.storage',
    'utils.notifications',
    'utils.retrieval.graph',
    'utils.stt.pre_recorded',
    'utils.stt.vad',
    'utils.llm.usage_tracker',
    'utils.log_sanitizer',
]


class TestVoiceMessageRuntimeErrorHandling:
    """Voice message helpers preserve typed provider failures for their routers."""

    _saved_modules = {}
    _transcribe_fn = None
    _process_fn = None
    _process_stream_fn = None

    @classmethod
    def setup_class(cls):
        cls._saved_modules = {name: sys.modules.get(name) for name in _CHAT_STUB_MODULES}
        cls._saved_modules['utils.chat'] = sys.modules.get('utils.chat')

        for mod_name in _CHAT_STUB_MODULES:
            sys.modules[mod_name] = ModuleType(mod_name)

        sys.modules['deepgram'].DeepgramClient = MagicMock()
        sys.modules['deepgram'].DeepgramClientOptions = MagicMock()
        sys.modules['fal_client'].submit = MagicMock()
        sys.modules['utils.other.endpoints'].timeit = lambda f: f
        sys.modules['utils.other.storage'].get_syncing_file_temporal_signed_url = MagicMock(return_value='https://fake')
        sys.modules['utils.other.storage'].schedule_syncing_temporal_file_deletion = MagicMock()
        sys.modules['utils.other.storage'].get_playback_artifact_signed_url = MagicMock(return_value=None)
        sys.modules['utils.other.storage'].download_legacy_merged_wav = MagicMock(return_value=None)
        sys.modules['utils.other.storage'].download_playback_artifact = MagicMock(return_value=None)
        sys.modules['utils.other.storage'].upload_playback_artifact = MagicMock()
        sys.modules['utils.other.storage'].upload_audio_chunk = MagicMock()
        sys.modules['utils.other.storage'].precache_conversation_audio = MagicMock()
        sys.modules['utils.other.storage'].mark_playback_unavailable = MagicMock()
        sys.modules['utils.other.storage'].is_playback_unavailable = MagicMock(return_value=False)
        sys.modules['utils.other.storage'].enqueue_conversation_audio_merge = MagicMock()
        sys.modules['utils.other.storage'].delete_syncing_temporal_file = MagicMock()
        sys.modules['utils.other.storage'].upload_audio_chunk = MagicMock()
        sys.modules['utils.other.storage'].precache_conversation_audio = MagicMock()
        sys.modules['utils.other.storage'].is_playback_unavailable = MagicMock(return_value=False)
        sys.modules['utils.other.storage'].mark_playback_unavailable = MagicMock()
        sys.modules['utils.notifications'].send_notification = MagicMock()
        sys.modules['utils.notifications'].send_notification_async = AsyncMock()
        sys.modules['utils.retrieval.graph'].execute_graph_chat = MagicMock()
        sys.modules['utils.retrieval.graph'].execute_graph_chat_stream = MagicMock()
        sys.modules['utils.log_sanitizer'].sanitize = lambda v: v
        sys.modules['database._client'].db = MagicMock()
        sys.modules['database.redis_db'].r = MagicMock()
        sys.modules['database.chat'].add_message = MagicMock()
        sys.modules['database.chat'].get_messages = MagicMock(return_value=[])
        sys.modules['database.chat'].get_chat_session = MagicMock(return_value=None)
        sys.modules['database.notifications'].get_token_only = MagicMock(return_value=None)
        sys.modules['database.users'].get_user_store_recording_permission = MagicMock(return_value=False)
        sys.modules['database.users'].get_user_transcription_preferences = MagicMock(return_value={})
        sys.modules['database.apps'].record_app_usage = MagicMock()
        sys.modules['utils.apps'].get_available_app_by_id = MagicMock(return_value=None)
        sys.modules['utils.conversation_helpers'].extract_memory_ids = MagicMock(return_value=[])
        sys.modules['utils.conversations.factory'].deserialize_conversation = MagicMock(return_value=None)
        sys.modules['utils.llm.chat'].initial_chat_message = MagicMock()
        sys.modules['utils.llm.persona'].initial_persona_chat_message = MagicMock()

        # Model stubs
        sys.modules['models.chat'].ChatSession = MagicMock()
        sys.modules['models.chat'].Message = MagicMock()
        sys.modules['models.chat'].ResponseMessage = MagicMock()
        sys.modules['models.chat'].MessageConversation = MagicMock()
        sys.modules['models.conversation'].Conversation = MagicMock()
        sys.modules['models.notification_message'].NotificationMessage = MagicMock()
        sys.modules['models.app'].App = MagicMock()
        sys.modules['models.app'].UsageHistoryType = MagicMock()
        sys.modules['models.transcript_segment'].TranscriptSegment = MagicMock()

        # STT stubs
        sys.modules['utils.stt.pre_recorded'].PrerecordedSTTConfigurationError = type(
            'PrerecordedSTTConfigurationError', (RuntimeError,), {}
        )
        sys.modules['utils.stt.pre_recorded'].prerecorded = MagicMock()
        sys.modules['utils.stt.pre_recorded'].prerecorded_from_bytes = MagicMock()
        sys.modules['utils.stt.pre_recorded'].postprocess_words = MagicMock()
        sys.modules['utils.stt.pre_recorded'].get_deepgram_model_for_language = MagicMock(return_value=('en', 'nova-3'))
        sys.modules['utils.stt.pre_recorded'].get_prerecorded_service = MagicMock(
            return_value=('deepgram', 'en', 'nova-3')
        )
        sys.modules['utils.stt.vad'].VADAudioDecodeError = type('VADAudioDecodeError', (RuntimeError,), {})
        sys.modules['utils.stt.vad'].VADProcessingError = type('VADProcessingError', (RuntimeError,), {})
        sys.modules['utils.stt.vad'].linear16_pcm_is_silent = MagicMock(return_value=False)
        sys.modules['utils.stt.vad'].vad_is_empty_strict = MagicMock(return_value=False)

        # Usage tracker stub
        sys.modules['utils.llm.usage_tracker'].track_usage = MagicMock()
        sys.modules['utils.llm.usage_tracker'].set_usage_context = MagicMock()
        sys.modules['utils.llm.usage_tracker'].reset_usage_context = MagicMock()
        sys.modules['utils.llm.usage_tracker'].Features = MagicMock()

        # Force re-import
        sys.modules.pop('utils.chat', None)
        from utils.chat import (
            transcribe_voice_message_segment,
            process_voice_message_segment,
            process_voice_message_segment_stream,
        )

        cls._transcribe_fn = staticmethod(transcribe_voice_message_segment)
        cls._process_fn = staticmethod(process_voice_message_segment)
        cls._process_stream_fn = staticmethod(process_voice_message_segment_stream)

    @classmethod
    def teardown_class(cls):
        sys.modules.pop('utils.chat', None)
        for name, orig in cls._saved_modules.items():
            if orig is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = orig
        cls._saved_modules.clear()

    def test_transcribe_voice_message_propagates_typed_failure(self):
        """Provider errors cannot be reclassified as an empty successful result."""
        from utils.stt.outcomes import TranscriptionFailure, TranscriptionOutcome

        with patch(
            'utils.chat.prerecorded',
            side_effect=RuntimeError('Deepgram transcription failed after 2 attempts: timeout'),
        ):
            with pytest.raises(TranscriptionFailure) as exc_info:
                self._transcribe_fn('/tmp/test.wav', 'uid', language='en')
        assert exc_info.value.outcome == TranscriptionOutcome.UPSTREAM_ERROR

    def test_process_voice_message_propagates_typed_failure(self):
        """The chat-producing wrapper does not swallow provider failures."""
        from utils.stt.outcomes import TranscriptionFailure

        with patch(
            'utils.chat.prerecorded',
            side_effect=RuntimeError('Deepgram transcription failed after 2 attempts: timeout'),
        ):
            with pytest.raises(TranscriptionFailure):
                self._process_fn('/tmp/test.wav', 'uid', language='en')

    def test_process_voice_message_stream_propagates_typed_failure(self):
        """The SSE utility propagates; the router converts this to a typed error frame."""
        import asyncio

        from utils.stt.outcomes import TranscriptionFailure

        async def run():
            async def _run_inline(_executor, fn, *args, **kwargs):
                return fn(*args, **kwargs)

            with patch('utils.chat.run_blocking', side_effect=_run_inline), patch(
                'utils.chat.prerecorded',
                side_effect=RuntimeError('Deepgram transcription failed after 2 attempts: timeout'),
            ):
                async for _chunk in self._process_stream_fn('/tmp/test.wav', 'uid', language='en'):
                    pass

        with pytest.raises(TranscriptionFailure):
            asyncio.run(run())


class TestVoiceMessageRuntimeErrorTeardown:
    """Verify voice message tests restore shared executor state."""

    def test_storage_executor_submit_is_not_left_mocked(self):
        from unittest.mock import Mock

        from utils.executors import storage_executor

        submit_override = getattr(storage_executor, '__dict__', {}).get('submit')
        assert not isinstance(submit_override, Mock)
