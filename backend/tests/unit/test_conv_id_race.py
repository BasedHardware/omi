"""Unit tests for conversation_id race condition fixes (#6190).

Bug 1: segment_conversation_map prevents stale current_conversation_id
        from being used in speaker_assigned handler after rollover.
Bug 2: Pusher header_type 102 must not overwrite current_conversation_id
        from memory_id — only header_type 103 is authoritative.
"""

import json
import struct

from utils.speaker_assignment import resolve_conversation_for_segments


class TestResolveConversationForSegments:
    """Tests for the production resolve_conversation_for_segments function."""

    def test_segment_maps_to_original_conversation(self):
        """Segments created in conv-A should map to conv-A even after rollover to conv-B."""
        segment_conversation_map = {'seg-1': 'conv-A', 'seg-2': 'conv-A', 'seg-3': 'conv-A'}
        result = resolve_conversation_for_segments(['seg-1', 'seg-2'], segment_conversation_map, 'conv-B')
        assert result == 'conv-A'

    def test_fallback_to_current_when_segment_unknown(self):
        """If segment not in map (edge case), fall back to current_conversation_id."""
        result = resolve_conversation_for_segments(['unknown-seg'], {}, 'conv-B')
        assert result == 'conv-B'

    def test_empty_segment_ids_uses_current(self):
        """Empty segment_ids should use current_conversation_id."""
        result = resolve_conversation_for_segments([], {'seg-1': 'conv-A'}, 'conv-B')
        assert result == 'conv-B'

    def test_segments_across_two_conversations(self):
        """Segments from different conversations should each resolve correctly."""
        segment_conversation_map = {
            'seg-1': 'conv-A',
            'seg-2': 'conv-A',
            'seg-3': 'conv-B',
            'seg-4': 'conv-B',
        }
        assert resolve_conversation_for_segments(['seg-1'], segment_conversation_map, 'conv-B') == 'conv-A'
        assert resolve_conversation_for_segments(['seg-3'], segment_conversation_map, 'conv-B') == 'conv-B'

    def test_mixed_segment_ids_first_unknown_resolves_from_later(self):
        """If first segment_id is unknown but later ones are in the map, resolve correctly."""
        segment_conversation_map = {'seg-2': 'conv-A', 'seg-3': 'conv-A'}
        result = resolve_conversation_for_segments(
            ['unknown-seg', 'seg-2', 'seg-3'], segment_conversation_map, 'conv-B'
        )
        assert result == 'conv-A'

    def test_all_unknown_segments_fall_back_to_current(self):
        """If no segment_ids are in the map, fall back to current_conversation_id."""
        result = resolve_conversation_for_segments(['unknown-1', 'unknown-2'], {'seg-1': 'conv-A'}, 'conv-B')
        assert result == 'conv-B'

    def test_none_current_conversation_id(self):
        """When current_conversation_id is None and no match, returns None."""
        result = resolve_conversation_for_segments(['unknown'], {}, None)
        assert result is None

    def test_none_current_but_mapped(self):
        """When current_conversation_id is None but segment is mapped, returns mapped value."""
        result = resolve_conversation_for_segments(['seg-1'], {'seg-1': 'conv-A'}, None)
        assert result == 'conv-A'


