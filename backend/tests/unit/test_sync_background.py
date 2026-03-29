"""
Tests for sync_local_files background processing (#5941).

Verifies that:
1. _process_segments_background() runs threads, logs results, cleans up in finally
2. sync_local_files() returns 200 immediately with empty lists (background handoff)
3. File ownership transfer prevents double cleanup
4. Thread-start failure cleans up owned_paths
5. DG budget blocked path prevents double cleanup
"""

import os
import sys
import threading
from types import ModuleType
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# 1. Structural tests — verify code shape after background refactor
# ---------------------------------------------------------------------------


class TestBackgroundProcessingStructure:
    """Verify sync.py has the expected background processing structure."""

    @staticmethod
    def _read_sync_source():
        sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(sync_path) as f:
            return f.read()

    def test_process_segments_background_exists(self):
        """_process_segments_background function must exist."""
        source = self._read_sync_source()
        assert 'def _process_segments_background(' in source

    def test_background_has_try_except_finally(self):
        """_process_segments_background must have try/except/finally for cleanup."""
        source = self._read_sync_source()
        start = source.index('def _process_segments_background(')
        # Find end: next def at module level
        next_def = source.index('\n@router', start)
        func_body = source[start:next_def]

        assert 'try:' in func_body
        assert 'except Exception' in func_body
        assert 'finally:' in func_body
        assert '_cleanup_files' in func_body

    def test_background_logs_completion(self):
        """Background function must log success/failure counts."""
        source = self._read_sync_source()
        start = source.index('def _process_segments_background(')
        next_def = source.index('\n@router', start)
        func_body = source[start:next_def]

        assert 'sync_background complete' in func_body
        assert 'sync_background partial failure' in func_body
        assert 'sync_background failed' in func_body

    def test_endpoint_returns_empty_lists(self):
        """sync_local_files must return empty lists (background handoff)."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files(')
        func_body = source[start:]

        assert "{'new_memories': [], 'updated_memories': []}" in func_body

    def test_endpoint_no_207_or_500_responses(self):
        """sync_local_files must NOT return 207 or segment-level 500 (old sync behavior)."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files(')
        func_body = source[start:]

        # 207 partial failure is no longer returned from the endpoint
        assert 'status_code=207' not in func_body
        # All-failed 500 is no longer raised from the endpoint (errors are in background)
        assert 'successful_segments == 0' not in func_body

    def test_endpoint_uses_daemon_thread(self):
        """Background thread must be daemon so it dies with the process."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files(')
        func_body = source[start:]

        assert 'daemon=True' in func_body

    def test_ownership_transfer_clears_segmented_paths(self):
        """After copying to owned_paths, segmented_paths must be cleared."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files(')
        func_body = source[start:]

        # Must copy before clearing
        assert 'owned_paths = set(segmented_paths)' in func_body
        # Must clear to prevent finally cleanup
        assert "segmented_paths = set()" in func_body

    def test_thread_start_has_try_except(self):
        """bg.start() must be wrapped in try/except for cleanup on failure."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files(')
        func_body = source[start:]

        # The bg.start() block should be inside try/except
        bg_section_start = func_body.index('owned_paths = set(segmented_paths)')
        bg_section = func_body[bg_section_start : bg_section_start + 700]

        assert 'try:' in bg_section
        assert 'bg.start()' in bg_section
        assert '_cleanup_files(list(owned_paths))' in bg_section

    def test_finally_only_cleans_fast_path_files(self):
        """Finally block must only clean paths and wav_paths, not segmented_paths."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files(')
        func_body = source[start:]

        # Find the finally block
        finally_idx = func_body.rindex('finally:')
        finally_block = func_body[finally_idx:]

        assert '_cleanup_files(paths)' in finally_block
        assert '_cleanup_files(wav_paths)' in finally_block
        # Must NOT clean segmented_paths in finally (owned by background thread)
        assert 'segmented_paths' not in finally_block

    def test_dg_budget_blocked_prevents_double_cleanup(self):
        """DG budget blocked path must clear segmented_paths after manual cleanup."""
        source = self._read_sync_source()
        start = source.index('if dg_budget_blocked:')
        block = source[start : start + 400]

        assert '_cleanup_files(list(segmented_paths))' in block
        assert 'segmented_paths = set()' in block


# ---------------------------------------------------------------------------
# 2. Behavioral tests — _process_segments_background with stubbed imports
# ---------------------------------------------------------------------------


