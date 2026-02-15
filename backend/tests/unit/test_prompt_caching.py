"""Tests for OpenAI prompt caching support in conversation processing (issue #4654).

Verifies that:
1. _build_conversation_context() produces deterministic, identical output for the same inputs
2. get_transcript_structure() and extract_action_items() use conversation context
   as the second system message (after static instructions) to enable OpenAI prompt caching
3. Calendar context is unified (includes meeting_link in both functions)
"""

import inspect
import re
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

# Mock modules that initialize GCP clients or require API keys at import time
sys.modules.setdefault("database._client", MagicMock())
_mock_clients = MagicMock()
sys.modules.setdefault("utils.llm.clients", _mock_clients)

from models.conversation import CalendarMeetingContext, MeetingParticipant, ConversationPhoto
from utils.llm.conversation_processing import (
    _build_conversation_context,
    extract_action_items,
    get_transcript_structure,
)


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


class TestPromptMessageOrdering:
    """Tests that static instructions come before dynamic content in prompt templates.

    OpenAI prompt caching requires static content as a prefix for cross-conversation
    cache hits. These tests verify the message order is [instructions, context] not
    [context, instructions].
    """

    def _get_from_messages_calls(self, func):
        """Extract ChatPromptTemplate.from_messages call patterns from function source."""
        source = inspect.getsource(func)
        return re.findall(r'from_messages\(\[(.*?)\]\)', source, re.DOTALL)

    def test_get_transcript_structure_instructions_first(self):
        """Static instructions must be the first system message for cross-conversation caching."""
        calls = self._get_from_messages_calls(get_transcript_structure)
        assert len(calls) == 1, "Expected exactly one from_messages call"
        args = calls[0].strip()
        # instructions_text should come before context_message
        instructions_pos = args.index('instructions_text')
        context_pos = args.index('context_message')
        assert instructions_pos < context_pos, "instructions_text must come before context_message"

    def test_extract_action_items_instructions_first(self):
        """Static instructions must be the first system message for cross-conversation caching."""
        calls = self._get_from_messages_calls(extract_action_items)
        assert len(calls) == 1, "Expected exactly one from_messages call"
        args = calls[0].strip()
        instructions_pos = args.index('instructions_text')
        context_pos = args.index('context_message')
        assert instructions_pos < context_pos, "instructions_text must come before context_message"

    def test_both_functions_use_two_system_messages(self):
        """Both functions must use exactly two system messages."""
        for func in [get_transcript_structure, extract_action_items]:
            calls = self._get_from_messages_calls(func)
            assert len(calls) == 1, f"{func.__name__}: expected one from_messages call"
            # Count 'system' occurrences in the call
            system_count = calls[0].count("'system'")
            assert system_count == 2, f"{func.__name__}: expected 2 system messages, got {system_count}"

    def test_existing_items_context_not_in_instructions(self):
        """existing_items_context must be in the context message, not the instructions."""
        source = inspect.getsource(extract_action_items)
        # Find the instructions_text definition
        instructions_match = re.search(r"instructions_text\s*=\s*'''(.*?)'''", source, re.DOTALL)
        assert instructions_match, "Could not find instructions_text definition"
        instructions_content = instructions_match.group(1)
        assert (
            '{existing_items_context}' not in instructions_content
        ), "existing_items_context should not be in instructions_text (breaks static prefix caching)"
        # Verify it IS in the context_message
        context_match = re.search(r"context_message\s*=\s*['\"](.+?)['\"]", source)
        assert context_match, "Could not find context_message definition"
        assert 'existing_items_context' in context_match.group(1), "existing_items_context should be in context_message"

    def test_language_code_not_in_instructions(self):
        """language_code must be in the context message, not the instructions prefix."""
        source = inspect.getsource(extract_action_items)
        instructions_match = re.search(r"instructions_text\s*=\s*'''(.*?)'''", source, re.DOTALL)
        assert instructions_match, "Could not find instructions_text definition"
        instructions_content = instructions_match.group(1)
        assert (
            '{language_code}' not in instructions_content
        ), "language_code should not be in instructions_text (breaks static prefix caching for non-English)"
        context_match = re.search(r"context_message\s*=\s*['\"](.+?)['\"]", source)
        assert context_match, "Could not find context_message definition"
        assert 'language_code' in context_match.group(1), "language_code should be in context_message"


