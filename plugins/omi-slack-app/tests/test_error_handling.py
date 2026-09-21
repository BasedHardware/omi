import json
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from ..main import app  # The FastAPI application instance

client = TestClient(app)


@pytest.mark.parametrize(
    "method, url, payload",
    [
        ("post", "/update-channel", {"channel_id": "C123", "new_name": "new"}),
        ("post", "/refresh-channels", None),
        ("post", "/logout", None),
        ("post", "/api/send_message", {"channel": "C123", "text": "hi"}),
        ("post", "/api/search_messages", {"query": "test"}),
        ("post", "/api/search_channels", {"query": "general"}),
    ],
)
def test_generic_error_payloads(method, url, payload):
    """
    Simulate an internal error by monkey‑patching SlackClient methods to raise.
    The response must contain a generic error message and must not expose the
    original exception string.
    """
    from plugins.omi_slack_app import slack_client

    original = slack_client.SlackClient

    class BrokenClient(original):
        async def __getattr__(self, name):
            raise RuntimeError("sensitive internal detail")

    slack_client.SlackClient = BrokenClient

    response = client.request(method.upper(), url, json=payload)
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    data = response.json()
    assert data["success"] is False
    assert data["error"] == "Internal server error"

    # Restore original class for subsequent tests.
    slack_client.SlackClient = original


def test_auth_exception_hides_detail():
    """
    Ensure the /auth endpoint does not leak exception details.
    """
    from plugins.omi_slack_app import slack_client

    original = slack_client.SlackClient

    class BrokenClient(original):
        async def complete_oauth(self, *, state: str, code: str):
            raise RuntimeError("secret token path")

    slack_client.SlackClient = BrokenClient

    response = client.get("/auth?state=abc&code=def")
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.json()["detail"] == "OAuth initialization failed"

    slack_client.SlackClient = original


def test_webhook_invalid_json():
    """
    Invalid JSON payload should result in a generic 400 error without the
    original parsing exception.
    """
    response = client.post("/webhook", data="not a json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "Invalid JSON payload"
