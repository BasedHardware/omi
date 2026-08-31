"""The auth fake must be able to express what the port promises, or it cannot be adopted (BACKLOG L15).

`tests/auth_fakes.py` is imported by exactly ONE file (the contract suite). Every migrated caller is
instead tested by installing a `firebase_admin.auth` stub — **54 files** do that — so the neutral port is
crossed almost only by the Firebase adapter, and the next OIDC semantic gap reaches production unseen.

Adoption was not only inertia: the fake could not say the things those tests need. `verify_token` ignored
`check_revoked` entirely and could raise nothing but `InvalidToken`, so two real behaviours were
**inexpressible** through it:

  * the migrate-owner proof in `routers/apps.py`, which is the one caller that passes `check_revoked=True`
    — a revoked source token must not be accepted, and a fake that cannot be revoked cannot show that;
  * the WebSocket close-code contract (`map_ws_auth_close`), which routes each error CLASS to a different
    client recovery: 4001 refresh, 4004 re-login, 1008 invalid.

This file is the proof that both are expressible now. It is not the migration of the 54 stub sites — that
is mechanical and separate — it is the thing that has to be true before that migration is worth starting.
"""

from __future__ import annotations

import pytest

from tests.auth_fakes import FakeAuthProvider
from utils.auth import errors
from utils.auth.ports import Principal


def _principal(uid: str = 'u1') -> Principal:
    return Principal(uid=uid, email='u@example.com', email_verified=True, is_anonymous=False, provider='anonymous')


# --- the revocation semantic the port actually has ------------------------------------------------


def test_a_revoked_token_still_verifies_until_you_ask():
    """Not a quirk of the fake — the semantic of a signed JWT. It stays signature-valid after a
    server-side logout, which is why `check_revoked` exists and why the OIDC adapter has to make a
    separate introspection call for it. A fake that raised regardless would teach the wrong lesson."""
    provider = FakeAuthProvider().register('tok', _principal()).register_revoked('tok')

    assert provider.verify_token('tok').uid == 'u1'

    with pytest.raises(errors.RevokedToken):
        provider.verify_token('tok', check_revoked=True)


def test_the_migrate_owner_shape_can_now_be_written():
    """The one caller that passes check_revoked=True (routers/apps.py): a revoked source token must not
    be accepted as proof of the source identity. Before, the fake had no way to be revoked at all."""
    provider = FakeAuthProvider().register('source', _principal('old-uid')).register_revoked('source')

    with pytest.raises(errors.AuthError):
        provider.verify_token('source', check_revoked=True)


def test_a_token_that_was_never_revoked_is_unaffected():
    provider = FakeAuthProvider().register('tok', _principal())

    assert provider.verify_token('tok', check_revoked=True).uid == 'u1'


# --- the rest of the taxonomy ---------------------------------------------------------------------


@pytest.mark.parametrize(
    'register,expected',
    [
        ('register_expired', errors.ExpiredToken),
        ('register_jwks_unavailable', errors.JWKSUnavailable),
    ],
)
def test_each_failure_class_is_registrable(register, expected):
    provider = FakeAuthProvider()
    getattr(provider, register)('tok')

    with pytest.raises(expected):
        provider.verify_token('tok')


def test_an_unknown_token_is_still_invalid():
    """The default, unchanged: nothing registered means the token is not valid."""
    with pytest.raises(errors.InvalidToken):
        FakeAuthProvider().verify_token('never-seen')


def test_an_arbitrary_error_can_be_registered():
    """For the case ADR-0074 just fixed on the OIDC adapter: an unexpected failure maps to a plain
    AuthError, and a caller's handling of THAT has to be testable too."""
    provider = FakeAuthProvider().register_error('tok', errors.AuthError('a bug, not a bad token'))

    with pytest.raises(errors.AuthError) as raised:
        provider.verify_token('tok')
    assert not isinstance(raised.value, errors.InvalidToken)


# --- the WS close-code contract, through the port -------------------------------------------------


@pytest.mark.parametrize(
    'register,expected_code',
    [
        ('register_expired', 4001),  # refresh the token
        ('register_jwks_unavailable', 4001),  # keys unavailable: also transient
        ('register_revoked', 4004),  # re-login
        ('register_error', 1008),  # anything else: the request is invalid
    ],
)
def test_the_close_code_contract_is_expressible_through_the_fake(register, expected_code):
    """Each error class maps to a different client recovery, and the mapping was only ever exercisable by
    constructing the exceptions by hand. Now a test can drive it through the PORT, which is what makes it
    a contract instead of a table."""
    from utils.other.endpoints import map_ws_auth_close

    provider = FakeAuthProvider()
    if register == 'register_error':
        provider.register_error('tok', errors.AuthError('unexpected'))
    else:
        provider.register('tok', _principal())
        getattr(provider, register)('tok')

    with pytest.raises(errors.AuthError) as raised:
        provider.verify_token('tok', check_revoked=True)

    code, _reason = map_ws_auth_close(raised.value)
    assert code == expected_code
