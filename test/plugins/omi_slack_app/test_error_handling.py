import pytest
from fastapi.testclient import TestClient
from plugins.omi_slack_app.main import app

client = TestClient(app)


@pytest.mark.parametrize(
    "method, url, payload, expected_status, expected_detail",
    [
        ("GET", "/auth", None, 500, "OAuth initialization failed"),
        ("POST", "/update-channel", {"dummy": "data"}, 500, "Failed to update channel"),
        ("POST", "/refresh-channels", None, 500, "Failed to refresh channels"),
        ("POST", "/logout", None, 500, "Logout failed"),
        ("POST", "/webhook", {"invalid": "json"}, 400, "Invalid JSON payload"),
        ("POST", "/api/send_message", {"token": "x", "channel": "C1", "text": "hi"}, 500, "Failed to send message"),
        ("POST", "/api/search_messages", {"token": "x", "query": "test"}, 500, "Failed to search messages"),
        ("POST", "/api/search_channels", {"token": "x", "query": "test"}, 500, "Failed to search channels"),
    ],
)
def test_generic_error_responses(
    method, url, payload, expected_status, expected_detail
):
    response = client.request(method, url, json=payload)
    assert response.status_code == expected_status
    json_body = response.json()
    # FastAPI returns {"detail": "..."} for HTTPException
    assert "detail" in json_body
    assert json_body["detail"] == expected_detail
    # Ensure raw exception text is NOT present
    assert "Simulated" not in json_body["detail"]
