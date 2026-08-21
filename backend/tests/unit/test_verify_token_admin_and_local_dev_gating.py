"""Tests for utils.other.endpoints.verify_token's two opt-in/opt-out gates
added in the post-disclosure hardening pass:

- ADMIN_KEY_AUTH_ENABLED=false disables the ADMIN_KEY impersonation path
  entirely, even when ADMIN_KEY is set and the token matches it. Defaults to
  "true" so this repo's own integration tests, test stacks, and the
  production memory-continuity gauntlet (all of which rely on the
  `Bearer <ADMIN_KEY><uid>` format) keep working unchanged.
- LOCAL_DEVELOPMENT=true only falls back to uid '123' on an invalid Firebase
  token when no real Firebase credential (SERVICE_ACCOUNT_JSON /
  GOOGLE_APPLICATION_CREDENTIALS / FIREBASE_AUTH_CREDENTIALS_PATH) is configured -- so a misconfigured prod
  deployment that accidentally sets LOCAL_DEVELOPMENT=true can't silently
  grant unauthenticated access.

Isolation: utils.other.endpoints transitively imports firebase_admin.auth and
several database.* modules that construct clients / require a Firebase app at
import time. Follows the same stub_modules pattern as
test_ws_auth_handshake.py (see backend/docs/test_isolation.md, DECISIONS D2).
"""

import importlib
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import stub_modules
from utils.auth.errors import InvalidToken  # neutral taxonomy (ADR-0034) verify_token now raises

BACKEND_DIR = Path(__file__).resolve().parents[2]


class InvalidIdTokenError(Exception):
    pass


# Populated by the module-scoped autouse fixture below.
verify_token = None
# The MODULE OBJECT the fixture imported, not a fresh `import utils.other.endpoints` — that would build a
# different object outside `stub_modules`, and monkeypatching it would patch nothing the code under test
# can see.
endpoints_module = None


def _build_fakes():
    database_pkg = types.ModuleType("database")
    database_pkg.__path__ = [str(BACKEND_DIR / "database")]
    utils_pkg = types.ModuleType("utils")
    utils_pkg.__path__ = [str(BACKEND_DIR / "utils")]
    utils_other_pkg = types.ModuleType("utils.other")
    utils_other_pkg.__path__ = [str(BACKEND_DIR / "utils" / "other")]

    firebase_admin_stub = types.ModuleType("firebase_admin")
    firebase_auth_stub = types.ModuleType("firebase_admin.auth")
    firebase_admin_stub.auth = firebase_auth_stub
    for name in ("CertificateFetchError", "ExpiredIdTokenError", "RevokedIdTokenError"):
        setattr(firebase_auth_stub, name, type(name, (Exception,), {}))
    firebase_auth_stub.InvalidIdTokenError = InvalidIdTokenError
    # Every test here exercises the invalid-token fallback paths (ADMIN_KEY or
    # LOCAL_DEVELOPMENT), so an always-invalid token is the right default.
    firebase_auth_stub.verify_id_token = MagicMock(side_effect=InvalidIdTokenError("Invalid token"))
    firebase_auth_stub.get_user = MagicMock()

    database_client_stub = types.ModuleType("database._client")
    database_client_stub.db = MagicMock()
    database_client_stub.document_id_from_seed = MagicMock(return_value="doc-id")

    database_redis_stub = types.ModuleType("database.redis_db")
    database_redis_stub.check_rate_limit = MagicMock(return_value=True)
    database_redis_stub.try_acquire_listen_lock = MagicMock(return_value=True)
    database_redis_stub.try_acquire_user_platform_write_lock = MagicMock(return_value=True)

    users_stub = types.ModuleType("database.users")
    users_stub.record_user_platform = MagicMock()
    users_stub.record_client_device = MagicMock()

    fakes = {
        "database": database_pkg,
        "utils": utils_pkg,
        "utils.other": utils_other_pkg,
        "firebase_admin": firebase_admin_stub,
        "firebase_admin.auth": firebase_auth_stub,
        "database._client": database_client_stub,
        "database.redis_db": database_redis_stub,
        "database.users": users_stub,
        "utils.executors": None,
        "utils.other.endpoints": None,
    }
    return fakes


@pytest.fixture(scope="module", autouse=True)
def _endpoints_isolation():
    with stub_modules(_build_fakes()):
        endpoints = importlib.import_module("utils.other.endpoints")
        mod = sys.modules[__name__]
        mod.verify_token = endpoints.verify_token
        mod.endpoints_module = endpoints
        yield


ADMIN_KEY = 'a-sufficiently-long-admin-key-value'


