"""Unit tests for developer webhook proactive notification null-safety.

Directly exercises utils.app_integrations._process_proactive_notification and
_retrieve_contextual_memories to guarantee that explicit null values in
third-party webhook payloads (prompt: null, params: null, context: null,
filters: null) are defensively normalized without unhandled exceptions.
"""

from datetime import timezone
from unittest.mock import MagicMock
import pytest

import utils.app_integrations as app_int
from models.app import App


@pytest.fixture
def proactive_env(monkeypatch):
    """Neutralize database and LLM calls for _process_proactive_notification."""
    monkeypatch.setattr(
        app_int, "_hit_proactive_notification_rate_limits", lambda uid, app: False
    )
    monkeypatch.setattr(
        app_int, "_proactive_daily_cap_reached", lambda uid: False
    )
    monkeypatch.setattr(app_int, "_set_proactive_noti_sent_at", MagicMock())
    monkeypatch.setattr(
        app_int, "get_prompt_memories", lambda uid: ("Alice", "likes python")
    )
    monkeypatch.setattr(app_int, "send_app_notification", MagicMock())
    monkeypatch.setattr(app_int, "incr_daily_notification_count", MagicMock())
    monkeypatch.setattr(app_int, "_user_day_zone", lambda _uid: timezone.utc)

    mock_llm = MagicMock()
    mock_llm.invoke.return_value.content = "Here is your proactive recommendation."
    monkeypatch.setattr(app_int, "get_llm", MagicMock(return_value=mock_llm))
    return monkeypatch


def _make_app(scopes=None):
    app = MagicMock(spec=App)
    app.has_capability.return_value = True
    app.id = "app-test"
    app.name = "TestApp"
    app.proactive_notification = MagicMock()
    app.proactive_notification.scopes = (
        scopes
        if scopes is not None
        else ["user_name", "user_facts", "user_context", "user_chat"]
    )
    # Bind the hardened filter_proactive_notification_scopes implementation
    app.filter_proactive_notification_scopes = (
        lambda params=None: App.filter_proactive_notification_scopes(app, params)
    )
    return app


def test_null_prompt_returns_none_safely(proactive_env):
    """Explicit null prompt returns None without len() TypeError or LLM call."""
    payload = {"prompt": None, "params": ["user_name"]}
    result = app_int._process_proactive_notification("uid-1", _make_app(), payload)
    assert result is None
    app_int.get_llm.return_value.invoke.assert_not_called()
    app_int.send_app_notification.assert_not_called()


def test_empty_and_whitespace_prompt_returns_none(proactive_env):
    """Empty or whitespace-only prompt returns None before invoking LLM."""
    for empty_p in ["", "   ", "\n\t  "]:
        result = app_int._process_proactive_notification(
            "uid-1", _make_app(), {"prompt": empty_p}
        )
        assert result is None
        app_int.get_llm.return_value.invoke.assert_not_called()


def test_non_string_prompt_returns_none_safely(proactive_env):
    """Non-string prompt types (int, dict, list) are safely rejected."""
    for bad_prompt in [123, {"key": "val"}, [1, 2, 3], True]:
        result = app_int._process_proactive_notification(
            "uid-1", _make_app(), {"prompt": bad_prompt}
        )
        assert result is None
        app_int.get_llm.return_value.invoke.assert_not_called()


def test_prompt_exceeding_char_limit_notifies_and_returns_none(proactive_env):
    """Prompt exceeding max char limit alerts user and aborts before LLM."""
    huge_prompt = "A" * 128001
    result = app_int._process_proactive_notification(
        "uid-1", _make_app(), {"prompt": huge_prompt}
    )
    assert result is None
    app_int.send_app_notification.assert_called_once()
    app_int.get_llm.return_value.invoke.assert_not_called()


def test_null_params_defaults_gracefully(proactive_env):
    """Explicit null params does not raise TypeError during scope filtering."""
    payload = {"prompt": "Advice for user", "params": None}
    result = app_int._process_proactive_notification("uid-1", _make_app(), payload)
    assert result == "Here is your proactive recommendation."
    app_int.send_app_notification.assert_called_once()