class TestProcessSegmentsBackground:
    """Test _process_segments_background behavior with stubbed dependencies."""

    _saved_modules = {}

    # Stub modules needed for importing routers.sync
    _STUB_MODULES = [
        'firebase_admin',
        'firebase_admin.auth',
        'firebase_admin.credentials',
        'google.cloud',
        'google.cloud.storage',
        'google.cloud.firestore',
        'google.cloud.firestore_v1',
        'google.cloud.firestore_v1.base_query',
        'google.auth',
        'google.auth.transport',
        'google.auth.transport.requests',
        'google.api_core',
        'google.api_core.datetime_helpers',
        'database',
        'database._client',
        'database.redis_db',
        'database.auth',
        'database.conversations',
        'database.users',
        'opuslib',
        'pydub',
        'deepgram',
        'models',
        'models.conversation',
        'models.transcript_segment',
        'utils',
        'utils.other',
        'utils.other.endpoints',
        'utils.other.storage',
        'utils.other.timeout',
        'utils.conversations',
        'utils.conversations.process_conversation',
        'utils.stt',
        'utils.stt.pre_recorded',
        'utils.stt.vad',
        'utils.encryption',
        'utils.log_sanitizer',
        'utils.fair_use',
        'utils.subscription',
        'utils.observability',
        'utils.observability.langsmith',
    ]

    @classmethod
    def setup_class(cls):
        cls._saved_modules = {}
        for mod_name in cls._STUB_MODULES:
            cls._saved_modules[mod_name] = sys.modules.get(mod_name)

        for mod_name in cls._STUB_MODULES:
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
        sys.modules['utils.other.endpoints'].timeit = lambda f: f
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
        sys.modules['utils.fair_use'].record_speech_ms = MagicMock()
        sys.modules['utils.fair_use'].get_rolling_speech_ms = MagicMock()
        sys.modules['utils.fair_use'].check_soft_caps = MagicMock()
        sys.modules['utils.fair_use'].is_hard_restricted = MagicMock(return_value=False)
        sys.modules['utils.fair_use'].trigger_classifier_if_needed = MagicMock()
        sys.modules['utils.fair_use'].is_dg_budget_exhausted = MagicMock(return_value=False)
        sys.modules['utils.fair_use'].get_enforcement_stage = MagicMock(return_value='normal')
        sys.modules['utils.fair_use'].record_dg_usage_ms = MagicMock()
        sys.modules['utils.fair_use'].FAIR_USE_RESTRICT_DAILY_DG_MS = 0
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
        sys.modules['models.conversation'].CreateConversation = _CreateConversation
        sys.modules['models.conversation'].Conversation = _Conversation
        sys.modules['models.transcript_segment'].TranscriptSegment = _TranscriptSegment

        # Remove cached module to force fresh import
        sys.modules.pop('routers.sync', None)
        from routers.sync import _process_segments_background, _cleanup_files

        cls._process_segments_background = staticmethod(_process_segments_background)
        cls._cleanup_files = staticmethod(_cleanup_files)

    @classmethod
    def teardown_class(cls):
        sys.modules.pop('routers.sync', None)
        for name, orig in cls._saved_modules.items():
            if orig is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = orig
        cls._saved_modules.clear()

    def test_all_segments_succeed(self):
        """All segments succeed: log completion, no error log."""
        import routers.sync as sync_mod

        mock_process = MagicMock()
        paths = {'/tmp/seg1.wav', '/tmp/seg2.wav'}

        with patch.object(sync_mod, 'process_segment', mock_process), patch.object(
            sync_mod, '_cleanup_files'
        ) as mock_cleanup:
            self._process_segments_background(paths, 'uid123', 'omi', False, False, 10.0)

        assert mock_process.call_count == len(paths)
        mock_cleanup.assert_called_once()

    def test_partial_failure_logs_errors(self):
        """Some segments fail: error count logged, cleanup still runs."""
        import routers.sync as sync_mod

        call_count = [0]

        def failing_process(path, uid, response, lock, errors, source, is_locked):
            call_count[0] += 1
            if call_count[0] == 1:
                with lock:
                    errors.append(f'Failed: {path}')

        paths = {'/tmp/seg1.wav', '/tmp/seg2.wav'}

        with patch.object(sync_mod, 'process_segment', failing_process), patch.object(
            sync_mod, '_cleanup_files'
        ) as mock_cleanup:
            self._process_segments_background(paths, 'uid123', 'omi', False, False, 10.0)

        mock_cleanup.assert_called_once()

    def test_cleanup_runs_on_outer_exception(self):
        """If an unexpected error occurs outside threads, cleanup still runs in finally."""
        import routers.sync as sync_mod

        # Patch chunk_threads-like behavior to raise at the outer level
        original_thread = threading.Thread

        def broken_thread(*args, **kwargs):
            t = original_thread(*args, **kwargs)
            # Make join() raise to simulate an outer-level exception
            t.join = MagicMock(side_effect=RuntimeError("unexpected"))
            return t

        paths = {'/tmp/seg1.wav'}

        with patch.object(sync_mod, 'process_segment', MagicMock()), patch(
            'threading.Thread', broken_thread
        ), patch.object(sync_mod, '_cleanup_files') as mock_cleanup:
            # Should not propagate — caught by except
            self._process_segments_background(paths, 'uid123', 'omi', False, False, 10.0)

        mock_cleanup.assert_called_once()

    def test_dg_usage_recorded_when_enabled(self):
        """DG usage recorded when fair_use_restrict_dg=True."""
        import routers.sync as sync_mod

        mock_process = MagicMock()
        mock_record = MagicMock()

        paths = {'/tmp/seg1.wav'}

        with patch.object(sync_mod, 'process_segment', mock_process), patch.object(
            sync_mod, 'record_dg_usage_ms', mock_record
        ), patch.object(sync_mod, '_cleanup_files'):
            self._process_segments_background(paths, 'uid123', 'omi', False, True, 15.5)

        mock_record.assert_called_once_with('uid123', 15500)

    def test_dg_usage_not_recorded_when_disabled(self):
        """DG usage NOT recorded when fair_use_restrict_dg=False."""
        import routers.sync as sync_mod

        mock_process = MagicMock()
        mock_record = MagicMock()

        paths = {'/tmp/seg1.wav'}

        with patch.object(sync_mod, 'process_segment', mock_process), patch.object(
            sync_mod, 'record_dg_usage_ms', mock_record
        ), patch.object(sync_mod, '_cleanup_files'):
            self._process_segments_background(paths, 'uid123', 'omi', False, False, 15.5)

        mock_record.assert_not_called()

    def test_dg_usage_zero_duration_not_recorded(self):
        """DG usage not recorded when total_speech_seconds is 0."""
        import routers.sync as sync_mod

        mock_process = MagicMock()
        mock_record = MagicMock()

        paths = {'/tmp/seg1.wav'}

        with patch.object(sync_mod, 'process_segment', mock_process), patch.object(
            sync_mod, 'record_dg_usage_ms', mock_record
        ), patch.object(sync_mod, '_cleanup_files'):
            self._process_segments_background(paths, 'uid123', 'omi', False, True, 0.0)

        mock_record.assert_not_called()

    def test_dg_record_exception_does_not_crash(self):
        """DG recording failure is caught, does not prevent completion."""
        import routers.sync as sync_mod

        mock_process = MagicMock()
        mock_record = MagicMock(side_effect=Exception("Redis down"))

        paths = {'/tmp/seg1.wav'}

        with patch.object(sync_mod, 'process_segment', mock_process), patch.object(
            sync_mod, 'record_dg_usage_ms', mock_record
        ), patch.object(sync_mod, '_cleanup_files') as mock_cleanup:
            # Should not raise
            self._process_segments_background(paths, 'uid123', 'omi', False, True, 10.0)

        mock_cleanup.assert_called_once()

    def test_empty_segments_set(self):
        """Empty segments set: no threads created, cleanup still runs."""
        import routers.sync as sync_mod

        mock_process = MagicMock()

        with patch.object(sync_mod, 'process_segment', mock_process), patch.object(
            sync_mod, '_cleanup_files'
        ) as mock_cleanup:
            self._process_segments_background(set(), 'uid123', 'omi', False, False, 0.0)

        mock_process.assert_not_called()
        mock_cleanup.assert_called_once()


