"""Tests for utils.other.endpoints.verify_token's two opt-in/opt-out gates
added in the post-disclosure hardening pass:

- ADMIN_KEY_AUTH_ENABLED=false disables the ADMIN_KEY impersonation path
  entirely, even when ADMIN_KEY is set and the token matches it. Defaults to
  "true" so this repo's own integration tests, test stacks, and the
  production memory-continuity gauntlet (all of which rely on the
  `Bearer <ADMIN_KEY><uid>` format) keep working unchanged.
- LOCAL_DEVELOPMENT=true only falls back to uid '123' on an invalid Firebase
  token when no real Firebase credential (SERVICE_ACCOUNT_JSON /
  GOOGLE_APPLICATION_CREDENTIALS) is configured -- so a misconfigured prod
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

BACKEND_DIR = Path(__file__).resolve().parents[2]


class InvalidIdTokenError(Exception):
    pass


# Populated by the module-scoped autouse fixture below.
verify_token = None


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
        yield


ADMIN_KEY = 'a-sufficiently-long-admin-key-value'


def _clear_admin_env(monkeypatch):
    monkeypatch.delenv('ADMIN_KEY', raising=False)
    monkeypatch.delenv('ADMIN_KEY_AUTH_ENABLED', raising=False)


def _clear_local_dev_env(monkeypatch):
    monkeypatch.delenv('LOCAL_DEVELOPMENT', raising=False)
    monkeypatch.delenv('SERVICE_ACCOUNT_JSON', raising=False)
    monkeypatch.delenv('GOOGLE_APPLICATION_CREDENTIALS', raising=False)


# ---------------------------------------------------------------------------
# ADMIN_KEY_AUTH_ENABLED gating
# ---------------------------------------------------------------------------


def test_admin_key_path_disabled_when_flag_is_false(monkeypatch):
    _clear_admin_env(monkeypatch)
    _clear_local_dev_env(monkeypatch)
    monkeypatch.setenv('ADMIN_KEY', ADMIN_KEY)
    monkeypatch.setenv('ADMIN_KEY_AUTH_ENABLED', 'false')

    token = ADMIN_KEY + 'target-uid'  # would impersonate 'target-uid' if the gate were open
    with pytest.raises(InvalidIdTokenError):
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

    with pytest.raises(InvalidIdTokenError):
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

    with pytest.raises(InvalidIdTokenError):
        verify_token('any-invalid-token')


def test_local_development_inert_when_google_application_credentials_is_set(monkeypatch):
    _clear_admin_env(monkeypatch)
    _clear_local_dev_env(monkeypatch)
    monkeypatch.setenv('LOCAL_DEVELOPMENT', 'true')
    monkeypatch.setenv('GOOGLE_APPLICATION_CREDENTIALS', '/tmp/fake-service-account.json')

    with pytest.raises(InvalidIdTokenError):
        verify_token('any-invalid-token')


def test_local_development_flag_off_raises_regardless_of_credentials(monkeypatch):
    _clear_admin_env(monkeypatch)
    _clear_local_dev_env(monkeypatch)

    with pytest.raises(InvalidIdTokenError):
        verify_token('any-invalid-token')
