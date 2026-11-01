from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest

from database.live_language_profile import (
    MAX_CODES,
    MAX_COUNT,
    MAX_SESSIONS,
    _clean_counts,
    _clean_sessions,
    append_live_language_session,
    get_live_language_sessions,
)


class FakeRedis:
    def __init__(self):
        self.store = {}
        self.get_calls = 0
        self.set_calls = 0
        self.delete_calls = 0

    def get(self, key):
        self.get_calls += 1
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.set_calls += 1
        self.store[key] = value
        return True

    def delete(self, key):
        self.delete_calls += 1
        self.store.pop(key, None)
        return 1


def test_clean_counts_case_normalization_and_whitespace():
    """Verify uppercase codes and whitespace are normalized to lowercase ISO-639 tags."""
    result = _clean_counts({'EN': 3, '  es  ': 5, 'FR': 2})
    assert result == {'es': 5, 'en': 3, 'fr': 2}


def test_clean_counts_duplicate_aggregation_and_max_clamp():
    """Verify duplicate case variations are aggregated and clamped to MAX_COUNT."""
    result = _clean_counts({'en': 6000, 'EN': 6000})
    assert result == {'en': MAX_COUNT}


def test_clean_counts_rejects_invalids():
    """Verify invalid types, booleans, negative counts, and invalid tags are dropped."""
    assert _clean_counts(None) == {}
    assert _clean_counts('not a dict') == {}
    assert _clean_counts({'': 5, 'toolongcode': 2, 'e': 1, '12': 4}) == {}
    assert _clean_counts({'en': -5, 'fr': 0, 'de': True, 'es': 2.5}) == {}


def test_clean_counts_limits_max_codes():
    """Verify output is bounded to MAX_CODES highest-frequency tags."""
    sample = {
        f'{c1}{c2}': i + 1
        for i, (c1, c2) in enumerate(zip('abcdefghijklmnopqrstuvwxy', 'bcdefghijklmnopqrstuvwxyz'))
    }
    result = _clean_counts(sample)
    assert len(result) == MAX_CODES


def test_clean_sessions_bounds_and_cleans():
    """Verify _clean_sessions filters malformed elements and clamps to MAX_SESSIONS."""
    assert _clean_sessions(None) == []
    assert _clean_sessions('invalid') == []

    sessions = [{'en': 1}] * (MAX_SESSIONS + 10)
    cleaned = _clean_sessions(sessions)
    assert len(cleaned) == MAX_SESSIONS


def test_get_live_language_sessions_invalid_uid_short_circuit():
    """Verify get_live_language_sessions returns empty list for empty/whitespace uid."""
    assert get_live_language_sessions('') == []
    assert get_live_language_sessions('   ') == []
    assert get_live_language_sessions(None) == []  # type: ignore[arg-type]


def test_get_live_language_sessions_re_raises_on_firestore_error(caplog):
    """Verify get_live_language_sessions logs a warning and re-raises on Firestore read errors."""
    client = SimpleNamespace(
        collection=lambda *_: SimpleNamespace(
            document=lambda *_: SimpleNamespace(get=lambda *_: (_ for _ in ()).throw(RuntimeError('Firestore down')))
        )
    )
    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError, match='Firestore down'):
            get_live_language_sessions('user123', firestore_client=client)

    assert any("Failed to fetch live language sessions for user user123: Firestore down" in rec.message for rec in caplog.records)


def test_get_live_language_sessions_cached_path_does_not_cache_on_error(monkeypatch, caplog):
    """Verify that on the cached production path (firestore_client=None), fetch errors propagate and do not pollute Redis."""
    from database import firestore_cache as fc
    from database import live_language_profile as llp

    fake_redis = FakeRedis()
    monkeypatch.setattr(fc, 'r', fake_redis)
    monkeypatch.setenv('FIRESTORE_CACHE_ENABLED', 'true')

    failing_client = SimpleNamespace(
        collection=lambda *_: SimpleNamespace(
            document=lambda *_: SimpleNamespace(
                get=lambda *_: (_ for _ in ()).throw(RuntimeError('Firestore transient outage'))
            )
        )
    )
    monkeypatch.setattr(llp, 'get_data_plane_firestore_client', lambda: failing_client)

    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError, match='Firestore transient outage'):
            get_live_language_sessions('user_cached_123')

    # Verify error was logged and nothing was written into Redis cache
    assert any("Failed to fetch live language sessions for user user_cached_123: Firestore transient outage" in rec.message for rec in caplog.records)
    assert fake_redis.set_calls == 0
    assert fake_redis.store == {}


def test_get_live_language_sessions_handles_missing_doc():
    """Verify get_live_language_sessions returns empty list when user document doesn't exist."""
    snapshot = SimpleNamespace(exists=False, to_dict=lambda: None)
    client = SimpleNamespace(
        collection=lambda *_: SimpleNamespace(document=lambda *_: SimpleNamespace(get=lambda *_: snapshot))
    )
    assert get_live_language_sessions('user123', firestore_client=client) == []


def test_append_live_language_session_invalid_input_short_circuits():
    """Verify append_live_language_session fails fast on invalid uid or empty counts."""
    assert not append_live_language_session('', {'en': 1})
    assert not append_live_language_session('   ', {'en': 1})
    assert not append_live_language_session('user1', {})
    assert not append_live_language_session('user1', {'invalid_long': 1})


def test_append_live_language_session_handles_transaction_exception(caplog):
    """Verify append_live_language_session catches transaction errors safely and logs a warning."""
    mock_txn = MagicMock()
    mock_txn._read_only = False
    client = SimpleNamespace(
        transaction=lambda: mock_txn,
        collection=lambda *_: SimpleNamespace(
            document=lambda *_: SimpleNamespace(
                get=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('Conflict on commit'))
            )
        ),
    )
    with caplog.at_level(logging.WARNING):
        assert not append_live_language_session('user1', {'en': 1}, firestore_client=client)

    assert any("Failed to append live language session for user user1: Conflict on commit" in rec.message for rec in caplog.records)

def test_append_live_language_session_successful_invalidation():
    """Verify cache is invalidated on successful append without custom firestore client."""
    with (
        patch('database.live_language_profile.get_data_plane_firestore_client') as mock_client_factory,
        patch('database.live_language_profile._append_transaction', return_value=True),
        patch('database.live_language_profile.invalidate') as mock_invalidate,
    ):
        mock_client = MagicMock()
        mock_client_factory.return_value = mock_client
        assert append_live_language_session('user_valid', {'en': 2})
        mock_invalidate.assert_called_once()

