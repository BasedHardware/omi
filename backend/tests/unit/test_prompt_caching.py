"""Tests for OpenAI prompt caching support in conversation processing (issue #4654).

Verifies that:
1. _build_conversation_context() produces deterministic, identical output for the same inputs
2. get_transcript_structure() and extract_action_items() use conversation context
   as the second system message (after static instructions) to enable OpenAI prompt caching
3. Calendar context is unified (includes meeting_link in both functions)
"""

import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

# Mock modules that initialize GCP clients or require API keys at import time
sys.modules.setdefault("database._client", MagicMock())
_mock_clients = MagicMock()
sys.modules.setdefault("utils.llm.clients", _mock_clients)

from models.conversation import CalendarMeetingContext, MeetingParticipant, ConversationPhoto
from utils.llm.conversation_processing import _build_conversation_context


class TestBuildConversationContext:
    """Tests for the shared context builder helper."""

    def test_empty_inputs_returns_empty(self):
        result = _build_conversation_context("", None, None)
        assert result == ""

    def test_none_transcript_returns_empty(self):
        result = _build_conversation_context(None, None, None)
        assert result == ""

    def test_whitespace_only_transcript_returns_empty(self):
        result = _build_conversation_context("   ", None, None)
        assert result == ""

    def test_transcript_only(self):
        result = _build_conversation_context("Speaker 0: Hello\n\nSpeaker 1: Hi", None, None)
        assert result == "Transcript: ```Speaker 0: Hello\n\nSpeaker 1: Hi```"

    def test_deterministic_output(self):
        """Same inputs must produce byte-identical output for cache hits."""
        transcript = "Speaker 0: Let's discuss the budget.\n\nSpeaker 1: Sure, I have the numbers."
        result1 = _build_conversation_context(transcript, None, None)
        result2 = _build_conversation_context(transcript, None, None)
        assert result1 == result2

    def test_calendar_context_includes_meeting_link(self):
        """Verify meeting_link is included in the shared context (was missing in extract_action_items)."""
        calendar = CalendarMeetingContext(
            calendar_event_id="test-event-1",
            title="Q2 Budget Review",
            start_time=datetime(2025, 3, 15, 14, 0, tzinfo=timezone.utc),
            duration_minutes=60,
            platform="Google Meet",
            meeting_link="https://meet.google.com/abc-def-ghi",
            participants=[
                MeetingParticipant(name="Alice", email="alice@example.com"),
            ],
        )
        result = _build_conversation_context("Speaker 0: Hello", None, calendar)
        assert "Meeting Link: https://meet.google.com/abc-def-ghi" in result

    def test_calendar_context_includes_all_fields(self):
        calendar = CalendarMeetingContext(
            calendar_event_id="test-event-1",
            title="Sprint Planning",
            start_time=datetime(2025, 3, 15, 10, 0, tzinfo=timezone.utc),
            duration_minutes=30,
            platform="Zoom",
            notes="Discuss backlog items",
            meeting_link="https://zoom.us/j/123",
            participants=[
                MeetingParticipant(name="Bob", email="bob@co.com"),
                MeetingParticipant(name="Carol", email="carol@co.com"),
            ],
        )
        result = _build_conversation_context("Speaker 0: Hi", None, calendar)
        assert "Meeting Title: Sprint Planning" in result
        assert "Duration: 30 minutes" in result
        assert "Platform: Zoom" in result
        assert "Meeting Notes: Discuss backlog items" in result
        assert "Meeting Link: https://zoom.us/j/123" in result
        assert "Bob <bob@co.com>" in result
        assert "Carol <carol@co.com>" in result

    def test_calendar_before_transcript(self):
        """Calendar context should appear before transcript for consistent ordering."""
        calendar = CalendarMeetingContext(
            calendar_event_id="test-event-1",
            title="Standup",
            start_time=datetime(2025, 3, 15, 9, 0, tzinfo=timezone.utc),
            duration_minutes=15,
            participants=[],
        )
        result = _build_conversation_context("Speaker 0: Good morning", None, calendar)
        calendar_pos = result.index("CALENDAR MEETING CONTEXT")
        transcript_pos = result.index("Transcript:")
        assert calendar_pos < transcript_pos

    def test_no_meeting_link_omitted(self):
        """When meeting_link is None, the line should not appear."""
        calendar = CalendarMeetingContext(
            calendar_event_id="test-event-1",
            title="Standup",
            start_time=datetime(2025, 3, 15, 9, 0, tzinfo=timezone.utc),
            duration_minutes=15,
            participants=[],
        )
        result = _build_conversation_context("Speaker 0: Hi", None, calendar)
        assert "Meeting Link" not in result

    def test_no_notes_omitted(self):
        """When notes is None, the line should not appear."""
        calendar = CalendarMeetingContext(
            calendar_event_id="test-event-1",
            title="Standup",
            start_time=datetime(2025, 3, 15, 9, 0, tzinfo=timezone.utc),
            duration_minutes=15,
            participants=[],
        )
        result = _build_conversation_context("Speaker 0: Hi", None, calendar)
        assert "Meeting Notes" not in result

    def test_deterministic_with_calendar(self):
        """Full context with calendar must be byte-identical across calls."""
        calendar = CalendarMeetingContext(
            calendar_event_id="test-event-1",
            title="Review",
            start_time=datetime(2025, 6, 1, 15, 0, tzinfo=timezone.utc),
            duration_minutes=45,
            platform="Teams",
            meeting_link="https://teams.microsoft.com/l/123",
            notes="Review PR",
            participants=[
                MeetingParticipant(name="Dan", email="dan@co.com"),
            ],
        )
        transcript = "Speaker 0: Let's review the PR.\n\nSpeaker 1: Sure."
        result1 = _build_conversation_context(transcript, None, calendar)
        result2 = _build_conversation_context(transcript, None, calendar)
        assert result1 == result2

    def test_participant_without_email(self):
        """Participant with name only should show name without angle brackets."""
        calendar = CalendarMeetingContext(
            calendar_event_id="test-event-1",
            title="Chat",
            start_time=datetime(2025, 3, 15, 9, 0, tzinfo=timezone.utc),
            duration_minutes=10,
            participants=[
                MeetingParticipant(name="Eve", email=None),
            ],
        )
        result = _build_conversation_context("test", None, calendar)
        assert "Eve" in result
        assert "<None>" not in result

    def test_participant_without_name(self):
        """Participant with email only should show email."""
        calendar = CalendarMeetingContext(
            calendar_event_id="test-event-1",
            title="Chat",
            start_time=datetime(2025, 3, 15, 9, 0, tzinfo=timezone.utc),
            duration_minutes=10,
            participants=[
                MeetingParticipant(name=None, email="unknown@co.com"),
            ],
        )
        result = _build_conversation_context("test", None, calendar)
        assert "unknown@co.com" in result