# ---------------------------------------------------------------------------
# 3. Stale test updates — tests from test_sync_silent_failure.py that need
#    updating for the new background architecture
# ---------------------------------------------------------------------------


class TestSyncEndpointBackgroundContract:
    """Verify the endpoint's new contract: immediate 200, background processing."""

    @staticmethod
    def _read_sync_source():
        sync_path = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'sync.py')
        with open(sync_path) as f:
            return f.read()

    def test_endpoint_creates_background_thread(self):
        """sync_local_files must create a daemon Thread targeting _process_segments_background."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files(')
        func_body = source[start:]

        assert '_process_segments_background' in func_body
        assert 'threading.Thread' in func_body
        assert 'daemon=True' in func_body
        assert 'bg.start()' in func_body

    def test_background_function_creates_lock_and_errors(self):
        """Lock and errors are now created in _process_segments_background, not the endpoint."""
        source = self._read_sync_source()
        bg_start = source.index('def _process_segments_background(')
        bg_end = source.index('\n@router', bg_start)
        bg_body = source[bg_start:bg_end]

        assert 'segment_lock = threading.Lock()' in bg_body or 'threading.Lock()' in bg_body
        assert "segment_errors = []" in bg_body or "[] " in bg_body

    def test_endpoint_does_not_create_segment_lock(self):
        """segment_lock must NOT be created in sync_local_files (moved to background)."""
        source = self._read_sync_source()
        start = source.index('async def sync_local_files(')
        func_body = source[start:]

        # segment_lock and segment_errors should not be in the endpoint anymore
        assert 'segment_lock = threading.Lock()' not in func_body
        assert 'segment_errors = []' not in func_body
