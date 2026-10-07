"""Tests for OpenAI prompt caching support in conversation processing (issue #4654).

Verifies that:
1. _build_conversation_context() produces deterministic, identical output for the same inputs
2. extract_action_items() uses conversation context as the second system message
   (after static instructions) to enable OpenAI prompt caching
3. Calendar context is unified (includes meeting_link in both functions)
"""

import inspect
import re
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from models.calendar_context import CalendarMeetingContext, MeetingParticipant
from models.conversation_photo import ConversationPhoto
from utils.llm.model_config import LUNA_MODEL
from utils.llm import conversation_processing as conv_proc
from utils.llm.conversation_processing import (
    ACTION_ITEMS_CACHE_KEY,
    _build_conversation_context,
    _gpt56_cacheable_system_message,
    extract_action_items,
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
        return re.findall(r'from_messages\(\s*\[(.*?)\]\s*\)', source, re.DOTALL)

    def test_extract_action_items_instructions_first(self):
        """Static instructions must be the first system message for cross-conversation caching."""
        calls = self._get_from_messages_calls(extract_action_items)
        assert len(calls) == 1, "Expected exactly one from_messages call"
        args = calls[0].strip()
        instructions_pos = args.index('_gpt56_cacheable_system_message(')
        context_pos = args.index('context_message')
        assert instructions_pos < context_pos, "instructions_text must come before context_message"

    def test_action_items_uses_two_system_messages(self):
        """The action-items prompt must use exactly two system messages."""
        calls = self._get_from_messages_calls(extract_action_items)
        assert len(calls) == 1, "expected one from_messages call"
        assert calls[0].count('_gpt56_cacheable_system_message(') == 1
        assert calls[0].count("('system', context_message)") == 1

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
        context_match = re.search(r"context_message\s*=\s*'''(.*?)'''", source, re.DOTALL)
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
        context_match = re.search(r"context_message\s*=\s*'''(.*?)'''", source, re.DOTALL)
        assert context_match, "Could not find context_message definition"
        assert 'language_code' in context_match.group(1), "language_code should be in context_message"


class TestPromptCacheRetention:
    """Tests for 24h prompt cache retention and routing keys (PR #4674)."""

    @staticmethod
    def _read_clients_source():
        from pathlib import Path

        clients_path = Path(__file__).resolve().parent.parent.parent / "utils" / "llm" / "clients.py"
        return clients_path.read_text(encoding="utf-8")

    @staticmethod
    def _import_model_config():
        """Import model_config.py in isolation (it has only stdlib deps)."""
        import importlib.util
        from pathlib import Path

        path = Path(__file__).resolve().parent.parent.parent / "utils" / "llm" / "model_config.py"
        spec = importlib.util.spec_from_file_location("_omi_model_config_test", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_qos_openai_llm_gates_retention_by_capability(self):
        """_get_or_create_openai_llm must gate prompt_cache_retention=24h via a capability check."""
        source = self._read_clients_source()
        match = re.search(
            r"_get_or_create_openai_llm.*?supports_cache_retention\(.*?prompt_cache_retention.*?24h",
            source,
            re.DOTALL,
        )
        assert match, "_get_or_create_openai_llm should gate prompt_cache_retention='24h' by supports_cache_retention()"

    def test_capability_gating_matrix(self):
        """Capability gating (not exact names): renamed gpt-5 still cached, non-capable models untouched."""
        mc = self._import_model_config()
        # A renamed/future gpt-5 family model must still get routing + retention.
        assert mc.supports_prompt_cache("gpt-5.9-turbo"), "renamed gpt-5 should support prompt_cache_key"
        assert mc.supports_cache_retention("gpt-5.9-turbo"), "renamed gpt-5 should support 24h retention"
        assert mc.supports_prompt_cache(LUNA_MODEL)
        assert not mc.supports_cache_retention(LUNA_MODEL), "gpt-x-luna uses explicit cache options"
        assert mc.supports_prompt_cache("gpt-5.6-sol")
        assert not mc.supports_cache_retention("gpt-5.6-sol"), "GPT-5.6 uses explicit 30m cache options"
        # Retired product models are no longer treated as active cache targets.
        assert not mc.supports_prompt_cache("gpt-4.1-mini")
        assert not mc.supports_cache_retention("gpt-4.1-mini")
        # Non-OpenAI models get neither.
        assert not mc.supports_prompt_cache("gemini-2.5-flash-lite")
        assert not mc.supports_cache_retention("gemini-2.5-flash-lite")

    def test_explicit_cache_and_chat_sanitizer_predicate(self):
        """One helper covers the GPT-5.6 wire contract and the canonical Luna id."""
        mc = self._import_model_config()
        assert mc.uses_explicit_cache_and_chat_sanitizer(mc.LUNA_MODEL)
        assert mc.uses_explicit_cache_and_chat_sanitizer("gpt-5.6-sol")
        assert mc.uses_explicit_cache_and_chat_sanitizer("gpt-5.6-terra")
        assert not mc.uses_explicit_cache_and_chat_sanitizer("gpt-5-nano")
        assert not mc.uses_explicit_cache_and_chat_sanitizer("gpt-4o")
        assert not mc.uses_explicit_cache_and_chat_sanitizer("")
        assert not mc.supports_cache_retention(mc.LUNA_MODEL)
        assert not mc.supports_cache_retention("gpt-5.6-terra")

        from pathlib import Path

        backend = Path(__file__).resolve().parent.parent.parent
        sites = {
            "utils/llm/clients.py": 1,
            "utils/llm/model_config.py": 2,
            "utils/llm/conversation_prompt_prefix.py": 1,
            "utils/llm/proactive_notification.py": 1,
            "llm_gateway/gateway/executor.py": 2,
        }
        for rel, minimum in sites.items():
            text = (backend / rel).read_text(encoding="utf-8")
            assert text.count("uses_explicit_cache_and_chat_sanitizer") >= minimum, rel

    def test_cache_retention_not_in_model_kwargs(self):
        """prompt_cache_retention must NOT be in model_kwargs (SDK rejects it there)."""
        source = self._read_clients_source()
        mk_blocks = re.findall(r'model_kwargs\s*=\s*\{[^}]*\}', source)
        for block in mk_blocks:
            assert 'prompt_cache_retention' not in block, f"prompt_cache_retention must not be in model_kwargs: {block}"

    def test_prompt_cache_key_in_action_items_function(self):
        """The action-items path keeps a fixed, non-user-derived cache routing key."""
        source = inspect.getsource(extract_action_items)
        assert 'ACTION_ITEMS_CACHE_KEY' in source
        assert "cache_key = 'omi-extract-actions'" in source


def test_explicit_cache_system_message_preserves_parser_schema_braces():
    """A cached system message must bypass ChatPromptTemplate variable parsing."""
    from langchain_core.prompts import ChatPromptTemplate

    system_message = _gpt56_cacheable_system_message('{"title": "string"}', cache_enabled=True, formatted=True)
    prompt = ChatPromptTemplate.from_messages([system_message, ('system', 'Content: {conversation_context}')])

    messages = prompt.format_messages(conversation_context='Transcript: hello')

    assert messages[0].content == [
        {
            'type': 'text',
            'text': '{"title": "string"}',
            'prompt_cache_breakpoint': {'mode': 'explicit'},
        }
    ]


def test_gateway_formatted_instructions_without_explicit_cache_stay_a_concrete_message():
    """The explicit-cache kill switch must not degrade pre-formatted instructions to a tuple template.

    Gateway mode pre-formats the parser schema (with literal JSON braces) into
    instructions_text. If that text were passed as a ('system', ...) template
    tuple, ChatPromptTemplate would parse the braces as variables and fail
    before the LLM call — the cache-off rollback path would be broken.
    """
    from langchain_core.prompts import ChatPromptTemplate

    message = _gpt56_cacheable_system_message('Schema: {"title": "string"}', cache_enabled=False, formatted=True)

    assert not isinstance(message, tuple), 'formatted instructions must be a concrete message'
    assert message.content == [
        {'type': 'text', 'text': 'Schema: {"title": "string"}'}
    ], 'no breakpoint: explicit-cache disabled must not request a cache write'

    prompt = ChatPromptTemplate.from_messages([message, ('system', 'Content: {conversation_context}')])
    rendered = prompt.format_messages(conversation_context='Transcript: hello')
    assert rendered[0].content[0]['text'] == 'Schema: {"title": "string"}'


def test_gpt56_cache_keys_are_stable_versioned_and_never_include_request_content():
    assert ACTION_ITEMS_CACHE_KEY == 'omi-extract-actions-v1'
    assert conv_proc._has_gpt56_cacheable_static_prefix('static ' * 1_100)
    assert not conv_proc._has_gpt56_cacheable_static_prefix('short prefix')


def test_gpt56_explicit_cache_defaults_on_in_gateway_and_honors_kill_switch(monkeypatch):
    monkeypatch.setattr(conv_proc, 'should_route_features_through_gateway', lambda: True)
    monkeypatch.delenv(conv_proc.GPT56_EXPLICIT_CACHE_ENABLED_ENV, raising=False)
    assert conv_proc._gpt56_explicit_cache_enabled()

    monkeypatch.setenv(conv_proc.GPT56_EXPLICIT_CACHE_ENABLED_ENV, 'false')
    assert not conv_proc._gpt56_explicit_cache_enabled()

    monkeypatch.setenv(conv_proc.GPT56_EXPLICIT_CACHE_ENABLED_ENV, 'true')
    assert conv_proc._gpt56_explicit_cache_enabled()

    monkeypatch.setattr(conv_proc, 'should_route_features_through_gateway', lambda: False)
    assert not conv_proc._gpt56_explicit_cache_enabled()


def test_unique_prompt_app_result_drops_legacy_cache_key_whenever_gateway_mode_is_on(monkeypatch):
    """Regression (cubic review): the None/legacy cache_key split keys on gateway mode.

    get_app_result has no cacheable static prefix. With the gateway on it must still pass
    cache_key=None: a legacy prompt_cache_key would opt these unique-prompt requests back into
    implicit, billable cache writes. The explicit cache kill switch is set below to verify the
    old fully-disabled behavior remains available.
    """
    monkeypatch.setattr(conv_proc, 'should_route_features_through_gateway', lambda: True)
    monkeypatch.setenv(conv_proc.GPT56_EXPLICIT_CACHE_ENABLED_ENV, 'false')

    captured: dict = {}

    class _LLM:
        def invoke(self, *_args, **_kwargs):
            return MagicMock(content='{}')

    def _fake_get_llm(_feature, **kwargs):
        captured.update(kwargs)
        return _LLM()

    app = MagicMock()
    app.name = 'Test App'
    app.description = 'desc'
    app.memory_prompt = 'memory prompt'
    with patch.object(conv_proc, 'get_llm', side_effect=_fake_get_llm):
        conv_proc.get_app_result(transcript='Lunch meeting', photos=[], app=app, language_code='en')

    assert captured['cache_key'] is None
    assert captured['prompt_cache_options'] is None
