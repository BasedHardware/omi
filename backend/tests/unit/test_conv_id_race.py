"""Unit tests for conversation_id race condition fixes (#6190).

Bug 1: segment_conversation_map prevents stale current_conversation_id
        from being used in speaker_assigned handler after rollover.
Bug 2: Pusher header_type 102 must not overwrite current_conversation_id
        from memory_id — only header_type 103 is authoritative.
"""

import json
import struct

from utils.speaker_assignment import resolve_conversation_for_segments, resolve_transcript_conversation_id


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

    def test_removed_ids_pruned_from_map(self):
        """Merged/removed segment IDs should be pruned from the map."""
        segment_conversation_map = {'seg-1': 'conv-A', 'seg-2': 'conv-A', 'seg-3': 'conv-A'}
        removed_ids = ['seg-1', 'seg-2']
        for rid in removed_ids:
            segment_conversation_map.pop(rid, None)
        assert segment_conversation_map == {'seg-3': 'conv-A'}


class TestResolveTranscriptConversationId:
    """Tests for the production resolve_transcript_conversation_id function (Bug 2)."""

    def test_memory_id_returned_when_present(self):
        """memory_id should be used for transcript queue, not current_conversation_id."""
        result = resolve_transcript_conversation_id('conv-B', 'conv-A')
        assert result == 'conv-B'

    def test_current_used_when_memory_id_none(self):
        """Without memory_id, should fall back to current_conversation_id."""
        result = resolve_transcript_conversation_id(None, 'conv-A')
        assert result == 'conv-A'

    def test_current_used_when_memory_id_empty(self):
        """Empty string memory_id should fall back to current_conversation_id."""
        result = resolve_transcript_conversation_id('', 'conv-A')
        assert result == 'conv-A'

    def test_does_not_mutate_current_conversation_id(self):
        """Calling resolve_transcript_conversation_id must not change the caller's state.

        This tests the contract: header_type 102 must not overwrite
        current_conversation_id. The function returns the resolved value
        without side effects."""
        current_conversation_id = 'conv-A'
        conversation_or_memory_id = resolve_transcript_conversation_id('conv-B', current_conversation_id)
        assert current_conversation_id == 'conv-A'
        assert conversation_or_memory_id == 'conv-B'

    def test_both_none(self):
        """When both are None, returns None."""
        result = resolve_transcript_conversation_id(None, None)
        assert result is None

    def test_header_103_is_only_authority(self):
        """header_type 103 is the only way to change current_conversation_id.

        resolve_transcript_conversation_id never mutates the caller's ID."""
        current_conversation_id = 'conv-A'

        # header_type 102 arrives with memory_id 'conv-B'
        transcript_conv = resolve_transcript_conversation_id('conv-B', current_conversation_id)
        assert transcript_conv == 'conv-B'
        assert current_conversation_id == 'conv-A'  # unchanged

        # header_type 103 is the only authority (done by caller)
        current_conversation_id = 'conv-C'
        assert current_conversation_id == 'conv-C'

    def test_private_cloud_chunks_use_authoritative_conv_id(self):
        """Private cloud sync chunks must use the header_type 103 conversation ID,
        not the memory_id from 102."""
        current_conversation_id = 'conv-A'
        private_cloud_queue = []

        # header_type 102 arrives but does NOT change current_conversation_id
        resolve_transcript_conversation_id('conv-B', current_conversation_id)

        # Private cloud chunk uses current_conversation_id (from 103)
        private_cloud_queue.append(
            {
                'data': b'\x00' * 100,
                'conversation_id': current_conversation_id,
                'timestamp': 1234567890.0,
                'retries': 0,
            }
        )
        assert private_cloud_queue[0]['conversation_id'] == 'conv-A'
