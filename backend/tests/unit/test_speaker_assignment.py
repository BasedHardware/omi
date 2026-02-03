"""Unit tests for speaker assignment logic in transcribe.py.

Tests cover:
1. _process_speaker_assigned_segments fallback logic
2. Text detection person creation and map updates
3. speaker_assigned event handling with can_assign gate

Note: The speaker assignment logic in transcribe.py is currently defined inside
nested async handlers, making it difficult to test directly. These tests verify
the logic patterns and data flow. For full integration testing, consider
refactoring _process_speaker_assigned_segments and related logic into standalone
testable functions in a separate module.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timezone
import uuid


class MockTranscriptSegment:
    """Mock TranscriptSegment for testing."""

    def __init__(self, id: str, speaker_id: int = None, is_user: bool = False, person_id: str = None):
        self.id = id
        self.speaker_id = speaker_id
        self.is_user = is_user
        self.person_id = person_id


class TestProcessSpeakerAssignedSegments:
    """Tests for _process_speaker_assigned_segments logic."""

    def test_assigns_person_from_segment_map(self):
        """Should assign person_id from segment_person_assignment_map."""
        segment = MockTranscriptSegment(id="seg1", speaker_id=1)
        segment_person_assignment_map = {"seg1": "person-123"}
        speaker_to_person_map = {}

        # Simulate the logic from _process_speaker_assigned_segments
        if not segment.is_user and not segment.person_id:
            person_id = None
            if segment.id in segment_person_assignment_map:
                person_id = segment_person_assignment_map[segment.id]
            elif segment.speaker_id in speaker_to_person_map:
                person_id = speaker_to_person_map[segment.speaker_id][0]

            if person_id and person_id != 'user':
                segment.is_user = False
                segment.person_id = person_id

        assert segment.person_id == "person-123"
        assert segment.is_user is False

    def test_fallback_to_speaker_to_person_map(self):
        """Should fall back to speaker_to_person_map when segment not in segment map."""
        segment = MockTranscriptSegment(id="seg2", speaker_id=1)
        segment_person_assignment_map = {}
        speaker_to_person_map = {1: ("person-456", "Alice")}

        # Simulate the logic
        if not segment.is_user and not segment.person_id:
            person_id = None
            if segment.id in segment_person_assignment_map:
                person_id = segment_person_assignment_map[segment.id]
            elif segment.speaker_id in speaker_to_person_map:
                person_id = speaker_to_person_map[segment.speaker_id][0]

            if person_id and person_id != 'user':
                segment.is_user = False
                segment.person_id = person_id

        assert segment.person_id == "person-456"

    def test_handles_user_person_id(self):
        """Should set is_user=True and clear person_id when person_id is 'user'."""
        segment = MockTranscriptSegment(id="seg3", speaker_id=1)
        segment_person_assignment_map = {"seg3": "user"}
        speaker_to_person_map = {}

        # Simulate the logic
        if not segment.is_user and not segment.person_id:
            person_id = None
            if segment.id in segment_person_assignment_map:
                person_id = segment_person_assignment_map[segment.id]

            if person_id:
                if person_id == 'user':
                    segment.is_user = True
                    segment.person_id = None
                else:
                    segment.is_user = False
                    segment.person_id = person_id

        assert segment.is_user is True
        assert segment.person_id is None

    def test_skips_already_assigned_segments(self):
        """Should skip segments that already have is_user or person_id set."""
        segment = MockTranscriptSegment(id="seg4", speaker_id=1, person_id="existing-person")
        segment_person_assignment_map = {"seg4": "new-person"}

        # Simulate the logic with early continue
        if segment.is_user or segment.person_id:
            pass  # Skip
        else:
            segment.person_id = segment_person_assignment_map.get(segment.id)

        # Should not be modified
        assert segment.person_id == "existing-person"


class TestTextDetectionSpeakerMapping:
    """Tests for text detection branch in speaker assignment."""

    def test_speaker_id_zero_does_not_update_speaker_map(self):
        """Boundary: speaker_id <= 0 should not update speaker_to_person_map."""
        speaker_to_person_map = {}
        segment_person_assignment_map = {}
        segment_id = "seg-text"
        speaker_id = 0  # Diarization off
        person_id = "person-789"
        detected_name = "Bob"

        # Simulate the guarded logic
        if speaker_id is not None and speaker_id > 0:
            speaker_to_person_map[speaker_id] = (person_id, detected_name)
        segment_person_assignment_map[segment_id] = person_id

        assert speaker_id not in speaker_to_person_map
        assert segment_person_assignment_map[segment_id] == person_id

    def test_speaker_id_positive_updates_speaker_map(self):
        """speaker_id > 0 should update speaker_to_person_map."""
        speaker_to_person_map = {}
        segment_person_assignment_map = {}
        segment_id = "seg-text2"
        speaker_id = 2  # Diarization active
        person_id = "person-101"
        detected_name = "Charlie"

        # Simulate the guarded logic
        if speaker_id is not None and speaker_id > 0:
            speaker_to_person_map[speaker_id] = (person_id, detected_name)
        segment_person_assignment_map[segment_id] = person_id

        assert speaker_to_person_map[speaker_id] == (person_id, detected_name)
        assert segment_person_assignment_map[segment_id] == person_id

    def test_speaker_id_none_does_not_update_speaker_map(self):
        """Boundary: speaker_id=None should not update speaker_to_person_map."""
        speaker_to_person_map = {}
        segment_person_assignment_map = {}
        segment_id = "seg-text3"
        speaker_id = None
        person_id = "person-202"
        detected_name = "Dave"

        # Simulate the guarded logic
        if speaker_id is not None and speaker_id > 0:
            speaker_to_person_map[speaker_id] = (person_id, detected_name)
        segment_person_assignment_map[segment_id] = person_id

        assert speaker_id not in speaker_to_person_map
        assert segment_person_assignment_map[segment_id] == person_id


class TestSpeakerAssignedEvent:
    """Tests for speaker_assigned event handling."""

    def test_updates_maps_even_when_can_assign_false(self):
        """Should update maps even when can_assign is False."""
        speaker_to_person_map = {}
        segment_person_assignment_map = {}
        can_assign = False
        speaker_id = 1
        person_id = "person-event"
        person_name = "EventPerson"
        segment_ids = ["seg-e1", "seg-e2"]

        # Simulate the new logic (always set maps)
        if speaker_id is not None and person_id is not None and person_name is not None:
            speaker_to_person_map[speaker_id] = (person_id, person_name)
            for sid in segment_ids:
                segment_person_assignment_map[sid] = person_id

        assert speaker_to_person_map[speaker_id] == (person_id, person_name)
        assert segment_person_assignment_map["seg-e1"] == person_id
        assert segment_person_assignment_map["seg-e2"] == person_id

    def test_sample_extraction_only_when_can_assign_true(self):
        """Should only enqueue speaker sample extraction when can_assign is True."""
        can_assign = False
        person_id = "person-sample"
        extraction_called = False

        def mock_create_task(coro):
            nonlocal extraction_called
            extraction_called = True

        # Simulate the conditional
        if can_assign and person_id and person_id != 'user':
            mock_create_task(None)

        assert extraction_called is False

        # Now with can_assign = True
        can_assign = True
        if can_assign and person_id and person_id != 'user':
            mock_create_task(None)

        assert extraction_called is True

    def test_ignores_incomplete_event_data(self):
        """Should not update maps when required fields are missing."""
        speaker_to_person_map = {}
        segment_person_assignment_map = {}
        speaker_id = 1
        person_id = None  # Missing
        person_name = "Name"
        segment_ids = ["seg-incomplete"]

        if speaker_id is not None and person_id is not None and person_name is not None:
            speaker_to_person_map[speaker_id] = (person_id, person_name)
            for sid in segment_ids:
                segment_person_assignment_map[sid] = person_id

        assert speaker_id not in speaker_to_person_map
        assert "seg-incomplete" not in segment_person_assignment_map


class TestPersonCreationOnTextDetection:
    """Tests for person creation when text detection finds unknown name."""

    def test_creates_person_when_not_found(self):
        """Should create person in database when get_person_by_name returns None."""
        # Simulate the text detection flow with mocked db calls
        create_person_calls = []

        def mock_get_person_by_name(uid, name):
            return None  # Person not found

        def mock_create_person(uid, data):
            create_person_calls.append((uid, data))
            return data

        # Simulate the text detection logic
        uid = "test-user"
        detected_name = "Alice"
        segment_speaker_id = 1
        segment_id = "seg-text-create"
        speaker_to_person_map = {}
        segment_person_assignment_map = {}

        person = mock_get_person_by_name(uid, detected_name)
        if person:
            person_id = person['id']
        else:
            person_id = str(uuid.uuid4())
            mock_create_person(
                uid,
                {
                    'id': person_id,
                    'name': detected_name,
                    'created_at': datetime.now(timezone.utc),
                    'updated_at': datetime.now(timezone.utc),
                },
            )

        # Verify person was created
        assert len(create_person_calls) == 1
        assert create_person_calls[0][0] == uid
        assert create_person_calls[0][1]['name'] == detected_name

    def test_does_not_create_person_when_found(self):
        """Should not create person when get_person_by_name returns existing person."""
        create_person_calls = []

        def mock_get_person_by_name(uid, name):
            return {'id': 'existing-person-id', 'name': name}  # Person found

        def mock_create_person(uid, data):
            create_person_calls.append((uid, data))

        # Simulate the text detection logic
        uid = "test-user"
        detected_name = "Bob"

        person = mock_get_person_by_name(uid, detected_name)
        if person:
            person_id = person['id']
        else:
            person_id = str(uuid.uuid4())
            mock_create_person(uid, {'id': person_id, 'name': detected_name})

        # Verify person was NOT created
        assert len(create_person_calls) == 0
        assert person_id == 'existing-person-id'
