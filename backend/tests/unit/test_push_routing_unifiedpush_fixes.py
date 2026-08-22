"""Push routing must reach UnifiedPush-only users: the important-conversation sync no longer
FCM-token-prechecks before routing, and BYOK error notifications import the send seam lazily so an
import cycle can't silently disable delivery (cubic review PR 10887)."""

import utils.notifications as notifications
from utils.llm import byok_errors


def test_important_conversation_routes_without_fcm_token_precheck(monkeypatch):
    calls = []
    monkeypatch.setattr(notifications, "_send_to_user", lambda uid, tag, **kw: calls.append((uid, kw.get("data"))))
    # A UnifiedPush-only user has no FCM tokens; the send must still be routed (not early-returned).
    monkeypatch.setattr(notifications.notification_db, "get_all_tokens", lambda _uid: [])

    notifications.send_important_conversation_message("u1", "conv-1")

    assert len(calls) == 1
    assert calls[0][1]["type"] == "important_conversation"


def test_byok_notification_delivers_via_lazy_import(monkeypatch):
    sent = []
    # The function imports send_user_notification lazily from utils.notifications at call time.
    monkeypatch.setattr(notifications, "send_user_notification", lambda uid, title, body, data: sent.append((uid, data)) or 1)
    monkeypatch.setattr(byok_errors, "try_acquire_byok_llm_error_notification_lock", lambda *a, **k: True)
    monkeypatch.setattr(byok_errors, "release_byok_llm_error_notification_lock", lambda *a, **k: None)

    byok_errors._send_byok_llm_error_notification("u1", "openai", "quota")

    assert len(sent) == 1
    assert sent[0][1]["type"] == "byok_llm_error"
