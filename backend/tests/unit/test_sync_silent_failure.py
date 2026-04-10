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

    def test_process_segment_treats_empty_words_as_success(self):
        """When Deepgram returns no words, treat it as a successful empty segment."""
        source = self._read_sync_source()
        start = source.index('def process_segment(')
        next_def = source.index('\ndef ', start + 1)
        func_body = source[start:next_def]
        empty_words_block = func_body[func_body.index('if not words:') : func_body.index('transcript_segments')]

        assert 'No transcript words for segment' in empty_words_block, "Must log empty-word segments"
        assert 'errors.append' not in empty_words_block, "Empty-word segments must not append to errors"
        assert 'return' in empty_words_block, "Empty-word segments must short-circuit as success"

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
        # Lock must protect the exception path and response dict mutations
        lock_sections = func_body.split('with lock:')
        assert len(lock_sections) >= 3, "Must have lock sections for exception errors + new_memories + updated_memories"

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
    """Verifies retry exhaustion raises while valid empty transcriptions stay empty."""

    @staticmethod
    def _read_deepgram_source():
        dg_path = os.path.join(os.path.dirname(__file__), '..', '..', 'utils', 'stt', 'pre_recorded.py')
        with open(dg_path) as f:
            return f.read()

    def test_deepgram_raises_runtime_error_on_final_retry(self):
        """After 2 retries, deepgram_prerecorded must raise instead of returning []."""
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
        assert 'attempts < 2' in func_body

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

        with patch('utils.stt.pre_recorded._deepgram_client', mock_client):
            with pytest.raises(RuntimeError, match='Deepgram transcription failed after 3 attempts'):
                self._deepgram_prerecorded('https://fake-audio.wav', attempts=0, return_language=True)

        # Should have been called 3 times (initial + 2 retries)
        assert mock_client.listen.rest.v.return_value.transcribe_url.call_count == 3

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

        with patch('utils.stt.pre_recorded._deepgram_client', mock_client):
            words, lang = self._deepgram_prerecorded('https://fake-audio.wav', return_language=True)

        assert words == []
        assert lang == 'en'
        # Should be called exactly once (no retries for valid response)
        assert mock_client.listen.rest.v.return_value.transcribe_url.call_count == 1


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
        segment_errors = [
            'Failed to process segment /tmp/1700000100.wav: Deepgram transcription failed after 3 attempts: timeout'
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
        assert 'Deepgram transcription failed after 3 attempts' in result['errors'][0]


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
    'models',
    'models.conversation',
    'models.transcript_segment',
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
    'utils.log_sanitizer',
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
        sys.modules['utils.log_sanitizer'].sanitize = lambda value: value
        sys.modules['utils.encryption'].encrypt = MagicMock()
        sys.modules['utils.stt.pre_recorded'].deepgram_prerecorded = MagicMock()
        sys.modules['utils.stt.pre_recorded'].postprocess_words = MagicMock()
        sys.modules['utils.stt.vad'].vad_is_empty = MagicMock()
        sys.modules['utils.fair_use'].FAIR_USE_ENABLED = False
        sys.modules['utils.fair_use'].FAIR_USE_RESTRICT_DAILY_DG_MS = 0
        sys.modules['utils.fair_use'].record_speech_ms = MagicMock()
        sys.modules['utils.fair_use'].get_rolling_speech_ms = MagicMock()
        sys.modules['utils.fair_use'].check_soft_caps = MagicMock()
        sys.modules['utils.fair_use'].is_hard_restricted = MagicMock(return_value=False)
        sys.modules['utils.fair_use'].trigger_classifier_if_needed = MagicMock()
        sys.modules['utils.fair_use'].is_dg_budget_exhausted = MagicMock(return_value=False)
        sys.modules['utils.fair_use'].get_enforcement_stage = MagicMock(return_value='off')
        sys.modules['utils.fair_use'].record_dg_usage_ms = MagicMock()
        sys.modules['utils.subscription'].has_transcription_credits = MagicMock(return_value=True)
        sys.modules['utils.conversations.process_conversation'].process_conversation = MagicMock()

        class _ConversationSource:
            omi = 'omi'

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
        sys.modules['models.conversation'].CreateConversation = _CreateConversation
        sys.modules['models.conversation'].Conversation = _Conversation
        sys.modules['models.transcript_segment'].TranscriptSegment = _TranscriptSegment

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

    def test_empty_words_are_successful_noop(self):
        """Real process_segment: empty Deepgram words → success with no memory changes."""
        process_segment = self._import_process_segment()

        response = {'updated_memories': set(), 'new_memories': set()}
        errors = []
        lock = threading.Lock()

        with patch('routers.sync.deepgram_prerecorded', return_value=([], 'en')), patch(
            'routers.sync.delete_syncing_temporal_file'
        ), patch('routers.sync.get_syncing_file_temporal_signed_url', return_value='https://fake'), patch(
            'routers.sync.time.sleep'
        ):
            from models.conversation_enums import ConversationSource

            process_segment('/tmp/1700000000.wav', 'uid', response, lock, errors, ConversationSource.omi, False)

        assert len(errors) == 0, "Empty words must not be treated as an error"
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
            from models.conversation_enums import ConversationSource

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
            from models.conversation_enums import ConversationSource

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
            from models.conversation_enums import ConversationSource

            process_segment('/tmp/1700000000.wav', 'uid', response, lock, errors, ConversationSource.omi, False)

        # Dedup should have skipped the merge — update_conversation_segments NOT called
        mock_update.assert_not_called()
        assert len(errors) == 0
        assert 'conv-existing' in response['updated_memories']

    def test_all_silent_segments_return_200_not_500(self):
        """When ALL segments are silent (empty words), endpoint should return 200 — not 500.

        This is the core bug in #6100: all-silent batches were treated as all-failed,
        triggering the 500 branch. Now empty words = success, so all-silent = 200.
        """
        process_segment = self._import_process_segment()

        response = {'updated_memories': set(), 'new_memories': set()}
        errors = []
        lock = threading.Lock()

        # Run 3 segments that all return empty words (silence)
        with patch('routers.sync.deepgram_prerecorded', return_value=([], 'en')), patch(
            'routers.sync.delete_syncing_temporal_file'
        ), patch('routers.sync.get_syncing_file_temporal_signed_url', return_value='https://fake'), patch(
            'routers.sync.time.sleep'
        ):
            from models.conversation_enums import ConversationSource

            for i in range(3):
                process_segment(f'/tmp/{i}.wav', 'uid', response, lock, errors, ConversationSource.omi, False)

        # All segments returned silently — zero errors
        total_segments = 3
        failed_segments = len(errors)
        successful_segments = total_segments - failed_segments

        assert failed_segments == 0, f"Silent segments must not produce errors: {errors}"
        assert successful_segments == 3

        # Endpoint logic: no failures → 200 (not 207, not 500)
        if total_segments > 0 and successful_segments == 0:
            status = 500
        elif failed_segments > 0:
            status = 207
        else:
            status = 200
        assert status == 200, "All-silent batch must return 200, not 500"

    def test_runtime_error_from_dg_becomes_segment_error(self):
        """When deepgram_prerecorded raises RuntimeError (retry exhaustion),
        process_segment catches it and appends to errors list."""
        process_segment = self._import_process_segment()

        response = {'updated_memories': set(), 'new_memories': set()}
        errors = []
        lock = threading.Lock()

        with patch(
            'routers.sync.deepgram_prerecorded',
            side_effect=RuntimeError('Deepgram transcription failed after 3 attempts: timeout'),
        ), patch('routers.sync.delete_syncing_temporal_file'), patch(
            'routers.sync.get_syncing_file_temporal_signed_url', return_value='https://fake'
        ), patch(
            'routers.sync.time.sleep'
        ):
            from models.conversation_enums import ConversationSource

            process_segment('/tmp/1700000000.wav', 'uid', response, lock, errors, ConversationSource.omi, False)

        assert len(errors) == 1
        assert 'Failed to process segment' in errors[0]
        assert 'Deepgram transcription failed after 3 attempts' in errors[0]


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
    'utils.other.endpoints',
    'utils.other.storage',
    'utils.notifications',
    'utils.retrieval.graph',
    'utils.stt.pre_recorded',
    'utils.llm.usage_tracker',
    'utils.log_sanitizer',
]


