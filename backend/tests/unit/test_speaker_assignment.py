"""Unit tests for speaker assignment utilities.

Tests the extracted helper functions in utils/speaker_assignment.py.
"""

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone
import uuid

from utils.speaker_assignment import (
    process_speaker_assigned_segments,
    update_speaker_assignment_maps,
    should_update_speaker_to_person_map,
)
from models.transcript_segment import TranscriptSegment


class TestProcessSpeakerAssignedSegments:
    """Tests for process_speaker_assigned_segments helper."""

    def _make_segment(self, id: str, speaker_id: int = 0, is_user: bool = False, person_id: str = None):
        """Create a TranscriptSegment for testing.

        Note: TranscriptSegment extracts speaker_id from speaker string in __init__,
        so we format the speaker string to match the desired speaker_id.
        """
        speaker = f"SPEAKER_{speaker_id:02d}"
        return TranscriptSegment(
            id=id,
            text="test text",
            speaker=speaker,
            is_user=is_user,
            person_id=person_id,
            start=0.0,
            end=1.0,
        )

    def test_assigns_person_from_segment_map(self):
        """Should assign person_id from segment_person_assignment_map."""
        segment = self._make_segment(id="seg1", speaker_id=1)
        segment_person_assignment_map = {"seg1": "person-123"}
        speaker_to_person_map = {}

        process_speaker_assigned_segments(
            [segment],
            segment_person_assignment_map,
            speaker_to_person_map,
        )

        assert segment.person_id == "person-123"
        assert segment.is_user is False

    def test_fallback_to_speaker_to_person_map(self):
        """Should fall back to speaker_to_person_map when segment not in segment map."""
        segment = self._make_segment(id="seg2", speaker_id=1)
        segment_person_assignment_map = {}
        speaker_to_person_map = {1: ("person-456", "Alice")}

        process_speaker_assigned_segments(
            [segment],
            segment_person_assignment_map,
            speaker_to_person_map,
        )

        assert segment.person_id == "person-456"

    def test_handles_user_person_id(self):
        """Should set is_user=True and clear person_id when person_id is 'user'."""
        segment = self._make_segment(id="seg3", speaker_id=1)
        segment_person_assignment_map = {"seg3": "user"}
        speaker_to_person_map = {}

        process_speaker_assigned_segments(
            [segment],
            segment_person_assignment_map,
            speaker_to_person_map,
        )

        assert segment.is_user is True
        assert segment.person_id is None

    def test_skips_already_assigned_segments(self):
        """Should skip segments that already have is_user or person_id set."""
        segment = self._make_segment(id="seg4", speaker_id=1, person_id="existing-person")
        segment_person_assignment_map = {"seg4": "new-person"}
        speaker_to_person_map = {}

        process_speaker_assigned_segments(
            [segment],
            segment_person_assignment_map,
            speaker_to_person_map,
        )

        # Should not be modified
        assert segment.person_id == "existing-person"

    def test_skips_is_user_segments(self):
        """Should skip segments that have is_user=True."""
        segment = self._make_segment(id="seg5", speaker_id=1, is_user=True)
        segment_person_assignment_map = {"seg5": "person-789"}
        speaker_to_person_map = {}

        process_speaker_assigned_segments(
            [segment],
            segment_person_assignment_map,
            speaker_to_person_map,
        )

        # Should not be modified
        assert segment.is_user is True
        assert segment.person_id is None

    def test_processes_multiple_segments(self):
        """Should process multiple segments correctly."""
        seg1 = self._make_segment(id="seg1", speaker_id=1)
        seg2 = self._make_segment(id="seg2", speaker_id=2)
        seg3 = self._make_segment(id="seg3", speaker_id=1)  # Same speaker as seg1

        segment_person_assignment_map = {"seg1": "person-A"}
        speaker_to_person_map = {2: ("person-B", "Bob")}

        process_speaker_assigned_segments(
            [seg1, seg2, seg3],
            segment_person_assignment_map,
            speaker_to_person_map,
        )

        assert seg1.person_id == "person-A"  # From segment map
        assert seg2.person_id == "person-B"  # From speaker map
        assert seg3.person_id is None  # No mapping found


class TestUpdateSpeakerAssignmentMaps:
    """Tests for update_speaker_assignment_maps helper."""

    def test_updates_both_maps(self):
        """Should update both maps when all fields are provided."""
        speaker_to_person_map = {}
        segment_person_assignment_map = {}

        result = update_speaker_assignment_maps(
            speaker_id=1,
            person_id="person-event",
            person_name="EventPerson",
            segment_ids=["seg-e1", "seg-e2"],
            speaker_to_person_map=speaker_to_person_map,
            segment_person_assignment_map=segment_person_assignment_map,
        )

        assert result is True
        assert speaker_to_person_map[1] == ("person-event", "EventPerson")
        assert segment_person_assignment_map["seg-e1"] == "person-event"
        assert segment_person_assignment_map["seg-e2"] == "person-event"

    def test_returns_false_when_speaker_id_missing(self):
        """Should return False and not update maps when speaker_id is None."""
        speaker_to_person_map = {}
        segment_person_assignment_map = {}

        result = update_speaker_assignment_maps(
            speaker_id=None,
            person_id="person-x",
            person_name="X",
            segment_ids=["seg-x"],
            speaker_to_person_map=speaker_to_person_map,
            segment_person_assignment_map=segment_person_assignment_map,
        )

        assert result is False
        assert len(speaker_to_person_map) == 0
        assert len(segment_person_assignment_map) == 0

    def test_returns_false_when_person_id_missing(self):
        """Should return False and not update maps when person_id is None."""
        speaker_to_person_map = {}
        segment_person_assignment_map = {}

        result = update_speaker_assignment_maps(
            speaker_id=1,
            person_id=None,
            person_name="Name",
            segment_ids=["seg-y"],
            speaker_to_person_map=speaker_to_person_map,
            segment_person_assignment_map=segment_person_assignment_map,
        )

        assert result is False
        assert len(speaker_to_person_map) == 0

    def test_returns_false_when_person_name_missing(self):
        """Should return False and not update maps when person_name is None."""
        speaker_to_person_map = {}
        segment_person_assignment_map = {}

        result = update_speaker_assignment_maps(
            speaker_id=1,
            person_id="person-z",
            person_name=None,
            segment_ids=["seg-z"],
            speaker_to_person_map=speaker_to_person_map,
            segment_person_assignment_map=segment_person_assignment_map,
        )

        assert result is False
        assert len(speaker_to_person_map) == 0


class TestShouldUpdateSpeakerToPersonMap:
    """Tests for should_update_speaker_to_person_map helper."""

    def test_returns_true_for_positive_speaker_id(self):
        """Should return True for speaker_id > 0 (diarization active)."""
        assert should_update_speaker_to_person_map(1) is True
        assert should_update_speaker_to_person_map(2) is True
        assert should_update_speaker_to_person_map(100) is True

    def test_returns_false_for_zero_speaker_id(self):
        """Should return False for speaker_id == 0 (diarization off)."""
        assert should_update_speaker_to_person_map(0) is False

    def test_returns_false_for_negative_speaker_id(self):
        """Should return False for speaker_id < 0."""
        assert should_update_speaker_to_person_map(-1) is False

    def test_returns_false_for_none_speaker_id(self):
        """Should return False for speaker_id is None."""
        assert should_update_speaker_to_person_map(None) is False
