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
    for name in ("CertificateFetchError", "ExpiredIdTokenError", "UserNotFoundError"):
        setattr(firebase_auth_stub, name, type(name, (Exception,), {}))
    firebase_auth_stub.InvalidIdTokenError = InvalidIdTokenError
    # Mirrors the real hierarchy: RevokedIdTokenError subclasses
    # InvalidIdTokenError, which is why verify_token must raise it outside the
    # LOCAL_DEVELOPMENT fallback's except block.
    firebase_auth_stub.RevokedIdTokenError = type("RevokedIdTokenError", (InvalidIdTokenError,), {})
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
    database_redis_stub.FIREBASE_TOKEN_WATERMARK_TTL_SECONDS = 60
    database_redis_stub.cache_firebase_token_watermark = MagicMock()
    database_redis_stub.get_cached_firebase_token_watermark = MagicMock(return_value=None)
    database_redis_stub.delete_cached_firebase_token_watermark = MagicMock()

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


# ---------------------------------------------------------------------------
# Token revocation enforcement
#
# verify_id_token() alone never observes revocation, so before this a token
# stolen ahead of an account deletion or password change stayed valid until its
# own `exp`. RevokedIdTokenError is also what makes the WebSocket 4004
# "re-login required" close code reachable at all.
# ---------------------------------------------------------------------------


def _valid_token_env(monkeypatch, *, uid='live-uid', iat=2000):
    _clear_admin_env(monkeypatch)
    _clear_local_dev_env(monkeypatch)
    monkeypatch.delenv('FIREBASE_TOKEN_REVOCATION_CHECK_ENABLED', raising=False)
    auth_stub = sys.modules['firebase_admin.auth']
    auth_stub.verify_id_token = MagicMock(return_value={'uid': uid, 'iat': iat})
    redis_stub = sys.modules['database.redis_db']
    redis_stub.get_cached_firebase_token_watermark = MagicMock(return_value=None)
    redis_stub.cache_firebase_token_watermark = MagicMock()
    return auth_stub, redis_stub


def _fake_firebase_user(*, disabled=False, valid_after_ms=0):
    user = MagicMock()
    user.disabled = disabled
    user.tokens_valid_after_timestamp = valid_after_ms
    return user


def test_live_user_with_fresh_token_is_accepted(monkeypatch):
    auth_stub, _ = _valid_token_env(monkeypatch)
    auth_stub.get_user = MagicMock(return_value=_fake_firebase_user(valid_after_ms=1000 * 1000))

    assert verify_token('a-real-token') == 'live-uid'


def test_token_issued_before_revocation_watermark_is_rejected(monkeypatch):
    auth_stub, _ = _valid_token_env(monkeypatch, iat=1000)
    # revoke_refresh_tokens() moves the watermark past the token's iat.
    auth_stub.get_user = MagicMock(return_value=_fake_firebase_user(valid_after_ms=5000 * 1000))

    with pytest.raises(auth_stub.RevokedIdTokenError):
        verify_token('a-stolen-token')


def test_deleted_account_token_is_rejected(monkeypatch):
    auth_stub, _ = _valid_token_env(monkeypatch)
    auth_stub.get_user = MagicMock(side_effect=auth_stub.UserNotFoundError('gone'))

    with pytest.raises(auth_stub.RevokedIdTokenError):
        verify_token('a-token-for-a-deleted-account')


def test_disabled_account_token_is_rejected(monkeypatch):
    auth_stub, _ = _valid_token_env(monkeypatch)
    auth_stub.get_user = MagicMock(return_value=_fake_firebase_user(disabled=True))

    with pytest.raises(auth_stub.RevokedIdTokenError):
        verify_token('a-token-for-a-disabled-account')


def test_revocation_check_fails_open_when_firebase_is_unreachable(monkeypatch):
    """A Firebase outage must not log every user out."""
    auth_stub, redis_stub = _valid_token_env(monkeypatch)
    auth_stub.get_user = MagicMock(side_effect=RuntimeError('firebase unreachable'))

    assert verify_token('a-real-token') == 'live-uid'
    redis_stub.cache_firebase_token_watermark.assert_not_called()


def test_cached_watermark_avoids_the_firebase_lookup(monkeypatch):
    auth_stub, redis_stub = _valid_token_env(monkeypatch, iat=1000)
    redis_stub.get_cached_firebase_token_watermark = MagicMock(
        return_value={'exists': True, 'disabled': False, 'valid_after_ms': 5000 * 1000}
    )
    auth_stub.get_user = MagicMock()

    with pytest.raises(auth_stub.RevokedIdTokenError):
        verify_token('a-stolen-token')
    auth_stub.get_user.assert_not_called()


def test_revocation_check_can_be_disabled_by_env_flag(monkeypatch):
    auth_stub, _ = _valid_token_env(monkeypatch, iat=1000)
    monkeypatch.setenv('FIREBASE_TOKEN_REVOCATION_CHECK_ENABLED', 'false')
    auth_stub.get_user = MagicMock(side_effect=AssertionError('must not be consulted when disabled'))

    assert verify_token('a-stolen-token') == 'live-uid'


def test_admin_key_impersonation_skips_the_revocation_check(monkeypatch):
    """The ADMIN_KEY path returns before Firebase is ever consulted."""
    auth_stub, _ = _valid_token_env(monkeypatch)
    monkeypatch.setenv('ADMIN_KEY', ADMIN_KEY)
    monkeypatch.setenv('ADMIN_KEY_AUTH_ENABLED', 'true')
    auth_stub.get_user = MagicMock(side_effect=AssertionError('must not be consulted'))

    assert verify_token(ADMIN_KEY + 'target-uid') == 'target-uid'


# ---------------------------------------------------------------------------
# ADMIN_KEY strength gate at startup
# ---------------------------------------------------------------------------


def _clear_stage_env(monkeypatch):
    _clear_admin_env(monkeypatch)
    monkeypatch.delenv('OMI_ENV_STAGE', raising=False)


def test_startup_rejects_weak_admin_key_when_impersonation_is_enabled(monkeypatch):
    _clear_stage_env(monkeypatch)
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('ADMIN_KEY', 'short-key')

    with pytest.raises(RuntimeError):
        endpoints_module.validate_admin_key_auth_configuration()


def test_startup_allows_weak_admin_key_when_impersonation_is_disabled(monkeypatch):
    _clear_stage_env(monkeypatch)
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('ADMIN_KEY', 'short-key')
    monkeypatch.setenv('ADMIN_KEY_AUTH_ENABLED', 'false')

    endpoints_module.validate_admin_key_auth_configuration()


def test_startup_allows_strong_admin_key_with_impersonation_enabled(monkeypatch):
    _clear_stage_env(monkeypatch)
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('ADMIN_KEY', 'x' * 32)

    endpoints_module.validate_admin_key_auth_configuration()


def test_startup_gate_is_inert_for_local_and_test_stages(monkeypatch):
    """Local harnesses and CI deliberately use short, well-known ADMIN_KEYs."""
    _clear_stage_env(monkeypatch)
    monkeypatch.setenv('ADMIN_KEY', 'short-key')

    endpoints_module.validate_admin_key_auth_configuration()
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    endpoints_module.validate_admin_key_auth_configuration()
