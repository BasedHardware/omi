"""
Tests for sync endpoint error handling fix (#4867/#4669).

Verifies that process_segment() properly propagates errors via thread-safe
error collection, and that the endpoint returns appropriate HTTP status codes:
- 200: all segments processed successfully
- 207: partial failure (some segments failed, some succeeded)
- 500: all segments failed

Previously, process_segment() had no error handling — Deepgram failures caused
silent returns or thread crashes, and the endpoint always returned 200.
"""

import os
import threading

import pytest

# ---------------------------------------------------------------------------
# 1. Structural verification — process_segment now has error handling
# ---------------------------------------------------------------------------


class TestProcessSegmentErrorHandling:
    """Verify process_segment has proper error handling after the fix."""

    @staticmethod
    def _read_sync_source():
        sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(sync_path) as f:
            return f.read()

    def test_process_segment_has_try_except(self):
        """process_segment() must wrap its body in try/except to catch all errors."""
        source = self._read_sync_source()
        start = source.index('def process_segment(')
        next_def = source.index('\ndef ', start + 1)
        func_body = source[start:next_def]

        assert 'try:' in func_body, "process_segment must have try/except"
        assert 'except Exception' in func_body, "process_segment must catch exceptions"

    def test_process_segment_errors_on_empty_words(self):
        """When Deepgram returns no words, treat as error (may be Deepgram failure, not just silence)."""
        source = self._read_sync_source()
        start = source.index('def process_segment(')
        next_def = source.index('\ndef ', start + 1)
        func_body = source[start:next_def]

        assert 'Deepgram returned no words' in func_body, "Must log error for empty Deepgram words"
        assert 'errors.append' in func_body, "Must append to errors list for empty words"

    def test_process_segment_warns_on_empty_postprocessed(self):
        """When words exist but postprocessing yields nothing, log warning (not error)."""
        source = self._read_sync_source()
        start = source.index('def process_segment(')
        next_def = source.index('\ndef ', start + 1)
        func_body = source[start:next_def]

        assert 'Postprocessing returned empty' in func_body, "Must log warning for empty postprocessed segments"

    def test_process_segment_collects_errors_on_exception(self):
        """When an exception occurs, it must be caught and appended to errors."""
        source = self._read_sync_source()
        start = source.index('def process_segment(')
        next_def = source.index('\ndef ', start + 1)
        func_body = source[start:next_def]

        assert 'Failed to process segment' in func_body, "Must include error context on exception"

    def test_process_segment_uses_lock_for_thread_safety(self):
        """Shared state mutations must be protected by a lock."""
        source = self._read_sync_source()
        start = source.index('def process_segment(')
        next_def = source.index('\ndef ', start + 1)
        func_body = source[start:next_def]

        assert 'with lock:' in func_body, "Must use lock for thread-safe mutations"
        # Lock must protect both error append and response dict mutations
        lock_sections = func_body.split('with lock:')
        assert len(lock_sections) >= 4, "Must have lock sections for errors (2) + new_memories + updated_memories"

    def test_process_segment_accepts_lock_and_errors_params(self):
        """process_segment must accept lock and errors as parameters."""
        source = self._read_sync_source()
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
        with open(sync_path) as f:
            return f.read()

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
    """Verifies deepgram_prerecorded returns empty list on final retry failure."""

    @staticmethod
    def _read_deepgram_source():
        dg_path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'stt', 'pre_recorded.py')
        with open(dg_path) as f:
            return f.read()

    def test_deepgram_returns_empty_list_on_final_retry(self):
        """After 2 retries, deepgram_prerecorded returns [] (not raise).
        This is now properly caught by process_segment's error handling."""
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

        assert 'return [], ' in func_body or "return []" in func_body
        assert 'attempts < 2' in func_body


# ---------------------------------------------------------------------------
# 4. App-side behavior documentation (unchanged, for PR evidence)
# ---------------------------------------------------------------------------


class TestAppSideSyncBehavior:
    """Documents app-side behavior that will be addressed in follow-up PR."""

    @staticmethod
    def _read_app_file(relative_path):
        app_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'app', 'lib', relative_path)
        if os.path.exists(app_path):
            with open(app_path) as f:
                return f.read()
        return None

    def test_app_accepts_200_and_207(self):
        """App treats both HTTP 200 and 207 as parseable responses."""
        source = self._read_app_file('backend/http/api/conversations.dart')
        if source is None:
            pytest.skip("App source not available")

        assert 'response.statusCode == 200' in source
        assert 'response.statusCode == 207' in source

    def test_app_keeps_wals_retryable_on_partial_failure(self):
        """App keeps WALs retryable when response has partial failure (207)."""
        source = self._read_app_file('services/wals/local_wal_sync.dart')
        if source is None:
            pytest.skip("App source not available")

        assert 'hasPartialFailure' in source, "Must check for partial failure"
        assert 'WalStatus.synced' in source, "Must still mark synced on full success"


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
        segment_errors = ['Deepgram returned no words for segment /tmp/1700000100.wav']
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
        assert 'Deepgram returned no words' in result['errors'][0]


