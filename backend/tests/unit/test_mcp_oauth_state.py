import os

import pytest

from utils.mcp_client import (
    generate_state_token,
    parse_state_token,
    validate_mcp_oauth_state_subject,
)


os.environ.setdefault(
    "ENCRYPTION_SECRET", "omi_test_state_signing_secret_for_unit_tests"
)


class TestMcpOAuthStateSigning:
    def test_generated_state_round_trips(self):
        state = generate_state_token("app-123", "user-456")

        assert state.count(":") == 3
        assert parse_state_token(state) == ("app-123", "user-456")

    def test_tampered_state_signature_is_rejected(self):
        state = generate_state_token("app-123", "user-456")
        tampered = state.replace("user-456", "victim-user")

        with pytest.raises(ValueError, match="signature"):
            parse_state_token(tampered)

    def test_legacy_state_still_parses_for_in_flight_oauth(self):
        assert parse_state_token("app-123:user-456:nonce") == ("app-123", "user-456")


class TestMcpOAuthStateSubjectValidation:
    def test_state_uid_must_match_stored_app_owner(self):
        validate_mcp_oauth_state_subject({"uid": "owner-user"}, "owner-user")

    def test_forged_cross_user_state_is_rejected(self):
        with pytest.raises(ValueError, match="app owner"):
            validate_mcp_oauth_state_subject({"uid": "attacker-owner"}, "victim-user")

    def test_missing_app_owner_is_rejected(self):
        with pytest.raises(ValueError, match="app owner"):
            validate_mcp_oauth_state_subject({}, "victim-user")
