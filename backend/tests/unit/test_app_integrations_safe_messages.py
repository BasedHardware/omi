"""Regression test: one malformed stored chat message must not abort the whole
proactive-notification build.

utils.app_integrations._process_proactive_notification loads the last 10 app chat
messages to substitute into the {{user_chat}} prompt slot. It used to build them with
[Message(**msg) for msg in get_app_messages(...)], so a single legacy or malformed
stored record raised a ValidationError. The only production caller wraps this in a broad
except (fire-and-forget via run_blocking), so the failure was silent: the proactive
notification was dropped on every run for that user until the bad row aged out of the
last-10 window. The fix routes the batch through Message.deserialize_many_safe (the
shared safe-deserialize helper added in #8882), which skips the bad record and keeps the
rest, so the notification is still built and sent.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

import utils.app_integrations as app_int

_GOOD_MESSAGE = {
    "id": "good-1",
    "text": "remember to drink water",
    "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
    "sender": "human",
    "type": "text",
}
# Missing text / created_at / sender / type -> Message(**record) raises ValidationError.
_MALFORMED_MESSAGE = {"id": "legacy-broken"}


@pytest.fixture
def proactive_env(monkeypatch):
    """Neutralize every dependency _process_proactive_notification touches except the real
    Message deserialization this test is exercising (app_int.Message stays the real class)."""
    monkeypatch.setattr(app_int, "_hit_proactive_notification_rate_limits", lambda uid, app: False)
    monkeypatch.setattr(app_int, "_proactive_daily_cap_reached", lambda uid: False)
    monkeypatch.setattr(app_int, "_set_proactive_noti_sent_at", MagicMock())
    monkeypatch.setattr(app_int, "get_prompt_memories", lambda uid: ("Zach", "likes tea"))
    monkeypatch.setattr(app_int, "send_app_notification", MagicMock())
    monkeypatch.setattr(app_int, "incr_daily_notification_count", MagicMock())

    llm = MagicMock()
    llm.invoke.return_value.content = "Here is your nudge."
    monkeypatch.setattr(app_int, "get_llm", MagicMock(return_value=llm))
    return monkeypatch


def _make_app():
    app = MagicMock()
    app.has_capability.return_value = True
    app.id = "app-x"
    app.name = "TestApp"
    app.filter_proactive_notification_scopes.return_value = ["user_chat"]
    return app


def test_malformed_message_does_not_abort_proactive_notification(proactive_env):
    proactive_env.setattr(
        app_int, "get_app_messages", lambda uid, app_id, limit=10: [_GOOD_MESSAGE, _MALFORMED_MESSAGE]
    )

    result = app_int._process_proactive_notification(
        "uid-1", _make_app(), {"prompt": "context: {{user_chat}}", "params": ["user_chat"]}
    )

    assert result == "Here is your nudge."


def test_all_messages_malformed_still_sends(proactive_env):
    proactive_env.setattr(app_int, "get_app_messages", lambda uid, app_id, limit=10: [_MALFORMED_MESSAGE])

    result = app_int._process_proactive_notification(
        "uid-2", _make_app(), {"prompt": "context: {{user_chat}}", "params": ["user_chat"]}
    )

    assert result == "Here is your nudge."
