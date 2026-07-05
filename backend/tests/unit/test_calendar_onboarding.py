"""Calendar onboarding + reconnect state: GET /v1/calendar/onboarding/status and POST .../reset.

When a user's Google Calendar OAuth token dies, refresh_google_token writes reauth_required +
reauth_reason and deletes access_token on the google_calendar integration, but no endpoint read
that back, so the app couldn't tell "never connected" from "was connected, now needs reconnect".
This surfaces needs_reconnect / reauth_reason / state on the status endpoint (existing keys kept)
and adds a reset endpoint that clears the skipped/reauth flags.

Test isolation: routers.calendar_onboarding imports cleanly; the pure state helper is tested
directly and the sync endpoints are called directly with users_db monkeypatched (no network).
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

import routers.calendar_onboarding as co

# --- pure state helper ---


def test_state_none_is_not_started():
    assert co._calendar_onboarding_state(None) == {
        "connected": False,
        "onboarding_completed": False,
        "needs_reconnect": False,
        "reauth_reason": None,
        "state": "not_started",
    }


def test_state_connected():
    s = co._calendar_onboarding_state({"connected": True, "access_token": "tok"})
    assert s["state"] == "connected"
    assert s["connected"] is True
    assert s["onboarding_completed"] is True
    assert s["needs_reconnect"] is False


def test_state_skipped_only():
    s = co._calendar_onboarding_state({"onboarding_skipped": True})
    assert s["state"] == "skipped"
    assert s["onboarding_completed"] is True
    assert s["connected"] is False


def test_state_needs_reconnect_invalid_grant():
    # Exact post-refresh-failure shape: reauth flags set, access_token deleted.
    s = co._calendar_onboarding_state({"connected": True, "reauth_required": True, "reauth_reason": "invalid_grant"})
    assert s["needs_reconnect"] is True
    assert s["reauth_reason"] == "invalid_grant"
    assert s["state"] == "needs_reconnect"


def test_state_needs_reconnect_missing_refresh_token():
    s = co._calendar_onboarding_state(
        {"connected": True, "reauth_required": True, "reauth_reason": "missing_refresh_token"}
    )
    assert s["reauth_reason"] == "missing_refresh_token"
    assert s["state"] == "needs_reconnect"


def test_connected_without_token_needs_reconnect():
    # Defensive: connected but access_token gone (deleted on refresh failure) even if the flag is absent.
    s = co._calendar_onboarding_state({"connected": True})
    assert s["needs_reconnect"] is True
    assert s["state"] == "needs_reconnect"


def test_reauth_reason_suppressed_when_not_required():
    s = co._calendar_onboarding_state({"connected": True, "access_token": "t", "reauth_reason": "stale"})
    assert s["needs_reconnect"] is False
    assert s["reauth_reason"] is None
    assert s["state"] == "connected"


def test_connected_and_skipped_prefers_connected():
    s = co._calendar_onboarding_state({"connected": True, "access_token": "t", "onboarding_skipped": True})
    assert s["state"] == "connected"


# --- endpoints ---


def test_status_endpoint_surfaces_needs_reconnect(monkeypatch):
    monkeypatch.setattr(
        co.users_db,
        "get_integration",
        lambda uid, key: {"connected": True, "reauth_required": True, "reauth_reason": "invalid_grant"},
    )
    result = co.get_calendar_onboarding_status(uid="u1")
    assert result["needs_reconnect"] is True
    assert result["reauth_reason"] == "invalid_grant"
    assert result["state"] == "needs_reconnect"


def test_status_endpoint_backward_compatible_keys(monkeypatch):
    monkeypatch.setattr(co.users_db, "get_integration", lambda uid, key: {"connected": True, "access_token": "t"})
    result = co.get_calendar_onboarding_status(uid="u1")
    assert result["connected"] is True
    assert result["onboarding_completed"] is True


def test_reset_endpoint_clears_flags(monkeypatch):
    calls = {}
    monkeypatch.setattr(
        co.users_db, "set_integration", lambda uid, key, data: calls.update(uid=uid, key=key, data=data)
    )
    result = co.reset_calendar_onboarding(uid="u1")
    assert result == {"reset": True}
    assert calls["uid"] == "u1"
    assert calls["key"] == "google_calendar"
    assert calls["data"] == {"onboarding_skipped": False, "reauth_required": False, "reauth_reason": None}
