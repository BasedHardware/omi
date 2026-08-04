"""Tests for the BYOK fingerprint pepper migration (utils/byok.py).

Background: the client only ever computes/sends plain SHA-256(raw_key) --
that's deliberate (the server never sees raw BYOK keys at enrollment). What
this hardening changes is what the *server* persists: instead of storing that
plain SHA-256 fingerprint as-is (rainbow-table attackable if it ever leaks,
e.g. a Firestore export, since API keys have well-known prefixes like sk-,
sk-ant-, AIza), it's wrapped with a server-only HMAC pepper
(BYOK_FINGERPRINT_PEPPER) before being stored or compared. Because the pepper
is read once at import time (`_BYOK_PEPPER = os.getenv(...)`), these tests
reload utils.byok fresh with the env var set/unset as needed, rather than
monkeypatching the environment after import.

Covers what the reviewer asked for:
- Newly stored peppered fingerprints validate.
- Existing legacy plain (unpeppered) fingerprints still validate once
  BYOK_FINGERPRINT_PEPPER is introduced (no forced re-enrollment).
- Mismatches fail in both modes.
"""

import hashlib
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]

RAW_KEY = 'sk-test-0123456789abcdef'
WRONG_KEY = 'sk-completely-different-key'


def _load_byok(monkeypatch, pepper: str | None):
    if pepper is None:
        monkeypatch.delenv('BYOK_FINGERPRINT_PEPPER', raising=False)
    else:
        monkeypatch.setenv('BYOK_FINGERPRINT_PEPPER', pepper)
    return load_module_fresh('utils.byok', str(BACKEND_DIR / 'utils' / 'byok.py'))


def _active_state(fingerprints: dict) -> dict:
    return {
        'active': True,
        'last_seen_at': datetime.now(timezone.utc),
        'fingerprints': fingerprints,
    }


def _client_fingerprint(raw_key: str) -> str:
    """What the client always computes/sends -- plain SHA-256, pepper-agnostic."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _database_users_stub() -> types.ModuleType:
    """_check_byok_validity() does `import database.users as users_db` inline
    and only reads BYOK_HEARTBEAT_TTL_SECONDS off it. The real database.users
    transitively imports firebase_admin/google-cloud-firestore, which this
    hermetic unit-test tier deliberately never needs -- stub just the one
    constant actually used (see backend/docs/test_isolation.md)."""
    stub = types.ModuleType('database.users')
    stub.BYOK_HEARTBEAT_TTL_SECONDS = 7 * 24 * 60 * 60  # matches database/users.py
    return stub


# ---------------------------------------------------------------------------
# peppered_fingerprint() itself
# ---------------------------------------------------------------------------


def test_no_pepper_configured_is_identity(monkeypatch):
    byok = _load_byok(monkeypatch, None)
    fp = _client_fingerprint(RAW_KEY)
    assert byok.peppered_fingerprint(fp) == fp


def test_pepper_configured_changes_the_stored_value(monkeypatch):
    byok = _load_byok(monkeypatch, 'server-only-pepper-secret')
    fp = _client_fingerprint(RAW_KEY)
    peppered = byok.peppered_fingerprint(fp)
    assert peppered != fp
    assert len(peppered) == 64  # still a hex SHA-256-sized digest


def test_pepper_is_deterministic_for_the_same_input(monkeypatch):
    byok = _load_byok(monkeypatch, 'server-only-pepper-secret')
    fp = _client_fingerprint(RAW_KEY)
    assert byok.peppered_fingerprint(fp) == byok.peppered_fingerprint(fp)


def test_different_peppers_produce_different_values(monkeypatch):
    byok_a = _load_byok(monkeypatch, 'pepper-a')
    fp = _client_fingerprint(RAW_KEY)
    peppered_a = byok_a.peppered_fingerprint(fp)

    byok_b = _load_byok(monkeypatch, 'pepper-b')
    peppered_b = byok_b.peppered_fingerprint(fp)

    assert peppered_a != peppered_b


# ---------------------------------------------------------------------------
# _check_byok_validity(): the actual per-request enrollment check
# ---------------------------------------------------------------------------


def test_new_peppered_enrollment_validates(monkeypatch):
    byok = _load_byok(monkeypatch, 'server-only-pepper-secret')
    stored = byok.peppered_fingerprint(_client_fingerprint(RAW_KEY))  # what enrollment would have stored today

    monkeypatch.setattr(byok, 'get_cached_byok_state', lambda uid: _active_state({'openai': stored}))
    byok.set_byok_keys({'openai': RAW_KEY})

    with stub_modules({'database.users': _database_users_stub()}):
        assert byok._check_byok_validity('uid-1') is None


def test_legacy_unpeppered_enrollment_still_validates_after_pepper_introduced(monkeypatch):
    byok = _load_byok(monkeypatch, 'server-only-pepper-secret')
    # Simulates a fingerprint stored back before BYOK_FINGERPRINT_PEPPER
    # existed: plain client SHA-256, never peppered.
    legacy_stored = _client_fingerprint(RAW_KEY)

    monkeypatch.setattr(byok, 'get_cached_byok_state', lambda uid: _active_state({'openai': legacy_stored}))
    byok.set_byok_keys({'openai': RAW_KEY})

    with stub_modules({'database.users': _database_users_stub()}):
        assert byok._check_byok_validity('uid-1') is None, 'legacy plain fingerprints must not be locked out'


def test_mismatched_key_fails_with_pepper_configured(monkeypatch):
    byok = _load_byok(monkeypatch, 'server-only-pepper-secret')
    stored = byok.peppered_fingerprint(_client_fingerprint(RAW_KEY))

    monkeypatch.setattr(byok, 'get_cached_byok_state', lambda uid: _active_state({'openai': stored}))
    byok.set_byok_keys({'openai': WRONG_KEY})

    with stub_modules({'database.users': _database_users_stub()}):
        error = byok._check_byok_validity('uid-1')
    assert error is not None
    assert 'mismatch' in error.lower()


def test_mismatched_key_fails_without_pepper_configured(monkeypatch):
    byok = _load_byok(monkeypatch, None)
    stored = _client_fingerprint(RAW_KEY)

    monkeypatch.setattr(byok, 'get_cached_byok_state', lambda uid: _active_state({'openai': stored}))
    byok.set_byok_keys({'openai': WRONG_KEY})

    with stub_modules({'database.users': _database_users_stub()}):
        error = byok._check_byok_validity('uid-1')
    assert error is not None
    assert 'mismatch' in error.lower()


def test_no_byok_headers_skips_validation_without_touching_state(monkeypatch):
    byok = _load_byok(monkeypatch, 'server-only-pepper-secret')

    def _fail_if_called(uid):
        raise AssertionError('get_cached_byok_state should not be called when no BYOK headers are present')

    monkeypatch.setattr(byok, 'get_cached_byok_state', _fail_if_called)
    byok.set_byok_keys({})

    assert byok._check_byok_validity('uid-1') is None
