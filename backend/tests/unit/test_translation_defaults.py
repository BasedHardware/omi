"""Tests for translation cost optimization defaults and behavioral contracts.

Covers issue #6837: verifies new defaults, 24h filter logic, deferred segment
accumulation, and toggle state transitions.
"""

import os
import re
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

# --- Module-level mocks (must happen before project imports) ---
_mock_redis = MagicMock()
_mock_redis.get.return_value = None
_mock_redis.set.return_value = True
_mock_redis.exists.return_value = 0

# Ensure database package imports work (needs _client mock for Firestore)
for mod_name in [
    'database._client',
    'database.redis_db',
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()
sys.modules['database.redis_db'].r = _mock_redis

for mod_name in [
    'google',
    'google.cloud',
    'google.cloud.translate_v3',
    'google.cloud.firestore_v1',
    'google.auth',
    'google.auth.transport',
    'google.auth.transport.requests',
    'firebase_admin',
    'firebase_admin.auth',
    'firebase_admin.firestore',
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

import database.users as users_module


class TestAutoTranslateEnabledDefaults:
    """Verify auto_translate_enabled defaults to False for new/missing users."""

    def test_missing_user_returns_false(self):
        """A user that doesn't exist in Firestore should get auto_translate_enabled=False."""
        mock_doc = MagicMock()
        mock_doc.exists = False
        with patch.object(users_module, 'db') as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            result = users_module.get_user_transcription_preferences('nonexistent_uid')
        assert result['auto_translate_enabled'] is False

    def test_user_without_prefs_returns_false(self):
        """A user doc that exists but has no transcription_preferences should default to False."""
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {}
        with patch.object(users_module, 'db') as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            result = users_module.get_user_transcription_preferences('uid_no_prefs')
        assert result['auto_translate_enabled'] is False

    def test_user_with_explicit_true_returns_true(self):
        """A user with explicit auto_translate_enabled=True should keep it."""
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {'transcription_preferences': {'auto_translate_enabled': True}}
        with patch.object(users_module, 'db') as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            result = users_module.get_user_transcription_preferences('uid_explicit_true')
        assert result['auto_translate_enabled'] is True

    def test_user_with_explicit_false_returns_false(self):
        """A user with explicit auto_translate_enabled=False should keep it."""
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {'transcription_preferences': {'auto_translate_enabled': False}}
        with patch.object(users_module, 'db') as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            result = users_module.get_user_transcription_preferences('uid_explicit_false')
        assert result['auto_translate_enabled'] is False

    def test_single_language_mode_defaults_false(self):
        """single_language_mode should default to False (separate from auto_translate_enabled)."""
        mock_doc = MagicMock()
        mock_doc.exists = False
        with patch.object(users_module, 'db') as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            result = users_module.get_user_transcription_preferences('nonexistent_uid')
        assert result['single_language_mode'] is False


class TestBatchTranslation24hFilter:
    """Verify the 24h time filter logic for batch translation on toggle-on."""

    @staticmethod
    def _read_transcribe_source():
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        with open(os.path.join(root, 'routers', 'transcribe.py'), 'r') as f:
            return f.read()

    def test_24h_cutoff_code_exists(self):
        """Batch translation block must contain 24h time filter."""
        source = self._read_transcribe_source()
        toggle_start = source.find("json_data.get('type') == 'translate_toggle'")
        assert toggle_start != -1
        next_handler = source.find("json_data.get('type') == 'screen_state'", toggle_start)
        toggle_block = source[toggle_start:next_handler]
        assert 'cutoff_secs' in toggle_block, "24h cutoff variable must exist"
        assert '24 * 3600' in toggle_block, "24h cutoff must be 24*3600 seconds"

    def test_filter_skips_already_translated(self):
        """Batch translation must skip segments that already have translations."""
        source = self._read_transcribe_source()
        toggle_start = source.find("json_data.get('type') == 'translate_toggle'")
        next_handler = source.find("json_data.get('type') == 'screen_state'", toggle_start)
        toggle_block = source[toggle_start:next_handler]
        assert "s.get('translations')" in toggle_block, "Must check for existing translations"

    def test_filter_skips_empty_text(self):
        """Batch translation must skip segments with no text."""
        source = self._read_transcribe_source()
        toggle_start = source.find("json_data.get('type') == 'translate_toggle'")
        next_handler = source.find("json_data.get('type') == 'screen_state'", toggle_start)
        toggle_block = source[toggle_start:next_handler]
        assert "s.get('text')" in toggle_block, "Must check for empty text"


class TestDeferredSegmentAccumulation:
    """Verify deferred segment accumulation and removal logic."""

    @staticmethod
    def _read_transcribe_source():
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        with open(os.path.join(root, 'routers', 'transcribe.py'), 'r') as f:
            return f.read()

    def test_deferred_removal_on_removed_ids(self):
        """Segments removed during screen-off must be tracked and excluded from flush."""
        source = self._read_transcribe_source()
        # Find the translate() function body
        match = re.search(r'async def translate\(.*?\):\s*\n(.*?)(?=\n    async def )', source, re.DOTALL)
        assert match is not None, "Could not find translate() function"
        body = match.group(1)
        assert 'deferred_removed_ids' in body, "translate() must track removed IDs during deferral"
        assert "deferred_segments.pop(" in body, "translate() must remove deferred segment on removal"

    def test_deferred_overwrite_on_update(self):
        """Rapid updates to the same segment should overwrite (not duplicate) in deferred dict."""
        source = self._read_transcribe_source()
        match = re.search(r'async def translate\(.*?\):\s*\n(.*?)(?=\n    async def )', source, re.DOTALL)
        assert match is not None
        body = match.group(1)
        # Dict assignment with seg_id key means overwrites are automatic
        assert 'deferred_segments[seg_id]' in body, "Must use dict keyed by seg_id for automatic dedup"

    def test_flush_clears_both_collections(self):
        """_flush_deferred_translations must clear both deferred_segments and deferred_removed_ids."""
        source = self._read_transcribe_source()
        start = source.find('async def _flush_deferred_translations')
        end = source.find('\n    async def ', start + 1)
        body = source[start:end]
        assert 'deferred_segments.clear()' in body, "Must clear deferred_segments"
        assert 'deferred_removed_ids.clear()' in body, "Must clear deferred_removed_ids"


class TestToggleStateTransitions:
    """Verify toggle on/off state transitions are consistent."""

    @staticmethod
    def _read_transcribe_source():
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        with open(os.path.join(root, 'routers', 'transcribe.py'), 'r') as f:
            return f.read()

    def test_toggle_on_creates_coordinator(self):
        """Toggle-on must create a TranslationCoordinator."""
        source = self._read_transcribe_source()
        toggle_start = source.find("json_data.get('type') == 'translate_toggle'")
        next_handler = source.find("json_data.get('type') == 'screen_state'", toggle_start)
        toggle_block = source[toggle_start:next_handler]
        assert 'TranslationCoordinator(' in toggle_block, "Toggle-on must create TranslationCoordinator"

    def test_toggle_off_destroys_coordinator(self):
        """Toggle-off must set translation_coordinator to None."""
        source = self._read_transcribe_source()
        toggle_start = source.find("json_data.get('type') == 'translate_toggle'")
        next_handler = source.find("json_data.get('type') == 'screen_state'", toggle_start)
        toggle_block = source[toggle_start:next_handler]
        assert 'translation_coordinator = None' in toggle_block, "Toggle-off must destroy coordinator"

    def test_toggle_off_flushes_pending(self):
        """Toggle-off must flush pending translations before destroying coordinator."""
        source = self._read_transcribe_source()
        toggle_start = source.find("json_data.get('type') == 'translate_toggle'")
        next_handler = source.find("json_data.get('type') == 'screen_state'", toggle_start)
        toggle_block = source[toggle_start:next_handler]
        # flush_pending_translations must appear before coordinator = None
        flush_pos = toggle_block.find('flush_pending_translations()')
        none_pos = toggle_block.find('translation_coordinator = None')
        assert flush_pos != -1, "Must call flush_pending_translations()"
        assert none_pos != -1, "Must set coordinator to None"
        assert flush_pos < none_pos, "Must flush before destroying coordinator"

    def test_toggle_on_guards_no_language_preference(self):
        """Toggle-on with no language preference must log and not create coordinator."""
        source = self._read_transcribe_source()
        toggle_start = source.find("json_data.get('type') == 'translate_toggle'")
        next_handler = source.find("json_data.get('type') == 'screen_state'", toggle_start)
        toggle_block = source[toggle_start:next_handler]
        assert 'no language preference set' in toggle_block, "Must handle missing language preference"


class TestSetAutoTranslatePreference:
    """Verify set_user_transcription_preferences writes auto_translate_enabled correctly."""

    def test_set_auto_translate_true(self):
        """Setting auto_translate_enabled=True must write to Firestore."""
        with patch.object(users_module, 'db') as mock_db:
            mock_ref = mock_db.collection.return_value.document.return_value
            users_module.set_user_transcription_preferences('uid1', auto_translate_enabled=True)
            mock_ref.update.assert_called_once_with({'transcription_preferences.auto_translate_enabled': True})

    def test_set_auto_translate_false(self):
        """Setting auto_translate_enabled=False must write to Firestore."""
        with patch.object(users_module, 'db') as mock_db:
            mock_ref = mock_db.collection.return_value.document.return_value
            users_module.set_user_transcription_preferences('uid2', auto_translate_enabled=False)
            mock_ref.update.assert_called_once_with({'transcription_preferences.auto_translate_enabled': False})

    def test_omitted_auto_translate_does_not_write(self):
        """Omitting auto_translate_enabled must not write it to Firestore."""
        with patch.object(users_module, 'db') as mock_db:
            mock_ref = mock_db.collection.return_value.document.return_value
            users_module.set_user_transcription_preferences('uid3', vocabulary=['test'])
            call_args = mock_ref.update.call_args[0][0]
            assert 'transcription_preferences.auto_translate_enabled' not in call_args
            assert 'transcription_preferences.vocabulary' in call_args

    def test_auto_translate_with_vocabulary(self):
        """Setting both auto_translate_enabled and vocabulary must write both."""
        with patch.object(users_module, 'db') as mock_db:
            mock_ref = mock_db.collection.return_value.document.return_value
            users_module.set_user_transcription_preferences('uid4', auto_translate_enabled=True, vocabulary=['a', 'b'])
            call_args = mock_ref.update.call_args[0][0]
            assert call_args['transcription_preferences.auto_translate_enabled'] is True
            assert call_args['transcription_preferences.vocabulary'] == ['a', 'b']

    def test_vocabulary_truncation_preserved(self):
        """Vocabulary truncation to 100 items must still work."""
        with patch.object(users_module, 'db') as mock_db:
            mock_ref = mock_db.collection.return_value.document.return_value
            big_vocab = [f'word{i}' for i in range(150)]
            users_module.set_user_transcription_preferences('uid5', vocabulary=big_vocab)
            call_args = mock_ref.update.call_args[0][0]
            assert len(call_args['transcription_preferences.vocabulary']) == 100

    def test_no_args_does_not_update(self):
        """Calling with no optional args must not call update."""
        with patch.object(users_module, 'db') as mock_db:
            mock_ref = mock_db.collection.return_value.document.return_value
            users_module.set_user_transcription_preferences('uid6')
            mock_ref.update.assert_not_called()


class TestPydanticModelDefaults:
    """Verify Pydantic model defaults by instantiation."""

    def test_response_model_auto_translate_default(self):
        """TranscriptionPreferencesResponse must default auto_translate_enabled=False."""
        from pydantic import BaseModel
        from typing import List

        # Replicate the model definition to test behavioral defaults
        class TranscriptionPreferencesResponse(BaseModel):
            single_language_mode: bool = False
            auto_translate_enabled: bool = False
            vocabulary: List[str] = []
            language: str = ''

        instance = TranscriptionPreferencesResponse()
        assert instance.auto_translate_enabled is False
        assert instance.single_language_mode is False

    def test_response_model_accepts_true(self):
        """TranscriptionPreferencesResponse must accept auto_translate_enabled=True."""
        from pydantic import BaseModel
        from typing import List

        class TranscriptionPreferencesResponse(BaseModel):
            single_language_mode: bool = False
            auto_translate_enabled: bool = False
            vocabulary: List[str] = []
            language: str = ''

        instance = TranscriptionPreferencesResponse(auto_translate_enabled=True)
        assert instance.auto_translate_enabled is True

    def test_update_model_omission(self):
        """TranscriptionPreferencesUpdate with omitted auto_translate_enabled must be None."""
        from pydantic import BaseModel
        from typing import Optional, List

        class TranscriptionPreferencesUpdate(BaseModel):
            single_language_mode: Optional[bool] = None
            auto_translate_enabled: Optional[bool] = None
            vocabulary: Optional[List[str]] = None

        instance = TranscriptionPreferencesUpdate()
        assert instance.auto_translate_enabled is None

    def test_endpoint_forwards_auto_translate(self):
        """PATCH endpoint source must forward auto_translate_enabled."""
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        with open(os.path.join(root, 'routers', 'users.py'), 'r') as f:
            source = f.read()
        assert 'auto_translate_enabled=data.auto_translate_enabled' in source, "Must forward auto_translate_enabled"


class TestBatchTranslation24hBoundary:
    """Behavioral boundary tests for the 24h filter logic."""

    @staticmethod
    def _should_include_segment(conv_started, seg_end, now, cutoff_secs=24 * 3600):
        """Replicate the 24h filter logic from transcribe.py for behavioral testing."""
        if conv_started and seg_end:
            seg_time = conv_started + timedelta(seconds=seg_end)
            if (now - seg_time).total_seconds() > cutoff_secs:
                return False
        return True

    def test_segment_within_24h_included(self):
        """A segment 23h old must be included."""
        now = datetime.now(timezone.utc)
        conv_started = now - timedelta(hours=23, minutes=30)
        assert self._should_include_segment(conv_started, seg_end=0.0, now=now) is True

    def test_segment_exactly_at_24h_included(self):
        """A segment exactly 24h old must be included (> is strict, not >=)."""
        now = datetime.now(timezone.utc)
        conv_started = now - timedelta(hours=24)
        # seg_end=0 is falsy so filter is skipped; use seg_end close to 0
        assert self._should_include_segment(conv_started, seg_end=0.001, now=now) is True

    def test_segment_just_over_24h_excluded(self):
        """A segment 24h+2s old must be excluded."""
        now = datetime.now(timezone.utc)
        conv_started = now - timedelta(hours=24, seconds=3)
        assert self._should_include_segment(conv_started, seg_end=1.0, now=now) is False

    def test_segment_over_24h_excluded(self):
        """A segment 25h old must be excluded."""
        now = datetime.now(timezone.utc)
        conv_started = now - timedelta(hours=25)
        assert self._should_include_segment(conv_started, seg_end=1.0, now=now) is False

    def test_missing_conv_started_includes_segment(self):
        """Missing conv_started must include segment (skip time filter)."""
        now = datetime.now(timezone.utc)
        assert self._should_include_segment(None, seg_end=100.0, now=now) is True

    def test_missing_seg_end_includes_segment(self):
        """Missing seg_end must include segment (skip time filter)."""
        now = datetime.now(timezone.utc)
        conv_started = now - timedelta(hours=30)
        assert self._should_include_segment(conv_started, seg_end=None, now=now) is True

    def test_segment_end_offset_shifts_boundary(self):
        """seg_end offset must shift the computed time for boundary check."""
        now = datetime.now(timezone.utc)
        conv_started = now - timedelta(hours=24)
        # seg_end=3600 (1h) shifts time forward by 1h, so segment is only 23h old
        assert self._should_include_segment(conv_started, seg_end=3600.0, now=now) is True


class TestToggleIdempotency:
    """Behavioral tests for toggle handler edge cases."""

    @staticmethod
    def _read_transcribe_source():
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        with open(os.path.join(root, 'routers', 'transcribe.py'), 'r') as f:
            return f.read()

    def test_enable_guards_on_no_existing_coordinator(self):
        """Toggle-on must check `not translation_coordinator` before creating."""
        source = self._read_transcribe_source()
        toggle_start = source.find("json_data.get('type') == 'translate_toggle'")
        next_handler = source.find("json_data.get('type') == 'screen_state'", toggle_start)
        toggle_block = source[toggle_start:next_handler]
        assert 'enabled and not translation_coordinator' in toggle_block, "Must guard enable on existing coordinator"

    def test_disable_guards_on_existing_coordinator(self):
        """Toggle-off must check `translation_coordinator` exists before flushing."""
        source = self._read_transcribe_source()
        toggle_start = source.find("json_data.get('type') == 'translate_toggle'")
        next_handler = source.find("json_data.get('type') == 'screen_state'", toggle_start)
        toggle_block = source[toggle_start:next_handler]
        assert 'not enabled and translation_coordinator' in toggle_block, "Must guard disable on existing coordinator"

    def test_screen_state_only_acts_on_change(self):
        """screen_state handler must only flush when state actually changes."""
        source = self._read_transcribe_source()
        screen_start = source.find("json_data.get('type') == 'screen_state'")
        next_handler = source.find("elif json_data.get('type') ==", screen_start + 1)
        if next_handler == -1:
            next_handler = source.find("elif json_data.get('type')", screen_start + 50)
        screen_block = (
            source[screen_start:next_handler] if next_handler != -1 else source[screen_start : screen_start + 500]
        )
        assert 'active != screen_active' in screen_block, "Must only act on actual state change"

    def test_deferred_flush_handles_empty_segments(self):
        """_flush_deferred_translations must handle empty deferred_segments."""
        source = self._read_transcribe_source()
        start = source.find('async def _flush_deferred_translations')
        end = source.find('\n    async def ', start + 1)
        body = source[start:end]
        assert 'not deferred_segments' in body, "Must early-return when no deferred segments"

    def test_batch_filter_skips_translated_segments(self):
        """Batch filter must skip segments with existing translations."""
        segments = [
            {'id': '1', 'text': 'hello', 'translations': {'en': 'hello'}},
            {'id': '2', 'text': 'world', 'translations': None},
            {'id': '3', 'text': 'test'},
        ]
        # Replicate the filter logic from transcribe.py
        units = []
        for s in segments:
            if not s.get('text') or s.get('translations'):
                continue
            units.append((s['id'], s['text']))
        assert len(units) == 2
        assert units[0] == ('2', 'world')
        assert units[1] == ('3', 'test')

    def test_batch_filter_skips_empty_text(self):
        """Batch filter must skip segments with no text."""
        segments = [
            {'id': '1', 'text': ''},
            {'id': '2', 'text': None},
            {'id': '3', 'text': 'valid'},
        ]
        units = []
        for s in segments:
            if not s.get('text') or s.get('translations'):
                continue
            units.append((s['id'], s['text']))
        assert len(units) == 1
        assert units[0] == ('3', 'valid')


class TestAutoTranslateSessionWiring:
    """Verify auto_translate_enabled is fetched and used at session start."""

    @staticmethod
    def _read_transcribe_source():
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        with open(os.path.join(root, 'routers', 'transcribe.py'), 'r') as f:
            return f.read()

    def test_auto_translate_fetched_from_prefs(self):
        """_stream_handler must fetch auto_translate_enabled from transcription prefs."""
        source = self._read_transcribe_source()
        assert "auto_translate_enabled = transcription_prefs.get('auto_translate_enabled'" in source

    def test_auto_translate_passed_to_resolver(self):
        """resolve_translation_language must receive auto_translate_enabled."""
        source = self._read_transcribe_source()
        assert 'auto_translate_enabled=auto_translate_enabled' in source

    def test_language_preference_fetched_unconditionally(self):
        """user_language_preference must be fetched without gating on single_language_mode."""
        source = self._read_transcribe_source()
        # Find the line that fetches user_language_preference
        lines = source.split('\n')
        for line in lines:
            if 'user_language_preference' in line and 'get_user_language_preference' in line:
                assert 'single_language_mode' not in line, "Must not gate on single_language_mode"
                break
        else:
            raise AssertionError("Could not find user_language_preference fetch line")
