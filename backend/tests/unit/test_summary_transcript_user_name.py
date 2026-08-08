"""#5319 — LLM transcript rendering must use the configured profile name."""

from unittest.mock import MagicMock

import pytest

from utils.conversations.transcript_for_llm import conversation_transcript_for_llm


def test_conversation_transcript_for_llm_passes_configured_name(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "utils.conversations.transcript_for_llm.get_user_name",
        lambda uid, use_default=False: "Stephen",
    )
    conversation = MagicMock()
    conversation.get_transcript.return_value = "Stephen: Hello.\n\nSpeaker 1: Hi."
    people = [MagicMock()]

    rendered = conversation_transcript_for_llm("uid-1", conversation, people)

    conversation.get_transcript.assert_called_once_with(False, people=people, user_name="Stephen")
    assert rendered.startswith("Stephen:")


def test_conversation_transcript_for_llm_forwards_missing_name(monkeypatch: pytest.MonkeyPatch):
    """When no profile name exists, forward None so segments_as_string keeps its 'User' fallback."""
    monkeypatch.setattr(
        "utils.conversations.transcript_for_llm.get_user_name",
        lambda uid, use_default=False: None,
    )
    conversation = MagicMock()
    conversation.get_transcript.return_value = "User: Hello."

    conversation_transcript_for_llm("uid-1", conversation, people=None, include_timestamps=True)

    conversation.get_transcript.assert_called_once_with(True, people=None, user_name=None)
