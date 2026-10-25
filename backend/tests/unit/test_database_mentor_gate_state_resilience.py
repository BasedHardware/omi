"""Hermetic resilience unit tests for backend/database/mentor_gate_state.py.

Validates defensive boundaries for uid sanitization, safe TTL clamping,
non-mapping state rejection, Redis exception fall-open behavior, and local mirror eviction.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

import pytest

import database.mentor_gate_state as mentor_state


class FakeRedis:
    def __init__(self):
        self.store: Dict[str, str] = {}
        self.ttls: Dict[str, int] = {}

    def get(self, key: str) -> Optional[str]:
        return self.store.get(key)

    def set(self, key: str, value: str, ex: Optional[int] = None, nx: bool = False) -> bool:
        if nx and key in self.store:
            return False
        self.store[key] = str(value)
        if ex is not None:
            self.ttls[key] = ex
        return True

    def delete(self, key: str) -> None:
        self.store.pop(key, None)
        self.ttls.pop(key, None)


@pytest.fixture(autouse=True)
def clean_local_mirror(monkeypatch):
    """Hermetically isolate local mirror and Redis singleton between tests."""
    fake_redis = FakeRedis()
    import database.redis_db as redis_db

    monkeypatch.setattr(redis_db, 'r', fake_redis)

    with mentor_state._local_lock:
        mentor_state._local.clear()
    yield fake_redis
    with mentor_state._local_lock:
        mentor_state._local.clear()


class TestUidSanitization:
    @pytest.mark.parametrize(
        'bad_uid',
        [
            None,
            '',
            '   ',
            '\t\n',
            123,
            45.67,
            [],
            {},
            object(),
            'a' * 129,
        ],
    )
    def test_clean_uid_rejects_invalid_inputs(self, bad_uid):
        assert mentor_state._clean_uid(bad_uid) is None

    @pytest.mark.parametrize(
        'raw,expected',
        [
            ('user123', 'user123'),
            ('  user_with_spaces  ', 'user_with_spaces'),
            ('\tuser:sub.id\n', 'user:sub.id'),
            ('a' * 128, 'a' * 128),
        ],
    )
    def test_clean_uid_strips_and_preserves_valid(self, raw, expected):
        assert mentor_state._clean_uid(raw) == expected


class TestSafeTtl:
    @pytest.mark.parametrize(
        'bad_ttl,default',
        [
            (0, 30),
            (-1, 30),
            (-999, 90000),
            ('bad', 30),
            (None, 60),
            ([], 30),
            ({}, 30),
        ],
    )
    def test_safe_ttl_falls_back_to_default(self, bad_ttl, default):
        assert mentor_state._safe_ttl(bad_ttl, default) == default

    @pytest.mark.parametrize(
        'valid_ttl,default,expected',
        [
            (1, 30, 1),
            (60, 30, 60),
            ('120', 30, 120),
            (90000, 30, 90000),
        ],
    )
    def test_safe_ttl_coerces_positive_ints(self, valid_ttl, default, expected):
        assert mentor_state._safe_ttl(valid_ttl, default) == expected


class TestFallOpenContracts:
    @pytest.mark.parametrize('invalid_uid', [None, '', '   ', 123, 'a' * 150])
    def test_fall_open_on_invalid_uid(self, invalid_uid):
        assert mentor_state.read(invalid_uid) is None
        assert mentor_state.read_authoritative(invalid_uid) is None
        assert mentor_state.claim(invalid_uid) is True
        mentor_state.release(invalid_uid)  # no-op, must not raise
        mentor_state.record(invalid_uid, {'count': 1})  # no-op, must not raise

    @pytest.mark.parametrize('bad_state', [None, 'string', 123, [1, 2, 3], object()])
    def test_record_rejects_non_mapping_state(self, bad_state, clean_local_mirror):
        mentor_state.record('valid_user', bad_state)
        # Should not write to Redis or local mirror
        assert mentor_state._redis_key('valid_user') not in clean_local_mirror.store
        assert mentor_state.read('valid_user') is None

    def test_redis_failure_falls_open(self, monkeypatch):
        broken_redis = MagicMock()
        broken_redis.get.side_effect = RuntimeError('Redis disconnected')
        broken_redis.set.side_effect = RuntimeError('Redis disconnected')
        broken_redis.delete.side_effect = RuntimeError('Redis disconnected')

        import database.redis_db as redis_db

        monkeypatch.setattr(redis_db, 'r', broken_redis)

        assert mentor_state.read('user1') is None
        assert mentor_state.read_authoritative('user1') is None
        assert mentor_state.claim('user1') is True
        mentor_state.release('user1')  # must not raise

        # Failed write should clear local mirror and not raise
        mentor_state.record('user1', {'val': 1})
        with mentor_state._local_lock:
            assert 'user1' not in mentor_state._local

    def test_corrupted_json_in_redis_falls_open(self, clean_local_mirror):
        clean_local_mirror.set(mentor_state._redis_key('user1'), '{invalid_json')
        assert mentor_state.read('user1') is None
        assert mentor_state.read_authoritative('user1') is None


class TestLocalMirrorLifecycle:
    def test_happy_path_claim_record_and_mirror(self, clean_local_mirror):
        uid = 'user_happy'
        state = {'count': 3, 'last_eval_at': 1700000000.0}

        assert mentor_state.claim(uid) is True
        mentor_state.record(uid, state)

        # Read should return state from mirror
        assert mentor_state.read(uid) == state

        # Clear mirror to verify read_authoritative repopulates mirror
        with mentor_state._local_lock:
            mentor_state._local.clear()

        auth = mentor_state.read_authoritative(uid)
        assert auth == state

        with mentor_state._local_lock:
            assert uid in mentor_state._local

        mentor_state.release(uid)
        assert mentor_state._claim_key(uid) not in clean_local_mirror.store

    def test_local_mirror_eviction_under_overflow(self, monkeypatch):
        # Temporarily reduce MAX_LOCAL_ENTRIES for test speed
        monkeypatch.setattr(mentor_state, '_MAX_LOCAL_ENTRIES', 5)

        for i in range(10):
            mentor_state._write_local(f'user_{i}', {'i': i}, ttl=3600)

        with mentor_state._local_lock:
            # Must be clamped to 5
            assert len(mentor_state._local) == 5
            # Oldest keys user_0..user_4 must have been evicted, retaining user_5..user_9
            for i in range(5):
                assert f'user_{i}' not in mentor_state._local
            for i in range(5, 10):
                assert f'user_{i}' in mentor_state._local
