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


class TestSingleLanguageModeDefaults:
    """Verify single_language_mode defaults to True for new/missing users."""

    def test_missing_user_returns_true(self):
        """A user that doesn't exist in Firestore should get single_language_mode=True."""
        mock_doc = MagicMock()
        mock_doc.exists = False
        with patch.object(users_module, 'db') as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            result = users_module.get_user_transcription_preferences('nonexistent_uid')
        assert result['single_language_mode'] is True

    def test_user_without_prefs_returns_true(self):
        """A user doc that exists but has no transcription_preferences should default to True."""
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {}
        with patch.object(users_module, 'db') as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            result = users_module.get_user_transcription_preferences('uid_no_prefs')
        assert result['single_language_mode'] is True

    def test_user_with_explicit_false_returns_false(self):
        """A user with explicit single_language_mode=False should keep it."""
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {'transcription_preferences': {'single_language_mode': False}}
        with patch.object(users_module, 'db') as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            result = users_module.get_user_transcription_preferences('uid_explicit_false')
        assert result['single_language_mode'] is False

    def test_user_with_explicit_true_returns_true(self):
        """A user with explicit single_language_mode=True should keep it."""
        mock_doc = MagicMock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {'transcription_preferences': {'single_language_mode': True}}
        with patch.object(users_module, 'db') as mock_db:
            mock_db.collection.return_value.document.return_value.get.return_value = mock_doc
            result = users_module.get_user_transcription_preferences('uid_explicit_true')
        assert result['single_language_mode'] is True


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
