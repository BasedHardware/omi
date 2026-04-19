"""Tests for user name context injection in transcript structure prompt (#6216)."""

import inspect
import re
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

# Mock modules that initialize clients at import time
sys.modules.setdefault("database._client", MagicMock())
sys.modules.setdefault("firebase_admin", MagicMock())
_mock_clients = MagicMock()
sys.modules.setdefault("utils.llm.clients", _mock_clients)

from models.structured import Structured
from utils.llm import conversation_processing as cp


class _FakeChain:
    def __init__(self, captured):
        self.captured = captured

    def __or__(self, _other):
        return self

    def invoke(self, values):
        self.captured["invoke_values"] = values
        return Structured()


class _FakePrompt:
    def __init__(self, captured):
        self.captured = captured

    def __or__(self, _other):
        return _FakeChain(self.captured)


def _run_with_user_name(monkeypatch, user_name: str):
    captured = {}

    def fake_from_messages(messages):
        captured["messages"] = messages
        return _FakePrompt(captured)

    monkeypatch.setattr(cp, "_build_conversation_context", lambda *_args, **_kwargs: "Transcript: ```hello```")
    monkeypatch.setattr(cp, "get_user_name", lambda _uid: user_name)
    monkeypatch.setattr(cp.ChatPromptTemplate, "from_messages", fake_from_messages)
    monkeypatch.setattr(cp.llm_medium_experiment, "bind", lambda **_kwargs: object())

    cp.get_transcript_structure(
        transcript="Speaker 0: hello",
        started_at=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
        language_code="en",
        tz="UTC",
        uid="user-123",
    )

    return captured


def test_get_transcript_structure_injects_named_user(monkeypatch):
    captured = _run_with_user_name(monkeypatch, "Aarav")

    assert "messages" in captured
    context_message = captured["messages"][1][1]
    assert "{user_name}" in context_message
    assert captured["invoke_values"]["user_name"] == "Aarav"


def test_get_transcript_structure_uses_default_user_name(monkeypatch):
    captured = _run_with_user_name(monkeypatch, "The User")
    assert captured["invoke_values"]["user_name"] == "The User"


def test_get_transcript_structure_supports_firestore_fallback_name(monkeypatch):
    captured = _run_with_user_name(monkeypatch, "Priya")
    assert captured["invoke_values"]["user_name"] == "Priya"


def test_get_transcript_structure_falls_back_when_get_user_name_raises(monkeypatch):
    captured = {}

    def fake_from_messages(messages):
        captured["messages"] = messages
        return _FakePrompt(captured)

    def raising_get_user_name(_uid):
        raise RuntimeError("redis down")

    monkeypatch.setattr(cp, "_build_conversation_context", lambda *_a, **_kw: "Transcript: ```hello```")
    monkeypatch.setattr(cp, "get_user_name", raising_get_user_name)
    monkeypatch.setattr(cp.ChatPromptTemplate, "from_messages", fake_from_messages)
    monkeypatch.setattr(cp.llm_medium_experiment, "bind", lambda **_kwargs: object())

    cp.get_transcript_structure(
        transcript="Speaker 0: hello",
        started_at=datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
        language_code="en",
        tz="UTC",
        uid="user-123",
    )

    assert captured["invoke_values"]["user_name"] == "The User"


def test_user_name_context_is_not_in_static_instructions_prefix():
    source = inspect.getsource(cp.get_transcript_structure)

    instructions_match = re.search(r"instructions_text\\s*=\\s*'''(.*?)'''", source, re.DOTALL)
    assert instructions_match, "Could not find instructions_text definition"
    instructions_content = instructions_match.group(1)
    assert "{user_name}" not in instructions_content

    context_match = re.search(r"context_message\\s*=", source)
    assert context_match, "Could not find context_message definition"
    assert "{user_name}" in source
