import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient
import os
import sys

# Add the backend directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from backend.routers.integrations import router as integrations_router
from backend.routers.oauth import router as oauth_router

@pytest.fixture
def client():
    """Create a test client."""
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(integrations_router)
    app.include_router(oauth_router)
    return TestClient(app)

class TestRedisErrorSanitization:
    """Test that Redis errors are sanitized and don't leak connection details."""

    @patch("backend.routers.integrations.get_redis_connection")
    def test_redis_connection_failure_returns_generic_error(self, mock_get_redis):
        """Test that Redis connection failures return generic 500 error."""
        # Simulate Redis connection failure
        mock_get_redis.side_effect = ConnectionError(
            "Connection refused to redis://internal-vpc:6379/0"
        )

        with pytest.raises(Exception) as exc_info:
            # This would be called via POST /integrations/
            from backend.routers.integrations import create_integration
            from unittest.mock import MagicMock
            from sqlalchemy.orm import Session

            # Create mock objects
            mock_db = MagicMock(spec=Session)
            mock_user = MagicMock()
            mock_user.id = 1

            # Call the function
            create_integration(MagicMock(), mock_db, mock_user)

        # Verify the error is generic and doesn't contain connection details
        assert "redis://internal-vpc" not in str(exc_info.value)
        assert "6379" not in str(exc_info.value)
        assert "Connection refused" not in str(exc_info.value)

    @patch("backend.routers.integrations.get_redis_connection")
    def test_redis_timeout_returns_generic_error(self, mock_get_redis):
        """Test that Redis timeout returns generic 500 error."""
        mock_get_redis.side_effect = TimeoutError("Redis connection timeout")

        with pytest.raises(Exception) as exc_info:
            from backend.routers.integrations import create_integration
            from unittest.mock import MagicMock
            from sqlalchemy.orm import Session

            mock_db = MagicMock(spec=Session)
            mock_user = MagicMock()
            mock_user.id = 1

            create_integration(MagicMock(), mock_db, mock_user)

        # Verify the error is generic
        assert "timeout" not in str(exc_info.value).lower() or "service temporarily unavailable" in str(exc_info.value)

class TestFirebaseErrorSanitization:
    """Test that Firebase errors are sanitized and don't leak endpoint details."""

    def test_firebase_init_failure_returns_generic_error(self, client):
        """Test that Firebase initialization failures return generic 500 error."""
        with patch("firebase_admin.initialize_app") as mock_init:
            mock_init.side_effect = Exception(
                "Failed to connect to https://firebase.googleapis.com/v1/projects/my-project"
            )

            with pytest.raises(Exception) as exc_info:
                from backend.routers.oauth import get_firebase_app
                get_firebase_app()

            # Verify no Firebase URLs are leaked
            assert "firebase.googleapis.com" not in str(exc_info.value)
            assert "my-project" not in str(exc_info.value)

    @patch("backend.routers.oauth.firebase_auth.verify_id_token")
    def test_invalid_token_returns_401_generic(self, mock_verify):
        """Test that invalid Firebase tokens return generic 401."""
        from firebase_admin.auth import InvalidIdTokenError
        mock_verify.side_effect = InvalidIdTokenError("invalid-argument", "Invalid token")

        response = client.post(
            "/oauth/verify",
            headers={"Authorization": "Bearer invalid-token"},
        )

        assert response.status_code == 401
        assert "Invalid token" not in response.json()["detail"]
        assert "invalid-argument" not in response.json()["detail"]

    @patch("backend.routers.oauth.firebase_auth.verify_id_token")
    def test_expired_token_returns_401_generic(self, mock_verify):
        """Test that expired Firebase tokens return generic 401."""
        from firebase_admin.auth import ExpiredIdTokenError
        mock_verify.side_effect = ExpiredIdTokenError("deadline-exceeded", "Token expired")

        response = client.post(
            "/oauth/verify",
            headers={"Authorization": "Bearer expired-token"},
        )

        assert response.status_code == 401
        assert "Token expired" not in response.json()["detail"]
        assert "deadline-exceeded" not in response.json()["detail"]

class TestOAuthTokenExchangeSanitization:
    """Test that OAuth token exchange errors are sanitized."""

    @patch("backend.routers.oauth.exchange_code_for_token")
    def test_token_exchange_failure_returns_generic_error(self, mock_exchange):
        """Test that token exchange failures return generic 500."""
        mock_exchange.side_effect = Exception(
            "Failed to exchange token with https://oauth.provider.com/token"
        )

        with pytest.raises(Exception) as exc_info:
            from backend.routers.oauth import exchange_token
            from unittest.mock import MagicMock

            mock_request = MagicMock()
            mock_request.form = MagicMock(return_value={
                "code": "test-code",
                "grant_type": "authorization_code"
            })

            exchange_token(mock_request, MagicMock())

        # Verify no provider URLs are leaked
        assert "oauth.provider.com" not in str(exc_info.value)
        assert "/token" not in str(exc_info.value)

    @patch("backend.routers.oauth.exchange_code_for_token")
    def test_token_exchange_connection_error_returns_generic(self, mock_exchange):
        """Test that connection errors in token exchange are generic."""
        mock_exchange.side_effect = ConnectionError(
            "Connection refused to https://internal-auth.provider.com:8443/token"
        )

        with pytest.raises(Exception) as exc_info:
            from backend.routers.oauth import exchange_token
            from unittest.mock import MagicMock

            mock_request = MagicMock()
            mock_request.form = MagicMock(return_value={
                "code": "test-code",
                "grant_type": "authorization_code"
            })

            exchange_token(mock_request, MagicMock())

        # Verify no internal endpoints are leaked
        assert "internal-auth.provider.com" not in str(exc_info.value)
        assert "8443" not in str(exc_info.value)
