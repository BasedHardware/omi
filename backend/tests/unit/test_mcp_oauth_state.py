import os
import time

os.environ.setdefault(
    "ENCRYPTION_SECRET", "omi_test_state_signing_secret_for_unit_tests"
)

import pytest

from utils.mcp_client import (
    MCP_OAUTH_STATE_MAX_AGE_SECONDS,
    generate_state_token,
    parse_state_token,
    validate_mcp_oauth_state_subject,
)


class TestMcpOAuthStateSigning:
    def test_generated_state_round_trips(self):
        state = generate_state_token("app-123", "user-456")

        assert state.count(":") == 5
        assert state.startswith("v1:")
        assert parse_state_token(state) == ("app-123", "user-456")

    def test_generated_state_round_trips_with_colon_values(self):
        state = generate_state_token("collection:app-123", "tenant:user-456")

        assert state.count(":") == 5
        assert parse_state_token(state) == ("collection:app-123", "tenant:user-456")

    def test_tampered_state_signature_is_rejected(self):
        state = generate_state_token("app-123", "user-456")
        parts = state.split(":")
        tampered = ":".join([parts[0], parts[1], "dmljdGltLXVzZXI", *parts[3:]])

        with pytest.raises(ValueError, match="signature"):
            parse_state_token(tampered)

    def test_unsigned_legacy_state_is_rejected(self):
        with pytest.raises(ValueError, match="Invalid state token"):
            parse_state_token("app-123:user-456:nonce")

    def test_expired_state_is_rejected(self, monkeypatch):
        issued_at = int(time.time()) - MCP_OAUTH_STATE_MAX_AGE_SECONDS - 1
        monkeypatch.setattr(time, "time", lambda: issued_at)
        expired = generate_state_token("app-123", "user-456")
        monkeypatch.setattr(
            time, "time", lambda: issued_at + MCP_OAUTH_STATE_MAX_AGE_SECONDS + 1
        )

        with pytest.raises(ValueError, match="Expired"):
            parse_state_token(expired)


class TestMcpOAuthStateSubjectValidation:
    def test_state_uid_must_match_stored_app_owner(self):
        validate_mcp_oauth_state_subject({"uid": "owner-user"}, "owner-user")

    def test_forged_cross_user_state_is_rejected(self):
        with pytest.raises(ValueError, match="app owner"):
            validate_mcp_oauth_state_subject({"uid": "attacker-owner"}, "victim-user")

    def test_missing_app_owner_is_rejected(self):
        with pytest.raises(ValueError, match="app owner"):
            validate_mcp_oauth_state_subject({}, "victim-user")
