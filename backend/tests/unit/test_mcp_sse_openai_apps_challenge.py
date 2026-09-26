"""Fail-closed coverage for /.well-known/openai-apps-challenge.

The challenge token moved from a hardcoded constant to the
``OPENAI_APPS_CHALLENGE_TOKEN`` environment variable. An unset variable must
fail closed with 404 (not an empty 200) so a misconfigured deployment breaks
OpenAI apps verification loudly instead of silently.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest


@pytest.fixture(scope="module")
def client():
    from routers import mcp_sse

    app = FastAPI()
    app.include_router(mcp_sse.router)
    return TestClient(app)


def test_openai_apps_challenge_serves_configured_token(client, monkeypatch):
    from routers import mcp_sse

    monkeypatch.setattr(mcp_sse, "OPENAI_APPS_CHALLENGE_TOKEN", "challenge-token-value")
    response = client.get("/.well-known/openai-apps-challenge")
    assert response.status_code == 200
    assert response.text == "challenge-token-value"
    assert response.headers["content-type"].startswith("text/plain")


def test_openai_apps_challenge_fails_closed_with_404_when_unset(client, monkeypatch):
    from routers import mcp_sse

    monkeypatch.setattr(mcp_sse, "OPENAI_APPS_CHALLENGE_TOKEN", None)
    response = client.get("/.well-known/openai-apps-challenge")
    assert response.status_code == 404
