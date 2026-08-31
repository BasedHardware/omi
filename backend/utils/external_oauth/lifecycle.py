"""Executable external-connection lifecycle and retry policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Mapping

from utils.external_oauth.contracts import ConnectionState, RevocationDisposition

DISCONNECT_RETENTION_DEADLINE = timedelta(days=7)
ACCOUNT_DELETION_REVOKE_DEADLINE = timedelta(hours=24)
REVOCATION_RETRY_DELAYS = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=30),
    timedelta(hours=2),
    timedelta(hours=6),
)
REVOCATION_STEADY_RETRY = timedelta(hours=6)
REVOCATION_ESCALATION_AFTER = timedelta(hours=2)

TERMINAL_STATES = frozenset({ConnectionState.REVOKED, ConnectionState.CANCELLED, ConnectionState.EXPIRED})

ALLOWED_TRANSITIONS: Mapping[ConnectionState, frozenset[ConnectionState]] = {
    ConnectionState.PENDING_CONSENT: frozenset(
        {
            ConnectionState.ACTIVE,
            ConnectionState.CANCELLED,
            ConnectionState.EXPIRED,
            ConnectionState.DELETION_PENDING,
        }
    ),
    ConnectionState.ACTIVE: frozenset(
        {
            ConnectionState.REAUTH_REQUIRED,
            ConnectionState.BLOCKED_BY_ADMIN,
            ConnectionState.REVOKE_PENDING,
            ConnectionState.DELETION_PENDING,
            ConnectionState.REVOKED,
        }
    ),
    ConnectionState.REAUTH_REQUIRED: frozenset(
        {
            ConnectionState.PENDING_CONSENT,
            ConnectionState.BLOCKED_BY_ADMIN,
            ConnectionState.REVOKE_PENDING,
            ConnectionState.DELETION_PENDING,
            ConnectionState.REVOKED,
        }
    ),
    ConnectionState.BLOCKED_BY_ADMIN: frozenset(
        {
            ConnectionState.PENDING_CONSENT,
            ConnectionState.REVOKE_PENDING,
            ConnectionState.DELETION_PENDING,
            ConnectionState.REVOKED,
        }
    ),
    ConnectionState.REVOKE_PENDING: frozenset(
        {ConnectionState.REVOKED, ConnectionState.REVOCATION_FAILED, ConnectionState.DELETION_PENDING}
    ),
    ConnectionState.REVOCATION_FAILED: frozenset({ConnectionState.REVOKE_PENDING, ConnectionState.DELETION_PENDING}),
    ConnectionState.DELETION_PENDING: frozenset({ConnectionState.DELETION_PENDING, ConnectionState.REVOKED}),
    ConnectionState.REVOKED: frozenset(),
    ConnectionState.CANCELLED: frozenset(),
    ConnectionState.EXPIRED: frozenset(),
}


@dataclass(frozen=True)
class TransitionDecision:
    increments_generation: bool
    secret_use: str


def transition_decision(
    source: ConnectionState,
    target: ConnectionState,
    *,
    disposition: RevocationDisposition | None = None,
    admin_clearance: bool = False,
) -> TransitionDecision:
    if target not in ALLOWED_TRANSITIONS[source]:
        raise ValueError(f'illegal external connection transition: {source.value}->{target.value}')

    reconnect_dispositions = {
        RevocationDisposition.PROVIDER_CONFIRMED_REVOKE,
        RevocationDisposition.PROVIDER_ALREADY_INVALID,
    }
    if target == ConnectionState.PENDING_CONSENT:
        if disposition not in reconnect_dispositions:
            raise ValueError('reconnect requires terminal disposition of the old grant')
        if source == ConnectionState.BLOCKED_BY_ADMIN and not admin_clearance:
            raise ValueError('admin-blocked reconnect requires independent clearance')

    if target == ConnectionState.REVOKED:
        permitted = {
            RevocationDisposition.PROVIDER_CONFIRMED_REVOKE,
            RevocationDisposition.PROVIDER_ALREADY_INVALID,
            RevocationDisposition.SECURITY_APPROVED_DECOMMISSION,
        }
        if source in {
            ConnectionState.ACTIVE,
            ConnectionState.REAUTH_REQUIRED,
            ConnectionState.BLOCKED_BY_ADMIN,
        }:
            permitted = {RevocationDisposition.PROVIDER_ALREADY_INVALID}
        elif source == ConnectionState.DELETION_PENDING:
            permitted.add(RevocationDisposition.DELETION_DEADLINE_DESTROYED)
        if disposition not in permitted:
            raise ValueError('revoked transition requires an allowed terminal disposition')

    fences = target in {
        ConnectionState.REAUTH_REQUIRED,
        ConnectionState.BLOCKED_BY_ADMIN,
        ConnectionState.REVOKE_PENDING,
        ConnectionState.DELETION_PENDING,
        ConnectionState.REVOKED,
        ConnectionState.PENDING_CONSENT,
    }
    if source == target == ConnectionState.DELETION_PENDING:
        fences = False
    if source == ConnectionState.REAUTH_REQUIRED and target == ConnectionState.BLOCKED_BY_ADMIN:
        fences = False
    if target == ConnectionState.ACTIVE:
        secret_use = 'read_refresh'
    elif target in {
        ConnectionState.REVOKE_PENDING,
        ConnectionState.REVOCATION_FAILED,
        ConnectionState.DELETION_PENDING,
    }:
        secret_use = 'revoke_only'
    else:
        secret_use = 'none'
    return TransitionDecision(increments_generation=fences, secret_use=secret_use)


def revocation_retry_delay(attempt: int) -> timedelta:
    if attempt < 1:
        raise ValueError('attempt is one-based')
    if attempt <= len(REVOCATION_RETRY_DELAYS):
        return REVOCATION_RETRY_DELAYS[attempt - 1]
    return REVOCATION_STEADY_RETRY