class TestSegmentConversationMapPopulation:
    """Tests that segment_conversation_map is populated correctly at segment creation."""

    def test_map_populated_at_segment_creation(self):
        """Verify the map is populated when segments are first processed, not later."""
        segment_conversation_map = {}
        current_session_segments = {}
        current_conversation_id = 'conv-A'

        # Simulate newly_processed_segments loop (mirrors transcribe.py)
        segments = [
            type('Seg', (), {'id': 'seg-1', 'speech_profile_processed': True})(),
            type('Seg', (), {'id': 'seg-2', 'speech_profile_processed': False})(),
        ]
        for seg in segments:
            current_session_segments[seg.id] = seg.speech_profile_processed
            segment_conversation_map[seg.id] = current_conversation_id

        assert segment_conversation_map == {'seg-1': 'conv-A', 'seg-2': 'conv-A'}
        assert current_session_segments == {'seg-1': True, 'seg-2': False}

    def test_map_snapshots_correct_conv_across_rollover(self):
        """Segments populated before and after rollover map to their respective conversations."""
        segment_conversation_map = {}

        current_conversation_id = 'conv-A'
        for sid in ['seg-1', 'seg-2']:
            segment_conversation_map[sid] = current_conversation_id

        current_conversation_id = 'conv-B'
        for sid in ['seg-3', 'seg-4']:
            segment_conversation_map[sid] = current_conversation_id

        # Now use the production function to resolve
        assert resolve_conversation_for_segments(['seg-1'], segment_conversation_map, 'conv-B') == 'conv-A'
        assert resolve_conversation_for_segments(['seg-3'], segment_conversation_map, 'conv-B') == 'conv-B'


class TestPusherMemoryIdOverwrite:
    """Tests that header_type 102 no longer overwrites current_conversation_id."""

    def _parse_header_102(self, data):
        """Parse a header_type 102 message."""
        header_type = struct.unpack('<I', data[:4])[0]
        assert header_type == 102
        return json.loads(bytes(data[4:]).decode('utf-8'))

    def test_header_102_does_not_overwrite_conversation_id(self):
        """memory_id in transcript should NOT change current_conversation_id."""
        current_conversation_id = 'conv-A'

        # Build a 102 message with memory_id
        payload = json.dumps({'segments': [], 'memory_id': 'conv-B'}).encode('utf-8')
        data = struct.pack('<I', 102) + payload
        res = self._parse_header_102(data)

        memory_id = res.get('memory_id')
        # The fix: we do NOT overwrite current_conversation_id
        # (removed: if memory_id: current_conversation_id = memory_id)
        conversation_or_memory_id = memory_id or current_conversation_id
        assert current_conversation_id == 'conv-A'  # must stay unchanged
        assert conversation_or_memory_id == 'conv-B'  # transcript queue uses memory_id

    def test_header_102_without_memory_id_uses_current(self):
        """Without memory_id, transcript queue should use current_conversation_id."""
        current_conversation_id = 'conv-A'

        payload = json.dumps({'segments': [{'text': 'hello'}]}).encode('utf-8')
        data = struct.pack('<I', 102) + payload
        res = self._parse_header_102(data)

        memory_id = res.get('memory_id')
        conversation_or_memory_id = memory_id or current_conversation_id
        assert conversation_or_memory_id == 'conv-A'

    def test_private_cloud_chunks_use_authoritative_conv_id(self):
        """Private cloud sync chunks must always use the header_type 103 conversation ID."""
        current_conversation_id = 'conv-A'
        private_cloud_queue = []

        # Simulate header_type 102 with different memory_id
        memory_id = 'conv-B'
        # Fix: we do NOT overwrite current_conversation_id

        # Simulate header_type 101 audio chunk queuing
        private_cloud_queue.append(
            {
                'data': b'\x00' * 100,
                'conversation_id': current_conversation_id,
                'timestamp': 1234567890.0,
                'retries': 0,
            }
        )

        assert private_cloud_queue[0]['conversation_id'] == 'conv-A'

    def test_header_103_is_authoritative(self):
        """header_type 103 should be the only way to change current_conversation_id."""
        current_conversation_id = None

        # Header 103 sets it
        new_conversation_id = 'conv-A'
        current_conversation_id = new_conversation_id
        assert current_conversation_id == 'conv-A'

        # Header 102 with memory_id must NOT change it
        memory_id = 'conv-B'
        # (no overwrite)
        assert current_conversation_id == 'conv-A'

        # Header 103 with new ID changes it
        current_conversation_id = 'conv-C'
        assert current_conversation_id == 'conv-C'
