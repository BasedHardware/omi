from datetime import timedelta

import pytest

from utils.external_oauth.contracts import ConnectionState, Connector, ExternalOAuthError, RevocationDisposition
from utils.external_oauth.lifecycle import (
    ACCOUNT_DELETION_REVOKE_DEADLINE,
    ALLOWED_TRANSITIONS,
    DISCONNECT_RETENTION_DEADLINE,
    TERMINAL_STATES,
    revocation_retry_delay,
    transition_decision,
)
from utils.external_oauth.scopes import (
    CALENDAR_EVENTS_READONLY,
    EMAIL,
    GMAIL_READONLY,
    OPENID,
    canonicalize_scopes,
    require_exact_scopes,
)


def test_calendar_and_gmail_grants_are_exact_and_separate():
    assert require_exact_scopes(Connector.GOOGLE_CALENDAR, [OPENID, EMAIL, CALENDAR_EVENTS_READONLY]) == frozenset(
        {OPENID, EMAIL, CALENDAR_EVENTS_READONLY}
    )
    assert require_exact_scopes(Connector.GMAIL, [OPENID, EMAIL, GMAIL_READONLY]) == frozenset(
        {OPENID, EMAIL, GMAIL_READONLY}
    )
    with pytest.raises(ExternalOAuthError, match='provider_scope_set_mismatch'):
        require_exact_scopes(Connector.GMAIL, [OPENID, EMAIL, GMAIL_READONLY, CALENDAR_EVENTS_READONLY])


def test_provider_alias_is_canonicalized_but_unknown_scope_fails_closed():
    assert canonicalize_scopes(['https://www.googleapis.com/auth/userinfo.email']) == frozenset({EMAIL})
    with pytest.raises(ExternalOAuthError, match='provider_returned_unknown_scope'):
        canonicalize_scopes(['https://www.googleapis.com/auth/drive.readonly'])


def test_all_declared_transitions_are_executable_and_terminals_are_closed():
    for source, targets in ALLOWED_TRANSITIONS.items():
        for target in targets:
            disposition = None
            if target == ConnectionState.REVOKED:
                disposition = RevocationDisposition.PROVIDER_ALREADY_INVALID
            elif target == ConnectionState.PENDING_CONSENT:
                disposition = RevocationDisposition.PROVIDER_CONFIRMED_REVOKE
            decision = transition_decision(
                source,
                target,
                disposition=disposition,
                admin_clearance=source == ConnectionState.BLOCKED_BY_ADMIN,
            )
            assert decision.secret_use in {'none', 'read_refresh', 'revoke_only'}
    for terminal in TERMINAL_STATES:
        assert not ALLOWED_TRANSITIONS[terminal]
        with pytest.raises(ValueError):
            transition_decision(terminal, ConnectionState.ACTIVE)


def test_revocation_policy_deadlines_and_backoff_are_encoded():
    assert DISCONNECT_RETENTION_DEADLINE == timedelta(days=7)
    assert ACCOUNT_DELETION_REVOKE_DEADLINE == timedelta(hours=24)
    assert [revocation_retry_delay(i) for i in range(1, 7)] == [
        timedelta(minutes=1),
        timedelta(minutes=5),
        timedelta(minutes=30),
        timedelta(hours=2),
        timedelta(hours=6),
        timedelta(hours=6),
    ]


def test_revoke_and_delete_fence_generation_and_limit_secret_use():
    for target in (ConnectionState.REVOKE_PENDING, ConnectionState.DELETION_PENDING):
        decision = transition_decision(ConnectionState.ACTIVE, target)
        assert decision.increments_generation
        assert decision.secret_use == 'revoke_only'


def test_reconnect_and_terminal_disposition_guards_are_executable():
    with pytest.raises(ValueError, match='terminal disposition'):
        transition_decision(ConnectionState.REAUTH_REQUIRED, ConnectionState.PENDING_CONSENT)
    with pytest.raises(ValueError, match='independent clearance'):
        transition_decision(
            ConnectionState.BLOCKED_BY_ADMIN,
            ConnectionState.PENDING_CONSENT,
            disposition=RevocationDisposition.PROVIDER_ALREADY_INVALID,
        )
    with pytest.raises(ValueError, match='terminal disposition'):
        transition_decision(ConnectionState.REVOKE_PENDING, ConnectionState.REVOKED)
    with pytest.raises(ValueError, match='allowed terminal'):
        transition_decision(
            ConnectionState.ACTIVE,
            ConnectionState.REVOKED,
            disposition=RevocationDisposition.SECURITY_APPROVED_DECOMMISSION,
        )


def test_deletion_retry_does_not_advance_generation():
    decision = transition_decision(ConnectionState.DELETION_PENDING, ConnectionState.DELETION_PENDING)
    assert not decision.increments_generation
