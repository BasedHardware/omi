"""
Tests for the Whoop weekly_summary tool route.

Uses FastAPI's dependency_overrides to bypass the shared-secret auth guard
during testing, following the idiomatic pattern used by related fixes.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

# Import the app/router components
import sys
import os

# Ensure the plugins directory is on the path
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", ".."),
)

from plugins.omi_whooop_app.main import router, WHOOP_TOOLS_SECRET
from plugins.omi_whoop_app.whoop_tools_auth import require_whoop_tools_auth


@pytest.fixture
def client():
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(router, prefix="/tools/whoop")
    return TestClient(app)


@pytest.fixture
def valid_token():
    """Return a valid WHOOP_TOOLS_SECRET for testing."""
    return "test_secret_value"


class TestWeeklySummaryAuth:
    """Tests verifying the auth guard blocks unauthenticated requests."""

    def test_missing_token_returns_401(self, client):
        """Request without any auth should return 401."""
        resp = client.post(
            "/tools/whoop/get_weekly_summary",
            json={"uid": "user123"},
        )
        assert resp.status_code == 401

    def test_wrong_token_returns_401(self, client):
        """Request with an incorrect token should return 401."""
        resp = client.post(
            "/tools/whoop/get_weekly_summary",
            json={"uid": "user123"},
            headers={"Authorization": "Bearer wrong_token"},
        )
        assert resp.status_code == 401

    def test_query_param_wrong_token_returns_401(self, client):
        """Request with wrong query-param token should return 401."""
        resp = client.post(
            "/tools/whoop/get_weekly_summary?whoop_tools_token=wrong_token",
            json={"uid": "user123"},
        )
        assert resp.status_code == 401


class TestWeeklySummarySuccess:
    """Tests verifying successful authenticated requests return data."""

    @pytest.fixture(autouse=True)
    def _override_auth(self, valid_token):
        """Bypass auth guard using dependency_overrides for real TestClient coverage."""
        from fastapi import FastAPI
        from plugins.omi_whoop_app.main import router as whoop_router
        from plugins.omi_whoop_app.whoop_tools_auth import require_whoop_tools_auth

        app = FastAPI()
        app.dependency_overrides[require_whoop_tools_auth] = lambda: {"authenticated": True}
        app.include_router(whoop_router, prefix="/tools/whoop")
        self._client = TestClient(app)
        yield
        self._client.close()

    @patch("plugins.omi_whoop_app.main.get_valid_access_token", new_callable=AsyncMock)
    @patch("plugins.omi_whoop_app.main.whoop_api_request", new_callable=AsyncMock)
    def test_get_weekly_summary_with_valid_token(self, mock_api, mock_token, _override_auth):
        """Authentic request should call Whoop API and return data."""
        mock_token.return_value = "valid_access_token"
        mock_api.return_value = {
            "weekly_summary": [
                {"week_ending": "2024-01-07", "averagestrain": 0.85},
            ]
        }

        resp = self._client.post(
            "/tools/whoop/get_weekly_summary",
            json={"uid": "user123"},
            headers={"Authorization": "Bearer test_secret_value"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "weekly_summary" in data
        mock_api.assert_called_once_with("valid_access_token", "weekly_summary")


class TestWeeklySummaryNoSecret:
    """Tests verifying fail-closed behavior when WHOOP_TOOLS_SECRET is unset."""

    @patch.dict(os.environ, {}, clear=True)
    def test_no_secret_returns_503(self, client):
        """When WHOOP_TOOLS_SECRET is unset, endpoint returns 503."""
        # Force re-import to pick up cleared env
        import importlib
        import plugins.omi_whoop_app.whoop_tools_auth as auth_module
        importlib.reload(auth_module)

        # Re-create router with fresh secret state
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router, prefix="/tools/whoop")
        test_client = TestClient(app)

        resp = test_client.post(
            "/tools/whoop/get_weekly_summary",
            json={"uid": "user123"},
            headers={"Authorization": "Bearer anything"},
        )
        assert resp.status_code == 503
        test_client.close()
