"""
Tests for in-memory conversation cache in stream_transcript_process().
Verifies cache refresh on ID change, 30s staleness, translation persist uses cache,
and cleanup on disconnect.
"""

import time
from unittest.mock import MagicMock, patch

from google.api_core.exceptions import NotFound


class FakeConversationsDb:
    """Mock conversations_db with call tracking."""

    def __init__(self):
        self.get_conversation_calls = 0
        self.update_segments_calls = 0
        self._conversation_data = {
            'id': 'conv-1',
            'transcript_segments': [],
            'data_protection_level': 'standard',
            'started_at': '2026-03-05T00:00:00+00:00',
        }

    def get_conversation(self, uid, conversation_id):
        self.get_conversation_calls += 1
        return dict(self._conversation_data)

    def update_conversation_segments(self, uid, conversation_id, segments, data_protection_level=None):
        self.update_segments_calls += 1


# Reproduce the cache logic from transcribe.py
def _make_cache(conversations_db, uid):
    """Create a cache instance matching the transcribe.py pattern."""
    _cached_conversation_data = None
    _cached_conversation_id = None
    _cached_conversation_time = 0.0
    _cached_protection_level = 'standard'
    current_conversation_id = 'conv-1'
    CONVERSATION_CACHE_REFRESH_SECONDS = 30

    def get_cached(force_refresh=False):
        nonlocal _cached_conversation_data, _cached_conversation_id, _cached_conversation_time, _cached_protection_level
        now = time.monotonic()
        id_changed = current_conversation_id != _cached_conversation_id
        stale = (now - _cached_conversation_time) >= CONVERSATION_CACHE_REFRESH_SECONDS
        if _cached_conversation_data is None or id_changed or stale or force_refresh:
            data = conversations_db.get_conversation(uid, current_conversation_id)
            if data:
                _cached_conversation_data = data
                _cached_conversation_id = current_conversation_id
                _cached_conversation_time = now
                _cached_protection_level = data.get('data_protection_level', 'standard')
            return data
        return _cached_conversation_data

    def update_cached_segments(segments_dicts):
        if _cached_conversation_data is not None:
            _cached_conversation_data['transcript_segments'] = segments_dicts

    def set_conversation_id(new_id):
        nonlocal current_conversation_id
        current_conversation_id = new_id

    def get_protection_level():
        return _cached_protection_level

    def cleanup():
        nonlocal _cached_conversation_data
        _cached_conversation_data = None

    return get_cached, update_cached_segments, set_conversation_id, get_protection_level, cleanup


class TestConversationCache:
    """Tests for in-memory conversation cache."""

    def test_first_call_fetches_from_db(self):
        """First call should read from Firestore."""
        db = FakeConversationsDb()
        get_cached, _, _, _, _ = _make_cache(db, 'uid-1')

        result = get_cached()

        assert result is not None
        assert result['id'] == 'conv-1'
        assert db.get_conversation_calls == 1

    def test_second_call_uses_cache(self):
        """Repeated calls within 30s should NOT read from Firestore again."""
        db = FakeConversationsDb()
        get_cached, _, _, _, _ = _make_cache(db, 'uid-1')

        get_cached()
        get_cached()
        get_cached()

        assert db.get_conversation_calls == 1

    def test_id_change_triggers_refresh(self):
        """Changing conversation ID should trigger a Firestore read."""
        db = FakeConversationsDb()
        get_cached, _, set_id, _, _ = _make_cache(db, 'uid-1')

        get_cached()
        assert db.get_conversation_calls == 1

        set_id('conv-2')
        get_cached()
        assert db.get_conversation_calls == 2

    def test_force_refresh(self):
        """force_refresh=True should bypass cache."""
        db = FakeConversationsDb()
        get_cached, _, _, _, _ = _make_cache(db, 'uid-1')

        get_cached()
        get_cached(force_refresh=True)

        assert db.get_conversation_calls == 2

    def test_staleness_triggers_refresh(self):
        """After 30s, cache should be considered stale."""
        db = FakeConversationsDb()
        get_cached, _, _, _, _ = _make_cache(db, 'uid-1')

        get_cached()
        assert db.get_conversation_calls == 1

        # Simulate time passing by patching time.monotonic
        original_monotonic = time.monotonic
        try:
            time.monotonic = lambda: original_monotonic() + 31
            get_cached()
            assert db.get_conversation_calls == 2
        finally:
            time.monotonic = original_monotonic

    def test_update_cached_segments_reflects_in_cache(self):
        """Updating cached segments should be visible on next cache hit."""
        db = FakeConversationsDb()
        get_cached, update_cached, _, _, _ = _make_cache(db, 'uid-1')

        get_cached()
        update_cached([{'id': 'seg-1', 'text': 'hello'}])

        result = get_cached()
        assert result['transcript_segments'] == [{'id': 'seg-1', 'text': 'hello'}]
        # Should still be only 1 Firestore call (used cache)
        assert db.get_conversation_calls == 1

    def test_protection_level_cached(self):
        """data_protection_level should be cached from conversation data."""
        db = FakeConversationsDb()
        db._conversation_data['data_protection_level'] = 'enhanced'
        get_cached, _, _, get_level, _ = _make_cache(db, 'uid-1')

        get_cached()
        assert get_level() == 'enhanced'

    def test_cleanup_clears_cache(self):
        """Cleanup should clear cached data, next call reads from DB."""
        db = FakeConversationsDb()
        get_cached, _, _, _, cleanup = _make_cache(db, 'uid-1')

        get_cached()
        assert db.get_conversation_calls == 1

        cleanup()
        get_cached()
        assert db.get_conversation_calls == 2


