"""Unit tests for speaker segment rehydration on WS reconnect.

Tests the fix for #5949: current_session_segments must be rehydrated from
persisted conversation transcript_segments when resuming a conversation
after WebSocket reconnection, so that can_assign works correctly for
speaker sample extraction.
"""

import pytest


class TestCurrentSessionSegmentsRehydration:
    """Tests for rehydrating current_session_segments from conversation data."""

    @staticmethod
    def _rehydrate(existing_segments):
        """Simulate the rehydration logic from _prepare_in_progess_conversations."""
        current_session_segments = {}
        for seg in existing_segments:
            sid = seg.get('id') if isinstance(seg, dict) else getattr(seg, 'id', None)
            if sid:
                spp = (
                    seg.get('speech_profile_processed', True)
                    if isinstance(seg, dict)
                    else getattr(seg, 'speech_profile_processed', True)
                )
                current_session_segments[sid] = spp
        return current_session_segments

    def test_rehydrate_from_dict_segments(self):
        """Segments stored as dicts should populate current_session_segments."""
        segments = [
            {'id': 'seg-1', 'text': 'hello', 'speech_profile_processed': True},
            {'id': 'seg-2', 'text': 'world', 'speech_profile_processed': False},
            {'id': 'seg-3', 'text': 'test', 'speech_profile_processed': True},
        ]
        result = self._rehydrate(segments)
        assert result == {'seg-1': True, 'seg-2': False, 'seg-3': True}

    def test_rehydrate_empty_segments(self):
        """Empty segments list should produce empty dict."""
        result = self._rehydrate([])
        assert result == {}

    def test_rehydrate_missing_speech_profile_processed(self):
        """Segments without speech_profile_processed should default to True."""
        segments = [
            {'id': 'seg-1', 'text': 'hello'},
            {'id': 'seg-2', 'text': 'world', 'speech_profile_processed': False},
        ]
        result = self._rehydrate(segments)
        assert result == {'seg-1': True, 'seg-2': False}

    def test_rehydrate_missing_id(self):
        """Segments without id should be skipped."""
        segments = [
            {'text': 'no id here'},
            {'id': 'seg-1', 'text': 'has id', 'speech_profile_processed': True},
        ]
        result = self._rehydrate(segments)
        assert result == {'seg-1': True}

    def test_can_assign_after_rehydration(self):
        """After rehydration, can_assign should be True for known processed segments."""
        segments = [
            {'id': 'seg-1', 'text': 'hello', 'speech_profile_processed': True},
            {'id': 'seg-2', 'text': 'world', 'speech_profile_processed': False},
        ]
        current_session_segments = self._rehydrate(segments)

        # Simulate the can_assign check from transcribe.py:2509-2514
        def can_assign_check(segment_ids):
            for sid in segment_ids:
                if sid in current_session_segments and current_session_segments[sid]:
                    return True
            return False

        # seg-1 is processed -> can_assign
        assert can_assign_check(['seg-1']) is True
        # seg-2 is not processed -> cannot assign
        assert can_assign_check(['seg-2']) is False
        # mixed: seg-1 processed -> can_assign
        assert can_assign_check(['seg-2', 'seg-1']) is True
        # unknown segment -> cannot assign
        assert can_assign_check(['seg-unknown']) is False

    def test_no_cross_conversation_leakage(self):
        """New conversation should have empty current_session_segments."""
        old_segments = [
            {'id': 'old-1', 'text': 'old', 'speech_profile_processed': True},
        ]
        old_result = self._rehydrate(old_segments)
        assert old_result == {'old-1': True}

        # Simulating new conversation (empty segments)
        new_result = self._rehydrate([])
        assert new_result == {}
        # Old result should not affect new result
        assert 'old-1' not in new_result

    def test_rehydrate_large_segment_list(self):
        """Rehydration should handle large segment lists efficiently."""
        segments = [
            {'id': f'seg-{i}', 'text': f'text {i}', 'speech_profile_processed': i % 2 == 0} for i in range(1000)
        ]
        result = self._rehydrate(segments)
        assert len(result) == 1000
        assert result['seg-0'] is True
        assert result['seg-1'] is False
        assert result['seg-999'] is False
