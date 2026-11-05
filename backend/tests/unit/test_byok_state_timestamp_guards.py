"""Regression tests for BYOK state timestamp coercion and null state/fingerprint guards."""

import hashlib
import types
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from unittest.mock import MagicMock, patch

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _raw_and_fp(raw: str = 'sk-live-key') -> tuple[str, str]:
    return raw, hashlib.sha256(raw.encode()).hexdigest()


@lru_cache(maxsize=1)
def _load_users_db():
    fakes = {
        'database._client': AutoMockModule('database._client'),
        'database.redis_db': AutoMockModule('database.redis_db'),
        'database.firestore_cache': AutoMockModule('database.firestore_cache'),
        'database.firestore_read_metrics': AutoMockModule('database.firestore_read_metrics'),
        'database.fsr_read_cache': AutoMockModule('database.fsr_read_cache'),
        'database.user_document_cache': AutoMockModule('database.user_document_cache'),
        'database.speaker_profile_authority': AutoMockModule('database.speaker_profile_authority'),
        'firebase_admin': AutoMockModule('firebase_admin'),
        'firebase_admin.auth': AutoMockModule('firebase_admin.auth'),
        'google.cloud.firestore': AutoMockModule('google.cloud.firestore'),
        'google.cloud.firestore_v1': AutoMockModule('google.cloud.firestore_v1'),
        'google.cloud.firestore_v1.base_query': AutoMockModule('google.cloud.firestore_v1.base_query'),
        'utils.other.storage': AutoMockModule('utils.other.storage'),
        'utils.encryption': AutoMockModule('utils.encryption'),
    }
    with stub_modules(fakes):
        return load_module_fresh('database.users', str(BACKEND_DIR / 'database' / 'users.py'))


def _database_users_stub(state_fn=None) -> types.ModuleType:
    stub = types.ModuleType('database.users')
    stub.BYOK_HEARTBEAT_TTL_SECONDS = 7 * 24 * 60 * 60
    if state_fn is not None:
        stub.get_byok_state = state_fn
    return stub


def test_is_byok_active_accepts_naive_and_iso_last_seen_at():
    users_db = _load_users_db()

    naive_recent = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=30)
    with patch.object(users_db, 'get_byok_state', return_value={'active': True, 'last_seen_at': naive_recent}):
        assert users_db.is_byok_active('uid-naive') is True

    iso_recent = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat().replace('+00:00', 'Z')
    with patch.object(users_db, 'get_byok_state', return_value={'active': True, 'last_seen_at': iso_recent}):
        assert users_db.is_byok_active('uid-iso') is True

    naive_expired = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        seconds=users_db.BYOK_HEARTBEAT_TTL_SECONDS + 60
    )
    with patch.object(users_db, 'get_byok_state', return_value={'active': True, 'last_seen_at': naive_expired}):
        assert users_db.is_byok_active('uid-expired') is False


def test_get_byok_state_and_is_byok_active_handle_explicit_null_byok_field():
    users_db = _load_users_db()

    fake_snapshot = MagicMock()
    fake_snapshot.to_dict.return_value = {'byok': None}
    with (
        patch.object(users_db, 'user_snapshot', return_value=fake_snapshot),
        patch.object(users_db, 'memo', side_effect=lambda uid, key, fn: fn()),
        patch.object(users_db, 'cached_read', side_effect=lambda cache_name, uid, key, fetch, **kw: fetch()),
    ):
        state = users_db.get_byok_state('uid-null-byok', firestore_client=MagicMock())
        assert state == {}
        assert users_db.is_byok_active('uid-null-byok', firestore_client=MagicMock()) is False


def test_validated_byok_keys_handles_naive_and_iso_last_seen_at(monkeypatch):
    monkeypatch.delenv('BYOK_FINGERPRINT_PEPPER', raising=False)
    byok = load_module_fresh('utils.byok', str(BACKEND_DIR / 'utils' / 'byok.py'))

    raw_key, fp = _raw_and_fp('sk-openai-test')
    naive_recent = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=15)
    state_naive = {
        'active': True,
        'last_seen_at': naive_recent,
        'fingerprints': {'openai': fp},
    }
    with (
        stub_modules({'database.users': _database_users_stub()}),
        patch.object(byok, 'get_cached_byok_state', return_value=state_naive),
    ):
        validated, err = byok._validated_byok_keys('uid-1', {'openai': raw_key})
        assert err is None
        assert validated == {'openai': raw_key}

    iso_recent = (datetime.now(timezone.utc) - timedelta(seconds=15)).isoformat().replace('+00:00', 'Z')
    state_iso = {
        'active': True,
        'last_seen_at': iso_recent,
        'fingerprints': {'openai': fp},
    }
    with (
        stub_modules({'database.users': _database_users_stub()}),
        patch.object(byok, 'get_cached_byok_state', return_value=state_iso),
    ):
        validated, err = byok._validated_byok_keys('uid-2', {'openai': raw_key})
        assert err is None
        assert validated == {'openai': raw_key}


def test_validated_byok_keys_guards_null_state_and_null_fingerprints(monkeypatch):
    monkeypatch.delenv('BYOK_FINGERPRINT_PEPPER', raising=False)
    byok = load_module_fresh('utils.byok', str(BACKEND_DIR / 'utils' / 'byok.py'))
    raw_key, _ = _raw_and_fp('sk-openai-test')

    with (
        stub_modules({'database.users': _database_users_stub(state_fn=lambda uid: None)}),
    ):
        assert byok.get_cached_byok_state('uid-cached-none') == {}

    with (
        stub_modules({'database.users': _database_users_stub()}),
        patch.object(byok, 'get_cached_byok_state', return_value=None),
    ):
        validated, err = byok._validated_byok_keys('uid-none', {'openai': raw_key})
        assert err is None
        assert validated == {}

    recent = datetime.now(timezone.utc) - timedelta(seconds=10)
    with (
        stub_modules({'database.users': _database_users_stub()}),
        patch.object(
            byok,
            'get_cached_byok_state',
            return_value={'active': True, 'last_seen_at': recent, 'fingerprints': None},
        ),
    ):
        validated, err = byok._validated_byok_keys('uid-null-fps', {'openai': raw_key})
        assert err is None
        assert validated == {}

    with (
        stub_modules({'database.users': _database_users_stub()}),
        patch.object(
            byok,
            'get_cached_byok_state',
            return_value={'active': True, 'last_seen_at': recent, 'fingerprints': {'openai': None}},
        ),
    ):
        validated, err = byok._validated_byok_keys('uid-null-provider-fp', {'openai': raw_key})
        assert validated == {}
        assert err == 'BYOK key fingerprint mismatch for provider: openai'