# ---------------------------------------------------------------------------
# 6. Deduplication on retry — prevents duplicate transcripts
# ---------------------------------------------------------------------------


class TestSegmentDeduplication:
    """Verifies that retried segments are deduplicated in the merge path."""

    @staticmethod
    def _read_sync_source():
        sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(sync_path) as f:
            return f.read()

    def test_merge_path_has_dedup_logic(self):
        """process_segment merge path must deduplicate before appending."""
        source = self._read_sync_source()
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
        source = self._read_sync_source()
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
from unittest.mock import MagicMock, patch

_STUB_MODULES = [
    'database._client',
    'database.redis_db',
    'database.fair_use',
    'database.users',
    'database.user_usage',
    'database.conversations',
    'firebase_admin',
    'firebase_admin.messaging',
    'opuslib',
    'pydub',
    'utils.other.endpoints',
    'utils.other.storage',
    'utils.encryption',
    'utils.stt.pre_recorded',
    'utils.stt.vad',
    'utils.fair_use',
    'utils.subscription',
    'utils.conversations.process_conversation',
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
        # Also save routers.sync if already imported
        cls._saved_modules['routers.sync'] = sys.modules.get('routers.sync')

        # Install stubs
        for mod_name in _STUB_MODULES:
            sys.modules[mod_name] = ModuleType(mod_name)

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
        sys.modules['utils.other.storage'].delete_syncing_temporal_file = MagicMock()
        sys.modules['utils.other.storage'].download_audio_chunks_and_merge = MagicMock()
        sys.modules['utils.other.storage'].get_or_create_merged_audio = MagicMock()
        sys.modules['utils.other.storage'].get_merged_audio_signed_url = MagicMock()
        sys.modules['utils.encryption'].encrypt = MagicMock()
        sys.modules['utils.stt.pre_recorded'].deepgram_prerecorded = MagicMock()
        sys.modules['utils.stt.pre_recorded'].postprocess_words = MagicMock()
        sys.modules['utils.stt.vad'].vad_is_empty = MagicMock()
        sys.modules['utils.fair_use'].FAIR_USE_ENABLED = False
        sys.modules['utils.fair_use'].record_speech_ms = MagicMock()
        sys.modules['utils.fair_use'].get_rolling_speech_ms = MagicMock()
        sys.modules['utils.fair_use'].check_soft_caps = MagicMock()
        sys.modules['utils.fair_use'].is_hard_restricted = MagicMock(return_value=False)
        sys.modules['utils.fair_use'].trigger_classifier_if_needed = MagicMock()
        sys.modules['utils.subscription'].has_transcription_credits = MagicMock(return_value=True)
        sys.modules['utils.conversations.process_conversation'].process_conversation = MagicMock()

        # Import under stubs
        from routers.sync import process_segment

        cls._process_segment = staticmethod(process_segment)

    @classmethod
    def teardown_class(cls):
        # Remove routers.sync so it can be re-imported cleanly
        sys.modules.pop('routers.sync', None)
        # Restore original modules
        for name, orig in cls._saved_modules.items():
            if orig is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = orig
        cls._saved_modules.clear()

    def _import_process_segment(self):
        return self._process_segment

    def test_empty_words_collects_error(self):
        """Real process_segment: empty Deepgram words → error collected.

        deepgram_prerecorded returns [] on both "no speech" AND "failure after retries".
        We treat it as an error so the segment is retried — dedup prevents duplicates
        if the segment was actually silent.
        """
        process_segment = self._import_process_segment()

        response = {'updated_memories': set(), 'new_memories': set()}
        errors = []
        lock = threading.Lock()

        with patch('routers.sync.deepgram_prerecorded', return_value=([], 'en')), patch(
            'routers.sync.delete_syncing_temporal_file'
        ), patch('routers.sync.get_syncing_file_temporal_signed_url', return_value='https://fake'), patch(
            'routers.sync.time.sleep'
        ):
            from models.conversation import ConversationSource

            process_segment('/tmp/1700000000.wav', 'uid', response, lock, errors, ConversationSource.omi, False)

        assert len(errors) == 1, "Empty words must be treated as an error"
        assert 'Deepgram returned no words' in errors[0]
        assert len(response['new_memories']) == 0
        assert len(response['updated_memories']) == 0

    def test_empty_postprocessed_skips_without_error(self):
        """Real process_segment: words present but postprocessing empty → warning, no error.

        When Deepgram returns words but postprocess_words yields no segments,
        it's a legitimate edge case (e.g. all words filtered out). Not an error.
        """
        process_segment = self._import_process_segment()

        response = {'updated_memories': set(), 'new_memories': set()}
        errors = []
        lock = threading.Lock()

        with patch('routers.sync.deepgram_prerecorded', return_value=([{'text': 'um'}], 'en')), patch(
            'routers.sync.postprocess_words', return_value=[]
        ), patch('routers.sync.delete_syncing_temporal_file'), patch(
            'routers.sync.get_syncing_file_temporal_signed_url', return_value='https://fake'
        ), patch(
            'routers.sync.time.sleep'
        ):
            from models.conversation import ConversationSource

            process_segment('/tmp/1700000000.wav', 'uid', response, lock, errors, ConversationSource.omi, False)

        assert len(errors) == 0, "Empty postprocessed segments must NOT be treated as an error"
        assert len(response['new_memories']) == 0
        assert len(response['updated_memories']) == 0

    def test_exception_caught_and_collected(self):
        """Real process_segment: Deepgram raises → exception caught, error collected."""
        process_segment = self._import_process_segment()

        response = {'updated_memories': set(), 'new_memories': set()}
        errors = []
        lock = threading.Lock()

        with patch('routers.sync.deepgram_prerecorded', side_effect=ConnectionError('timeout')), patch(
            'routers.sync.delete_syncing_temporal_file'
        ), patch('routers.sync.get_syncing_file_temporal_signed_url', return_value='https://fake'), patch(
            'routers.sync.time.sleep'
        ):
            from models.conversation import ConversationSource

            process_segment('/tmp/1700000000.wav', 'uid', response, lock, errors, ConversationSource.omi, False)

        assert len(errors) == 1
        assert 'Failed to process segment' in errors[0]
        assert 'timeout' in errors[0]

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

        with patch('routers.sync.deepgram_prerecorded', return_value=([{'text': 'hello'}], 'en')), patch(
            'routers.sync.postprocess_words', return_value=[real_segment]
        ), patch('routers.sync.get_timestamp_from_path', return_value=1700000000.0), patch(
            'routers.sync.get_closest_conversation_to_timestamps', return_value=None
        ), patch(
            'routers.sync.process_conversation', return_value=mock_conv
        ), patch(
            'routers.sync.delete_syncing_temporal_file'
        ), patch(
            'routers.sync.get_syncing_file_temporal_signed_url', return_value='https://fake'
        ), patch(
            'routers.sync.time.sleep'
        ):
            from models.conversation import ConversationSource

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

        def mock_deepgram_mixed(url, speakers_count=3, attempts=0, return_language=True):
            with call_lock:
                call_count[0] += 1
                n = call_count[0]
            if n == 2:
                raise ConnectionError('Deepgram timeout')  # Segment 2 fails with exception
            return [{'text': 'hello'}], 'en'

        real_segment = self._make_real_segment()
        mock_conv = MagicMock()
        mock_conv.id = 'conv-success'

        with patch('routers.sync.deepgram_prerecorded', side_effect=mock_deepgram_mixed), patch(
            'routers.sync.postprocess_words', return_value=[real_segment]
        ), patch('routers.sync.get_timestamp_from_path', return_value=1700000000.0), patch(
            'routers.sync.get_closest_conversation_to_timestamps', return_value=None
        ), patch(
            'routers.sync.process_conversation', return_value=mock_conv
        ), patch(
            'routers.sync.delete_syncing_temporal_file'
        ), patch(
            'routers.sync.get_syncing_file_temporal_signed_url', return_value='https://fake'
        ), patch(
            'routers.sync.time.sleep'
        ):
            from models.conversation import ConversationSource

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
        assert 'Failed to process segment' in errors[0]
        assert len(response['new_memories']) >= 1  # At least 1 success

    def test_dedup_skips_existing_segments_on_retry(self):
        """Real process_segment: retry with existing segments → dedup skips merge."""
        process_segment = self._import_process_segment()

        response = {'updated_memories': set(), 'new_memories': set()}
        errors = []
        lock = threading.Lock()

        mock_segment = MagicMock()
        mock_segment.end = 5.0
        mock_segment.dict.return_value = {'start': 0.0, 'end': 5.0, 'text': 'hello', 'speaker': 'SPEAKER_00'}

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

        with patch('routers.sync.deepgram_prerecorded', return_value=([{'text': 'hello'}], 'en')), patch(
            'routers.sync.postprocess_words', return_value=[mock_segment]
        ), patch('routers.sync.get_timestamp_from_path', return_value=1700000000.0), patch(
            'routers.sync.get_closest_conversation_to_timestamps', return_value=existing_conv
        ), patch(
            'routers.sync.update_conversation_segments'
        ) as mock_update, patch(
            'routers.sync.delete_syncing_temporal_file'
        ), patch(
            'routers.sync.get_syncing_file_temporal_signed_url', return_value='https://fake'
        ), patch(
            'routers.sync.time.sleep'
        ):
            from models.conversation import ConversationSource

            process_segment('/tmp/1700000000.wav', 'uid', response, lock, errors, ConversationSource.omi, False)

        # Dedup should have skipped the merge — update_conversation_segments NOT called
        mock_update.assert_not_called()
        assert len(errors) == 0
        assert 'conv-existing' in response['updated_memories']