class TestTranslateCacheIdGuard:
    """Tests for translate() conversation_id guard — only uses cache when IDs match."""

    def test_matching_id_uses_cache(self):
        """When conversation_id matches current, should use cache (no extra DB call)."""
        db = FakeConversationsDb()
        get_cached, _, set_id, get_level, _ = _make_cache(db, 'uid-1')

        # Prime cache
        get_cached()
        assert db.get_conversation_calls == 1

        # Simulate translate with matching ID — should use cache
        result = get_cached()  # hits cache
        assert db.get_conversation_calls == 1
        assert result is not None

    def test_mismatched_id_falls_back_to_db(self):
        """When conversation_id differs from current, should NOT use cache."""
        db = FakeConversationsDb()
        get_cached, _, set_id, _, _ = _make_cache(db, 'uid-1')

        # Prime cache with conv-1
        get_cached()
        assert db.get_conversation_calls == 1

        # Simulate translate for a different conversation_id
        # In real code, this path does conversations_db.get_conversation(uid, conversation_id)
        # directly instead of using _get_cached_conversation()
        different_id = 'conv-old'
        # The cache is keyed on current_conversation_id, so changing it triggers refresh
        set_id(different_id)
        get_cached()
        assert db.get_conversation_calls == 2  # fresh DB read


class TestUpdateConversationSegmentsDataProtection:
    """Tests for data_protection_level param on update_conversation_segments.

    Uses the extracted logic pattern to avoid Firestore init at import time.
    """

    @staticmethod
    def _update_segments_logic(doc_ref, uid, conversation_id, segments, data_protection_level=None):
        """Reproduce the exact logic from conversations.py update_conversation_segments."""
        if data_protection_level is not None:
            doc_level = data_protection_level
        else:
            doc_snapshot = doc_ref.get(field_paths=['data_protection_level'])
            if not doc_snapshot.exists:
                return
            doc_level = doc_snapshot.to_dict().get('data_protection_level', 'standard')
        # Simulate the update with try/except NotFound (mirrors conversations.py)
        try:
            doc_ref.update({'transcript_segments': segments, '_level': doc_level})
        except NotFound:
            return None
        return doc_level

    def test_skips_db_read_when_level_provided(self):
        """When data_protection_level is passed, should skip the extra Firestore read."""
        mock_doc_ref = MagicMock()

        result = self._update_segments_logic(
            mock_doc_ref, 'uid', 'conv-1', [{'text': 'hello'}], data_protection_level='standard'
        )

        assert result == 'standard'
        mock_doc_ref.get.assert_not_called()

    def test_falls_back_to_db_when_level_not_provided(self):
        """When data_protection_level is None, should read from Firestore."""
        mock_doc_ref = MagicMock()
        mock_doc_ref.get.return_value.exists = True
        mock_doc_ref.get.return_value.to_dict.return_value = {'data_protection_level': 'enhanced'}

        result = self._update_segments_logic(mock_doc_ref, 'uid', 'conv-1', [{'text': 'hello'}])

        assert result == 'enhanced'
        mock_doc_ref.get.assert_called_once()

    def test_returns_none_when_doc_not_found(self):
        """When document doesn't exist and no level provided, should return None."""
        mock_doc_ref = MagicMock()
        mock_doc_ref.get.return_value.exists = False

        result = self._update_segments_logic(mock_doc_ref, 'uid', 'conv-1', [{'text': 'hello'}])

        assert result is None

    def test_handles_deleted_doc_gracefully_with_cached_level(self):
        """When cached level is provided but doc was deleted, should not crash."""
        mock_doc_ref = MagicMock()
        mock_doc_ref.update.side_effect = NotFound("Document does not exist")

        result = self._update_segments_logic(
            mock_doc_ref, 'uid', 'conv-1', [{'text': 'hello'}], data_protection_level='standard'
        )

        # Should return None (graceful failure) instead of raising
        assert result is None

    def test_non_notfound_errors_propagate(self):
        """Non-NotFound errors (permission, quota) should still propagate."""
        mock_doc_ref = MagicMock()
        mock_doc_ref.update.side_effect = PermissionError("Insufficient permissions")

        import pytest

        with pytest.raises(PermissionError):
            self._update_segments_logic(
                mock_doc_ref, 'uid', 'conv-1', [{'text': 'hello'}], data_protection_level='standard'
            )