def test_non_list_params_defaults_gracefully(proactive_env):
    """Non-list params types (str, dict, int) default to empty scopes."""
    for bad_params in ["user_name", {"key": "val"}, 42]:
        app_int.send_app_notification.reset_mock()
        payload = {"prompt": "Advice for user", "params": bad_params}
        result = app_int._process_proactive_notification(
            "uid-1", _make_app(), payload
        )
        assert result == "Here is your proactive recommendation."


def test_params_with_null_and_mixed_items(proactive_env):
    """Params list containing None or non-string items is sanitized."""
    payload = {
        "prompt": "Hello {{user_name}}",
        "params": [None, 123, "user_name", False],
    }
    result = app_int._process_proactive_notification("uid-1", _make_app(), payload)
    assert result == "Here is your proactive recommendation."
    app_int.get_llm.return_value.invoke.assert_called_with("Hello Alice")


def test_null_context_handled_gracefully(proactive_env, monkeypatch):
    """Explicit null context does not crash _retrieve_contextual_memories."""
    retrieve_mock = MagicMock(return_value=[])
    monkeypatch.setattr(app_int, "_retrieve_contextual_memories", retrieve_mock)

    payload = {
        "prompt": "Context: {{user_context}}",
        "params": ["user_context"],
        "context": None,
    }
    result = app_int._process_proactive_notification("uid-1", _make_app(), payload)
    assert result == "Here is your proactive recommendation."
    retrieve_mock.assert_called_once_with("uid-1", {})


def test_retrieve_contextual_memories_skips_when_empty_context(monkeypatch):
    """Skip vector retrieval entirely when user_context is absent or empty."""
    query_mock = MagicMock()
    monkeypatch.setattr(app_int, "query_vectors_by_metadata", query_mock)

    # Null, non-mapping, or empty dict must immediately return []
    assert app_int._retrieve_contextual_memories("uid-1", None) == []
    assert app_int._retrieve_contextual_memories("uid-1", "invalid") == []
    assert app_int._retrieve_contextual_memories("uid-1", {}) == []
    assert (
        app_int._retrieve_contextual_memories(
            "uid-1", {"question": None, "filters": None}
        )
        == []
    )
    assert (
        app_int._retrieve_contextual_memories(
            "uid-1",
            {
                "question": "   ",
                "filters": {"people": None, "topics": None, "entities": None},
            },
        )
        == []
    )
    query_mock.assert_not_called()


def test_retrieve_contextual_memories_filters_non_string_terms(monkeypatch):
    """Metadata terms are strictly filtered to valid strings, not stringified."""
    query_mock = MagicMock(return_value=["mem-1"])
    monkeypatch.setattr(app_int, "query_vectors_by_metadata", query_mock)
    monkeypatch.setattr(
        app_int,
        "generate_embedding",
        MagicMock(return_value=[0.1] * 3072),
    )
    monkeypatch.setattr(
        app_int.conversations_db,
        "get_conversations_by_id",
        MagicMock(return_value=[{"id": "mem-1", "is_locked": False}]),
    )

    context = {
        "question": "What did we talk about?",
        "filters": {
            "people": [None, 123, True, "Alice", [1, 2]],
            "topics": ["Work", None, {"sub": "topic"}],
            "entities": ["Omi"],
            "dates": None,
        },
    }
    memories = app_int._retrieve_contextual_memories("uid-1", context)
    assert len(memories) == 1
    query_mock.assert_called_once_with(
        "uid-1",
        [0.1] * 3072,
        dates_filter=[None, None],
        people=["Alice"],
        topics=["Work"],
        entities=["Omi"],
        dates=[],
    )


def test_app_filter_proactive_notification_scopes_direct_null_call():
    """Direct call on App.filter_proactive_notification_scopes with None returns []."""
    app = App(
        id="app-1",
        name="App1",
        uid="owner-1",
        proactive_notification={"scopes": ["user_name", "user_facts"]},
    )
    assert app.filter_proactive_notification_scopes(None) == []
    assert app.filter_proactive_notification_scopes([]) == []
    assert (
        app.filter_proactive_notification_scopes(
            [None, "user_name", 999, "invalid_scope"]
        )
        == ["user_name"]
    )
