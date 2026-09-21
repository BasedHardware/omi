import pytest
from fastapi import status
from fastapi.testclient import TestClient
from unittest import mock

# Import the FastAPI app that aggregates the routers.
# Assuming the main FastAPI instance lives in plugins/omi-slack-app/main.py
from ..main import app

client = TestClient(app)

# Helper to assert that a response does NOT contain a given sensitive string
def assert_no_sensitive_info(response, sensitive):
    assert sensitive not in response.text

# ----------------------------------------------------------------------
# 1. /auth endpoint – force an exception inside the handler
# ----------------------------------------------------------------------
def test_auth_exception_is_sanitized(monkeypatch):
    def broken_init():
        raise RuntimeError("SECRET_TOKEN=abcd1234")
    monkeypatch.setattr("plugins.omi_slack_app.routes.auth.oauth_init", broken_init)
    resp = client.get("/auth")
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert resp.json()["detail"] == "Internal server error"
    assert_no_sensitive_info(resp, "SECRET_TOKEN")

# ----------------------------------------------------------------------
# 2. /update-channel – generic failure
# ----------------------------------------------------------------------
def test_update_channel_exception_is_sanitized(monkeypatch):
    def broken(payload):
        raise ValueError("DB_PASSWORD=supersecret")
    monkeypatch.setattr("plugins.omi_slack_app.routes.update_channel.update_channel", broken)
    resp = client.post("/update-channel", json={"dummy": "data"})
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert resp.json()["detail"] == "Internal server error"
    assert_no_sensitive_info(resp, "DB_PASSWORD")

# ----------------------------------------------------------------------
# 3. /refresh-channels – generic failure
# ----------------------------------------------------------------------
def test_refresh_channels_exception_is_sanitized(monkeypatch):
    def broken():
        raise RuntimeError("AWS_KEY=xyz")
    monkeypatch.setattr("plugins.omi_slack_app.routes.refresh_channels.refresh_channels", broken)
    resp = client.post("/refresh-channels")
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert resp.json()["detail"] == "Internal server error"
    assert_no_sensitive_info(resp, "AWS_KEY")

# ----------------------------------------------------------------------
# 4. /logout – generic failure
# ----------------------------------------------------------------------
def test_logout_exception_is_sanitized(monkeypatch):
    def broken():
        raise RuntimeError("TOKEN=leak")
    monkeypatch.setattr("plugins.omi_slack_app.routes.logout.logout", broken)
    resp = client.post("/logout")
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert resp.json()["detail"] == "Internal server error"
    assert_no_sensitive_info(resp, "TOKEN")

# ----------------------------------------------------------------------
# 5. /webhook – malformed JSON
# ----------------------------------------------------------------------
def test_webhook_invalid_json():
    # Send invalid JSON payload (plain text)
    resp = client.post("/webhook", data="not a json")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.json()["detail"] == "Invalid JSON payload"
    assert_no_sensitive_info(resp, "not a json")

# ----------------------------------------------------------------------
# 6. Chat tool endpoints – internal Slack client errors
# ----------------------------------------------------------------------
@pytest.fixture
def mock_slack_client_error(monkeypatch):
    async def error(*args, **kwargs):
        raise RuntimeError("SLACK_BOT_TOKEN=leaked")
    monkeypatch.setattr(
        "plugins.omi_slack_app.slack_client.SlackClient.send_message",
        error,
    )
    monkeypatch.setattr(
        "plugins.omi_slack_app.slack_client.SlackClient.search_messages",
        error,
    )
    monkeypatch.setattr(
        "plugins.omi_slack_app.slack_client.SlackClient.search_channels",
        error,
    )

def test_send_message_sanitized(mock_slack_client_error):
    resp = client.post("/api/send_message", json={"channel": "C123", "text": "hi"})
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert resp.json()["detail"] == "Internal server error"
    assert_no_sensitive_info(resp, "SLACK_BOT_TOKEN")

def test_search_messages_sanitized(mock_slack_client_error):
    resp = client.post("/api/search_messages", json={"query": "test"})
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert resp.json()["detail"] == "Internal server error"
    assert_no_sensitive_info(resp, "SLACK_BOT_TOKEN")

def test_search_channels_sanitized(mock_slack_client_error):
    resp = client.post("/api/search_channels", json={"query": "general"})
    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert resp.json()["detail"] == "Internal server error"
    assert_no_sensitive_info(resp, "SLACK_BOT_TOKEN")