class TestPromptCacheRetention:
    """Tests for 24h prompt cache retention and routing keys (PR #4674)."""

    @staticmethod
    def _read_clients_source():
        from pathlib import Path

        clients_path = Path(__file__).resolve().parent.parent.parent / "utils" / "llm" / "clients.py"
        return clients_path.read_text()

    def test_llm_medium_experiment_has_cache_retention(self):
        """llm_medium_experiment must have extra_body with prompt_cache_retention=24h."""
        source = self._read_clients_source()
        # Find the llm_medium_experiment definition block and check extra_body
        match = re.search(
            r'llm_medium_experiment\s*=.*?extra_body\s*=\s*\{[^}]*"prompt_cache_retention"\s*:\s*"24h"',
            source,
            re.DOTALL,
        )
        assert match, "llm_medium_experiment missing extra_body with prompt_cache_retention='24h'"

    def test_llm_agent_has_cache_retention(self):
        """llm_agent must have extra_body with prompt_cache_retention=24h."""
        source = self._read_clients_source()
        match = re.search(
            r'llm_agent\s*=.*?extra_body\s*=\s*\{[^}]*"prompt_cache_retention"\s*:\s*"24h"', source, re.DOTALL
        )
        assert match, "llm_agent missing extra_body with prompt_cache_retention='24h'"

    def test_llm_agent_stream_has_cache_retention(self):
        """llm_agent_stream must have extra_body with prompt_cache_retention=24h."""
        source = self._read_clients_source()
        match = re.search(
            r'llm_agent_stream\s*=.*?extra_body\s*=\s*\{[^}]*"prompt_cache_retention"\s*:\s*"24h"', source, re.DOTALL
        )
        assert match, "llm_agent_stream missing extra_body with prompt_cache_retention='24h'"

    def test_cache_retention_not_in_model_kwargs(self):
        """prompt_cache_retention must NOT be in model_kwargs (SDK rejects it there)."""
        source = self._read_clients_source()
        mk_blocks = re.findall(r'model_kwargs\s*=\s*\{[^}]*\}', source)
        for block in mk_blocks:
            assert 'prompt_cache_retention' not in block, f"prompt_cache_retention must not be in model_kwargs: {block}"

    def test_prompt_cache_key_in_structure_function(self):
        """get_transcript_structure must use prompt_cache_key='omi-transcript-structure'."""
        source = inspect.getsource(get_transcript_structure)
        assert (
            'prompt_cache_key="omi-transcript-structure"' in source
        ), "get_transcript_structure missing prompt_cache_key binding"

    def test_prompt_cache_key_in_action_items_function(self):
        """extract_action_items must use prompt_cache_key='omi-extract-actions'."""
        source = inspect.getsource(extract_action_items)
        assert (
            'prompt_cache_key="omi-extract-actions"' in source
        ), "extract_action_items missing prompt_cache_key binding"

    def test_distinct_cache_keys_per_function(self):
        """Each function must have a distinct prompt_cache_key to avoid cache conflation."""
        source_structure = inspect.getsource(get_transcript_structure)
        source_actions = inspect.getsource(extract_action_items)
        key_structure = re.search(r'prompt_cache_key="([^"]+)"', source_structure)
        key_actions = re.search(r'prompt_cache_key="([^"]+)"', source_actions)
        assert key_structure and key_actions, "Both functions must have prompt_cache_key"
        assert key_structure.group(1) != key_actions.group(
            1
        ), f"Cache keys must be distinct: structure={key_structure.group(1)}, actions={key_actions.group(1)}"