def _clear_admin_env(monkeypatch):
    monkeypatch.delenv('ADMIN_KEY', raising=False)
    monkeypatch.delenv('ADMIN_KEY_AUTH_ENABLED', raising=False)


def _clear_local_dev_env(monkeypatch):
    monkeypatch.delenv('LOCAL_DEVELOPMENT', raising=False)
    monkeypatch.delenv('SERVICE_ACCOUNT_JSON', raising=False)
    monkeypatch.delenv('GOOGLE_APPLICATION_CREDENTIALS', raising=False)
    monkeypatch.delenv('FIREBASE_AUTH_CREDENTIALS_PATH', raising=False)
    # Cleared too, so a test that does not set it exercises the DEFAULT backend (firebase) rather than
    # whatever leaked in from another test — the bypass is gated on the backend as well (BACKLOG L14).
    monkeypatch.delenv('AUTH_BACKEND', raising=False)


# ---------------------------------------------------------------------------
# ADMIN_KEY_AUTH_ENABLED gating
# ---------------------------------------------------------------------------


def test_admin_key_path_disabled_when_flag_is_false(monkeypatch):
    _clear_admin_env(monkeypatch)
    _clear_local_dev_env(monkeypatch)
    monkeypatch.setenv('ADMIN_KEY', ADMIN_KEY)
    monkeypatch.setenv('ADMIN_KEY_AUTH_ENABLED', 'false')

    token = ADMIN_KEY + 'target-uid'  # would impersonate 'target-uid' if the gate were open
    with pytest.raises(InvalidToken):
        verify_token(token)


def test_admin_key_path_enabled_when_flag_is_true(monkeypatch):
    _clear_admin_env(monkeypatch)
    monkeypatch.setenv('ADMIN_KEY', ADMIN_KEY)
    monkeypatch.setenv('ADMIN_KEY_AUTH_ENABLED', 'true')

    assert verify_token(ADMIN_KEY + 'target-uid') == 'target-uid'


def test_admin_key_path_defaults_to_enabled_when_flag_is_unset(monkeypatch):
    """Backward compatibility: existing deployments/CI that set ADMIN_KEY but
    have never heard of ADMIN_KEY_AUTH_ENABLED must keep working."""
    _clear_admin_env(monkeypatch)
    monkeypatch.setenv('ADMIN_KEY', ADMIN_KEY)

    assert verify_token(ADMIN_KEY + 'another-uid') == 'another-uid'


def test_non_matching_token_falls_through_to_firebase_even_when_enabled(monkeypatch):
    _clear_admin_env(monkeypatch)
    _clear_local_dev_env(monkeypatch)
    monkeypatch.setenv('ADMIN_KEY', ADMIN_KEY)
    monkeypatch.setenv('ADMIN_KEY_AUTH_ENABLED', 'true')

    with pytest.raises(InvalidToken):
        verify_token('a-token-that-does-not-start-with-the-admin-key')


# ---------------------------------------------------------------------------
# LOCAL_DEVELOPMENT gating
# ---------------------------------------------------------------------------


def test_local_development_returns_uid_123_without_real_credentials(monkeypatch):
    _clear_admin_env(monkeypatch)
    _clear_local_dev_env(monkeypatch)
    monkeypatch.setenv('LOCAL_DEVELOPMENT', 'true')

    assert verify_token('any-invalid-token') == '123'


def test_local_development_inert_when_service_account_json_is_set(monkeypatch):
    _clear_admin_env(monkeypatch)
    _clear_local_dev_env(monkeypatch)
    monkeypatch.setenv('LOCAL_DEVELOPMENT', 'true')
    monkeypatch.setenv('SERVICE_ACCOUNT_JSON', '{"type": "service_account"}')

    with pytest.raises(InvalidToken):
        verify_token('any-invalid-token')


def test_local_development_inert_when_google_application_credentials_is_set(monkeypatch):
    _clear_admin_env(monkeypatch)
    _clear_local_dev_env(monkeypatch)
    monkeypatch.setenv('LOCAL_DEVELOPMENT', 'true')
    monkeypatch.setenv('GOOGLE_APPLICATION_CREDENTIALS', '/tmp/fake-service-account.json')

    with pytest.raises(InvalidToken):
        verify_token('any-invalid-token')


def test_local_development_inert_when_firebase_auth_credentials_path_is_set(monkeypatch):
    _clear_admin_env(monkeypatch)
    _clear_local_dev_env(monkeypatch)
    monkeypatch.setenv('LOCAL_DEVELOPMENT', 'true')
    monkeypatch.setenv('FIREBASE_AUTH_CREDENTIALS_PATH', '/tmp/firebase-auth.json')

    with pytest.raises(InvalidToken):
        verify_token('any-invalid-token')