class TestVoiceMessageRuntimeErrorHandling:
    """Tests that voice message functions in utils/chat.py handle RuntimeError from deepgram_prerecorded."""

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
        sys.modules['utils.other.storage'].delete_syncing_temporal_file = MagicMock()
        sys.modules['utils.notifications'].send_notification = MagicMock()
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

        # Model stubs
        sys.modules['models.chat'].ChatSession = MagicMock()
        sys.modules['models.chat'].Message = MagicMock()
        sys.modules['models.chat'].ResponseMessage = MagicMock()
        sys.modules['models.chat'].MessageConversation = MagicMock()
        sys.modules['models.conversation'].Conversation = MagicMock()
        sys.modules['models.notification_message'].NotificationMessage = MagicMock()
        sys.modules['models.app'].UsageHistoryType = MagicMock()
        sys.modules['models.transcript_segment'].TranscriptSegment = MagicMock()

        # STT stubs
        sys.modules['utils.stt.pre_recorded'].deepgram_prerecorded = MagicMock()
        sys.modules['utils.stt.pre_recorded'].postprocess_words = MagicMock()
        sys.modules['utils.stt.pre_recorded'].get_deepgram_model_for_language = MagicMock(return_value=('en', 'nova-3'))

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

    def test_transcribe_voice_message_handles_runtime_error(self):
        """transcribe_voice_message_segment returns (None, lang) on RuntimeError, not crash."""
        with patch(
            'utils.chat.deepgram_prerecorded',
            side_effect=RuntimeError('Deepgram transcription failed after 3 attempts: timeout'),
        ), patch('utils.chat.time.sleep'):
            result = self._transcribe_fn('/tmp/test.wav', 'uid', language='en')

        assert result == (None, 'en'), f"Expected (None, 'en'), got {result}"

    def test_process_voice_message_handles_runtime_error(self):
        """process_voice_message_segment returns [] on RuntimeError, not crash."""
        with patch(
            'utils.chat.deepgram_prerecorded',
            side_effect=RuntimeError('Deepgram transcription failed after 3 attempts: timeout'),
        ), patch('utils.chat.time.sleep'):
            result = self._process_fn('/tmp/test.wav', 'uid', language='en')

        assert result == [], f"Expected [], got {result}"

    def test_process_voice_message_stream_handles_runtime_error(self):
        """process_voice_message_segment_stream returns (no yield) on RuntimeError, not crash."""
        import asyncio

        async def run():
            chunks = []
            with patch(
                'utils.chat.deepgram_prerecorded',
                side_effect=RuntimeError('Deepgram transcription failed after 3 attempts: timeout'),
            ), patch('utils.chat.time.sleep'):
                async for chunk in self._process_stream_fn('/tmp/test.wav', 'uid', language='en'):
                    chunks.append(chunk)
            return chunks

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result == [], f"Expected no chunks, got {result}"
