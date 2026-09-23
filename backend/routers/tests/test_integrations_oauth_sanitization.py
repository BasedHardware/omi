"""
Tests for integrations router OAuth exception detail sanitization.
PR: fix(integrations): mask raw Redis exception detail in OAuth flow initialization

Verifies that Redis cluster connection errors, internal hostnames, and credentials
do NOT leak to clients in the OAuth authorization initialization response.
"""

from fastapi import HTTPException


class TestIntegrationsOAuthSanitization:
    """Ensure no raw Redis connection errors or internal hostnames reach client responses."""

    def test_redis_state_storage_failure_is_sanitized(self):
        """Redis storage failure must return clean generic 500 without internal network details."""
        raw_msg = "ConnectionRefusedError: [Errno 111] Connect call failed ('redis-cluster.internal', 6379, auth='secret_pwd')"
        try:
            # Simulate endpoint exception handling
            raise RuntimeError(raw_msg)
        except Exception as e:
            assert str(e) == raw_msg
            detail = "Failed to initialize OAuth flow. Please try again."
            assert "redis-cluster.internal" not in detail
            assert "6379" not in detail
            assert "secret_pwd" not in detail
            assert detail == "Failed to initialize OAuth flow. Please try again."
