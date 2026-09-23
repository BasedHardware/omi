"""Unit tests for integrations router OAuth URL endpoint exception sanitization.

Verifies that Redis connection errors do not leak internal hostnames, ports,
or credentials in the HTTP 500 response from GET /v1/integrations/{app_key}/oauth-url.
"""

import os
import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

import routers.integrations as integrations_routes


def test_redis_setex_connection_error_is_masked(monkeypatch):
    """ConnectionError from redis_db.r.setex must not leak host/port in HTTP 500 detail."""
    # Arrange
    monkeypatch.setenv("BASE_API_URL", "https://api.example.com")

    # Patch resolve_integration_provider to return a valid OAuth provider
    fake_provider = {
        "kind": "oauth",
        "name": "TestProvider",
        "oauth": {
            "client_id_env": "TEST_CLIENT_ID",
            "redirect_path": "/v1/integrations/test/callback",
            "scopes": ["read"],
        },
    }
    monkeypatch.setattr(
        integrations_routes,
        "resolve_integration_provider",
        lambda app_key: ("test", fake_provider),
    )
    monkeypatch.setenv("TEST_CLIENT_ID", "client-id-123")

    # Patch redis_db.r.setex to simulate a cluster connection failure
    leak_text = "redis-cluster-prod-01.internal:6379 connection refused (ECONNREFUSED)"
    mock_redis = MagicMock()
    mock_redis.setex.side_effect = ConnectionError(leak_text)
    monkeypatch.setattr(integrations_routes.redis_db, "r", mock_redis)

    # Act
    with pytest.raises(HTTPException) as exc_info:
        integrations_routes.get_oauth_url(app_key="test", uid="uid-test-001")

    # Assert: static message, no internal details
    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to initialize OAuth flow. Please try again."
    assert "redis-cluster-prod-01" not in exc_info.value.detail
    assert "6379" not in exc_info.value.detail
    assert "ECONNREFUSED" not in exc_info.value.detail


def test_redis_setex_generic_exception_is_masked(monkeypatch):
    """Any exception from redis_db.r.setex must return the same static 500 detail."""
    monkeypatch.setenv("BASE_API_URL", "https://api.example.com")

    fake_provider = {
        "kind": "oauth",
        "name": "TestProvider",
        "oauth": {
            "client_id_env": "TEST_CLIENT_ID2",
            "redirect_path": "/v1/integrations/test/callback",
            "scopes": [],
        },
    }
    monkeypatch.setattr(
        integrations_routes,
        "resolve_integration_provider",
        lambda app_key: ("test", fake_provider),
    )
    monkeypatch.setenv("TEST_CLIENT_ID2", "client-id-456")

    mock_redis = MagicMock()
    mock_redis.setex.side_effect = RuntimeError("auth=secret_password host=redis-prod-02")
    monkeypatch.setattr(integrations_routes.redis_db, "r", mock_redis)

    with pytest.raises(HTTPException) as exc_info:
        integrations_routes.get_oauth_url(app_key="test", uid="uid-test-002")

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to initialize OAuth flow. Please try again."
    assert "secret_password" not in exc_info.value.detail
    assert "redis-prod-02" not in exc_info.value.detail


# CI retrigger