def test_local_development_flag_off_raises_regardless_of_credentials(monkeypatch):
    _clear_admin_env(monkeypatch)
    _clear_local_dev_env(monkeypatch)

    with pytest.raises(InvalidToken):
        verify_token('any-invalid-token')


# ---------------------------------------------------------------------------
# AUTH_BACKEND gating — the conjunct nothing was testing (BACKLOG L14)
# ---------------------------------------------------------------------------


def test_the_bypass_is_inert_on_an_oidc_backend(monkeypatch):
    """The one fail-open in the auth chain, and `auth_backend_name() == 'firebase'` is all that keeps it
    off an on-prem OIDC deployment that also sets LOCAL_DEVELOPMENT=true.

    Measured before this test existed: deleting that conjunct left the ENTIRE suite green — a full sweep
    of 984 files reported only the 4-5 known baseline failures. An OIDC deployment never has a Firebase
    credential, so `no_real_credential` is always true there: without the backend gate, every invalid
    token would have been granted uid '123'.
    """
    _clear_admin_env(monkeypatch)
    _clear_local_dev_env(monkeypatch)
    monkeypatch.setenv('LOCAL_DEVELOPMENT', 'true')
    monkeypatch.setenv('AUTH_BACKEND', 'oidc')

    with pytest.raises(InvalidToken):
        verify_token('any-invalid-token')


def test_the_bypass_still_works_on_the_default_backend(monkeypatch):
    """The legacy principal: unset AUTH_BACKEND means firebase, which is every existing dev harness."""
    _clear_admin_env(monkeypatch)
    _clear_local_dev_env(monkeypatch)
    monkeypatch.setenv('LOCAL_DEVELOPMENT', 'true')

    assert verify_token('any-invalid-token') == '123'


def test_the_bypass_works_when_firebase_is_declared_explicitly(monkeypatch):
    _clear_admin_env(monkeypatch)
    _clear_local_dev_env(monkeypatch)
    monkeypatch.setenv('LOCAL_DEVELOPMENT', 'true')
    monkeypatch.setenv('AUTH_BACKEND', 'firebase')

    assert verify_token('any-invalid-token') == '123'


def test_a_misspelled_backend_does_not_open_the_bypass(monkeypatch):
    """A typo must not be a way to turn the bypass on.

    It cannot be: `auth_backend_name()` refuses an unknown value with a ValueError instead of coercing to
    firebase (fail-closed, ADR-0034), and `get_auth_provider()` raises the same thing before the except
    branch is even reached. So the outcome is a loud configuration error, NOT a granted uid — which is
    what this pins. (That it surfaces as a 500 rather than a 401 is a separate, deliberate loudness.)
    """
    _clear_admin_env(monkeypatch)
    _clear_local_dev_env(monkeypatch)
    monkeypatch.setenv('LOCAL_DEVELOPMENT', 'true')
    monkeypatch.setenv('AUTH_BACKEND', 'oidcc')

    with pytest.raises(ValueError, match='Unknown AUTH_BACKEND'):
        verify_token('any-invalid-token')


def test_the_bypass_records_a_fallback(monkeypatch):
    """AGENTS.md requires a fail-open branch to call record_fallback. This one did not, so a deployment
    granting uid '123' to every invalid token left no trace beyond whatever the caller logged."""
    _clear_admin_env(monkeypatch)
    _clear_local_dev_env(monkeypatch)
    monkeypatch.setenv('LOCAL_DEVELOPMENT', 'true')
    events: list[dict] = []
    monkeypatch.setattr(endpoints_module, 'record_fallback', lambda **kw: events.append(kw))

    assert verify_token('any-invalid-token') == '123'

    assert len(events) == 1
    assert events[0]['component'] == 'auth'
    assert events[0]['to_mode'] == 'dev_uid_123'
    assert events[0]['reason'] == 'policy'
    assert events[0]['outcome'] == 'degraded'


def test_a_rejected_token_records_nothing(monkeypatch):
    """Only the fail-open is a fallback; an ordinary rejection is the system working."""
    _clear_admin_env(monkeypatch)
    _clear_local_dev_env(monkeypatch)
    monkeypatch.setenv('LOCAL_DEVELOPMENT', 'true')
    monkeypatch.setenv('AUTH_BACKEND', 'oidc')
    events: list[dict] = []
    monkeypatch.setattr(endpoints_module, 'record_fallback', lambda **kw: events.append(kw))

    with pytest.raises(InvalidToken):
        verify_token('any-invalid-token')

    assert events == []
