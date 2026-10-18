"""Hermetic unit tests for ``backend/database/action_items_cache.py`` resilience.

Covers the five gaps called out in the bounty:
  1. uid sanitization (injection / malformed keys)
  2. dependency injection on every public cache function
  3. RFC 9110 If-None-Match hardening (weak prefix + wrapping quotes)
  4. graceful import when ``config.firestore_read_levers`` is absent
  5. these tests themselves (this file)

No Redis, no Firestore, no network: every test injects a fake client.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
import types
from typing import Any, Dict, List, Optional

import redis as redis_pkg
import pytest

# Resolve the module relative to THIS file. In a real checkout the module lives at
# backend/database/action_items_cache.py; here it is laid down alongside the tests,
# so look next to the test first and fall back to the repo layout.
_HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(_HERE, '..', '..', '..', '..'))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

CACHE_MODULE_PATH = os.path.join(_HERE, 'action_items_cache.py')
if not os.path.exists(CACHE_MODULE_PATH):
    CACHE_MODULE_PATH = os.path.join(BACKEND_DIR, 'backend', 'database', 'action_items_cache.py')


class FakeRedisError(redis_pkg.exceptions.RedisError):  # type: ignore[attr-defined]
    """Injected-redis-failure stand-in: a real RedisError subclass, so the
    module's fail-open handlers catch it exactly as they would in production."""


class FakePipeline:
    def __init__(self) -> None:
        self.ops: List[tuple] = []

    def incr(self, key: str) -> 'FakePipeline':
        self.ops.append(('incr', key))
        return self

    def expire(self, key: str, ttl: int) -> 'FakePipeline':
        self.ops.append(('expire', key, ttl))
        return self

    def execute(self) -> List[Any]:
        return [None for _ in self.ops]


class FakeRedis:
    """Minimal in-memory stand-in recording every command issued."""

    def __init__(self, fail: bool = False) -> None:
        self.store: Dict[str, str] = {}
        self.fail = fail
        self.commands: List[tuple] = []
        self.pipeline_calls = 0

    # -- helpers used by the tests -------------------------------------------------
    def _maybe_fail(self) -> None:
        if self.fail:
            raise FakeRedisError('injected redis failure')

    # -- redis API used by the module ---------------------------------------------
    def pipeline(self) -> FakePipeline:
        self._maybe_fail()
        self.pipeline_calls += 1
        return FakePipeline()

    def get(self, key: str) -> Optional[str]:
        self._maybe_fail()
        self.commands.append(('get', key))
        return self.store.get(key)

    def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        self._maybe_fail()
        self.commands.append(('set', key, ex))
        self.store[key] = value
        return True


def _install_stubs(levers_available: bool) -> Dict[str, Any]:
    """Stub only the modules the repo layout requires. Leave ``redis`` alone.

    A real ``redis`` package is available, and the module under test catches
    ``redis.exceptions.RedisError`` from it. Shadowing ``redis`` with a fake module
    makes the module catch a *different* RedisError class than the one these tests
    raise, so fail-open handlers silently never fire. We therefore stub only
    ``database.redis_db`` and ``config.firestore_read_levers``.
    """
    saved = {k: v for k, v in sys.modules.items()
             if k == 'config' or k.startswith('config.')
             or k == 'database' or k.startswith('database.')}

    for key in list(saved):
        del sys.modules[key]

    database_pkg = types.ModuleType('database')
    database_pkg.__path__ = []  # type: ignore[attr-defined]
    redis_db_mod = types.ModuleType('database.redis_db')
    redis_db_mod.create_bounded_redis_client = lambda *a, **k: None  # type: ignore[attr-defined]
    database_pkg.redis_db = redis_db_mod  # type: ignore[attr-defined]
    sys.modules['database'] = database_pkg
    sys.modules['database.redis_db'] = redis_db_mod

    config_pkg = types.ModuleType('config')
    config_pkg.__path__ = []  # type: ignore[attr-defined]
    sys.modules['config'] = config_pkg

    if levers_available:
        levers = types.ModuleType('config.firestore_read_levers')

        def lever_enabled(name: str, uid: str) -> bool:
            return name == 'action_items_page' and uid == 'lever-user'

        levers.lever_enabled = lever_enabled  # type: ignore[attr-defined]
        sys.modules['config.firestore_read_levers'] = levers

    return saved


def _restore_stubs(saved: Dict[str, Any]) -> None:
    for key in [k for k in sys.modules
                if k == 'config' or k.startswith('config.')
                or k == 'database' or k.startswith('database.')]:
        del sys.modules[key]
    sys.modules.update(saved)


def load_module(levers_available: bool = True) -> types.ModuleType:
    """Load the cache module with a controllable environment (no repo needed)."""
    saved = _install_stubs(levers_available)
    try:
        spec = importlib.util.spec_from_file_location('action_items_cache', CACHE_MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        _restore_stubs(saved)
    return module


# ---------------------------------------------------------------------------
# 1. uid sanitization
# ---------------------------------------------------------------------------

class TestUidSanitization:
    def test_none_uid_is_rejected(self) -> None:
        m = load_module()
        assert m._sanitize_uid(None) is None

    def test_non_string_uid_is_rejected(self) -> None:
        m = load_module()
        for bad in (123, 1.5, b'uid', ['u'], {'u': 1}, object()):
            assert m._sanitize_uid(bad) is None

    def test_empty_and_whitespace_uids_are_rejected(self) -> None:
        m = load_module()
        for bad in ('', ' ', '\t', '\n', '   '):
            assert m._sanitize_uid(bad) is None

    def test_newline_and_carriage_return_are_rejected(self) -> None:
        m = load_module()
        for bad in ('u\r\nid', 'u\nid', 'u\rid', 'uid\r', '\nuid'):
            assert m._sanitize_uid(bad) is None

    def test_tab_and_embedded_space_are_rejected(self) -> None:
        m = load_module()
        for bad in ('u\tid', 'u id', ' uid', 'uid '):
            assert m._sanitize_uid(bad) is None

    def test_plain_uid_is_accepted_unchanged(self) -> None:
        m = load_module()
        assert m._sanitize_uid('user-42') == 'user-42'

    def test_uid_with_unicode_is_accepted(self) -> None:
        m = load_module()
        assert m._sanitize_uid('корисник-1') == 'корисник-1'

    def test_injection_uid_does_not_reach_redis(self) -> None:
        m = load_module()
        fake = FakeRedis()
        m.bump_action_items_list_version('uid\r\nINJECTED', redis_client=fake)
        assert fake.commands == []
        assert fake.pipeline_calls == 0

    def test_get_version_returns_none_for_injection_uid(self) -> None:
        m = load_module()
        fake = FakeRedis()
        assert m.get_action_items_list_version('uid\n', redis_client=fake) is None
        assert fake.commands == []

    def test_list_cache_key_raises_for_unsanitizable_uid(self) -> None:
        m = load_module()
        with pytest.raises(ValueError):
            m.list_cache_key('bad uid', 1, {})

    def test_list_cache_key_is_stable_and_safe(self) -> None:
        m = load_module()
        key = m.list_cache_key('user-42', 3, {'limit': 10})
        assert key.startswith('ail:user-42:3:')
        assert ' ' not in key and '\n' not in key


# ---------------------------------------------------------------------------
# 2. dependency injection
# ---------------------------------------------------------------------------

class TestDependencyInjection:
    def test_bump_uses_injected_client(self) -> None:
        m = load_module()
        fake = FakeRedis()
        m.bump_action_items_list_version('user-1', redis_client=fake)
        assert fake.pipeline_calls == 1

    def test_get_version_uses_injected_client(self) -> None:
        m = load_module()
        fake = FakeRedis()
        fake.store['ail:ver:user-1'] = '7'
        assert m.get_action_items_list_version('user-1', redis_client=fake) == 7
        assert ('get', 'ail:ver:user-1') in fake.commands

    def test_read_cached_list_uses_injected_client(self) -> None:
        m = load_module()
        fake = FakeRedis()
        fake.store['ail:k'] = json.dumps({'etag': 'W/"a"', 'body': {'x': 1}})
        assert m.read_cached_list('ail:k', redis_client=fake) == {'etag': 'W/"a"', 'body': {'x': 1}}

    def test_write_cached_list_uses_injected_client(self) -> None:
        m = load_module()
        fake = FakeRedis()
        m.write_cached_list('ail:k', body={'x': 1}, etag='W/"a"', ttl=30, redis_client=fake)
        assert ('set', 'ail:k', 30) in fake.commands

    def test_round_trip_through_injected_client(self) -> None:
        m = load_module()
        fake = FakeRedis()
        body = {'items': [1, 2, 3]}
        etag = m.compute_etag(body)
        m.write_cached_list('ail:u:1:fp', body=body, etag=etag, ttl=30, redis_client=fake)
        assert m.read_cached_list('ail:u:1:fp', redis_client=fake) == {'etag': etag, 'body': body}

    def test_bump_then_version_is_one(self) -> None:
        m = load_module()
        fake = FakeRedis()
        m.bump_action_items_list_version('user-1', redis_client=fake)
        fake.store['ail:ver:user-1'] = '1'
        assert m.get_action_items_list_version('user-1', redis_client=fake) == 1

    def test_write_is_skipped_when_ttl_zero(self) -> None:
        m = load_module()
        fake = FakeRedis()
        m.write_cached_list('ail:k', body={'x': 1}, etag='W/"a"', ttl=0, redis_client=fake)
        assert fake.commands == []

    def test_key_fingerprint_is_stable_across_param_order(self) -> None:
        m = load_module()
        a = m.list_cache_key('u', 1, {'limit': 10, 'offset': 0})
        b = m.list_cache_key('u', 1, {'offset': 0, 'limit': 10})
        assert a == b

    def test_key_differs_for_different_version(self) -> None:
        m = load_module()
        assert m.list_cache_key('u', 1, {}) != m.list_cache_key('u', 2, {})


# ---------------------------------------------------------------------------
# 3. RFC 9110 If-None-Match
# ---------------------------------------------------------------------------

class TestIfNoneMatch:
    def test_exact_strong_match(self) -> None:
        m = load_module()
        assert m.if_none_match_matches('"abc123"', '"abc123"') is True

    def test_weak_prefix_matches_strong_form(self) -> None:
        m = load_module()
        assert m.if_none_match_matches('W/"abc123"', '"abc123"') is True

    def test_stored_weak_matches_client_strong(self) -> None:
        m = load_module()
        assert m.if_none_match_matches('"abc123"', 'W/"abc123"') is True

    def test_unquoted_client_value_matches_quoted_stored(self) -> None:
        m = load_module()
        assert m.if_none_match_matches('abc123', '"abc123"') is True

    def test_quoted_client_value_matches_unquoted_stored(self) -> None:
        m = load_module()
        assert m.if_none_match_matches('"abc123"', 'abc123') is True

    def test_unquoted_weak_matches_quoted_weak(self) -> None:
        m = load_module()
        assert m.if_none_match_matches('W/abc123', 'W/"abc123"') is True

    def test_star_matches_anything(self) -> None:
        m = load_module()
        assert m.if_none_match_matches('*', '"whatever"') is True

    def test_multiple_candidates_any_match(self) -> None:
        m = load_module()
        assert m.if_none_match_matches('"nope", "abc123"', '"abc123"') is True

    def test_no_match_returns_false(self) -> None:
        m = load_module()
        assert m.if_none_match_matches('"other"', '"abc123"') is False

    def test_empty_header_returns_false(self) -> None:
        m = load_module()
        assert m.if_none_match_matches(None, '"abc123"') is False
        assert m.if_none_match_matches('', '"abc123"') is False

    def test_whitespace_around_candidate_is_tolerated(self) -> None:
        m = load_module()
        assert m.if_none_match_matches('  "abc123"  ', '"abc123"') is True

    def test_real_etag_from_compute_etag_matches(self) -> None:
        m = load_module()
        etag = m.compute_etag({'a': 1})
        assert etag.startswith('W/"') and etag.endswith('"')
        assert m.if_none_match_matches(etag, etag) is True
        assert m.if_none_match_matches(etag[2:], etag) is True


# ---------------------------------------------------------------------------
# 4. graceful import without the levers module
# ---------------------------------------------------------------------------

class TestLeverFallback:
    def test_module_imports_without_levers_module(self) -> None:
        m = load_module(levers_available=False)
        assert m.lever_enabled is None

    def test_list_cache_ttl_works_without_levers_module(self) -> None:
        m = load_module(levers_available=False)
        os.environ['ACTION_ITEMS_LIST_CACHE_TTL_SECONDS'] = '45'
        try:
            assert m.list_cache_ttl_seconds('user-1') == 45
        finally:
            del os.environ['ACTION_ITEMS_LIST_CACHE_TTL_SECONDS']

    def test_lever_override_applies_when_module_present(self) -> None:
        m = load_module(levers_available=True)
        os.environ['ACTION_ITEMS_LIST_CACHE_TTL_SECONDS'] = '10'
        os.environ['ACTION_ITEMS_PAGE_CACHE_TTL_SECONDS'] = '99'
        try:
            assert m.list_cache_ttl_seconds('lever-user') == 99
            assert m.list_cache_ttl_seconds('other-user') == 10
        finally:
            del os.environ['ACTION_ITEMS_LIST_CACHE_TTL_SECONDS']
            del os.environ['ACTION_ITEMS_PAGE_CACHE_TTL_SECONDS']

    def test_non_integer_env_falls_back_to_default(self) -> None:
        m = load_module()
        os.environ['ACTION_ITEMS_LIST_CACHE_TTL_SECONDS'] = 'not-a-number'
        try:
            assert m.list_cache_ttl_seconds('user-1') == 30
        finally:
            del os.environ['ACTION_ITEMS_LIST_CACHE_TTL_SECONDS']

    def test_zero_ttl_disables_cache(self) -> None:
        m = load_module()
        os.environ['ACTION_ITEMS_LIST_CACHE_TTL_SECONDS'] = '0'
        try:
            assert m.list_cache_ttl_seconds('user-1') == 0
        finally:
            del os.environ['ACTION_ITEMS_LIST_CACHE_TTL_SECONDS']

    def test_ttl_is_capped_at_maximum(self) -> None:
        m = load_module()
        os.environ['ACTION_ITEMS_LIST_CACHE_TTL_SECONDS'] = '99999'
        try:
            assert m.list_cache_ttl_seconds('user-1') == 300
        finally:
            del os.environ['ACTION_ITEMS_LIST_CACHE_TTL_SECONDS']


# ---------------------------------------------------------------------------
# 5. fail-open behaviour
# ---------------------------------------------------------------------------

class TestFailOpen:
    def test_read_returns_none_on_redis_error(self) -> None:
        m = load_module()
        fake = FakeRedis(fail=True)
        assert m.read_cached_list('ail:k', redis_client=fake) is None

    def test_write_does_not_raise_on_redis_error(self) -> None:
        m = load_module()
        fake = FakeRedis(fail=True)
        m.write_cached_list('ail:k', body={'x': 1}, etag='W/"a"', ttl=30, redis_client=fake)

    def test_bump_does_not_raise_on_redis_error(self) -> None:
        m = load_module()
        fake = FakeRedis(fail=True)
        m.bump_action_items_list_version('user-1', redis_client=fake)

    def test_get_version_returns_none_on_redis_error(self) -> None:
        m = load_module()
        fake = FakeRedis(fail=True)
        assert m.get_action_items_list_version('user-1', redis_client=fake) is None

    def test_malformed_cached_payload_returns_none(self) -> None:
        m = load_module()
        fake = FakeRedis()
        fake.store['ail:k'] = 'not-json'
        assert m.read_cached_list('ail:k', redis_client=fake) is None

    def test_payload_missing_keys_returns_none(self) -> None:
        m = load_module()
        fake = FakeRedis()
        fake.store['ail:k'] = json.dumps({'etag': 'W/"a"'})
        assert m.read_cached_list('ail:k', redis_client=fake) is None

    def test_non_dict_payload_returns_none(self) -> None:
        m = load_module()
        fake = FakeRedis()
        fake.store['ail:k'] = json.dumps([1, 2, 3])
        assert m.read_cached_list('ail:k', redis_client=fake) is None

    def test_version_read_of_garbage_returns_zero(self) -> None:
        m = load_module()
        fake = FakeRedis()
        fake.store['ail:ver:u'] = 'not-an-int'
        assert m.get_action_items_list_version('u', redis_client=fake) == 0

    def test_etag_is_deterministic_for_same_body(self) -> None:
        m = load_module()
        body = {'z': 1, 'a': [1, 2]}
        assert m.compute_etag(body) == m.compute_etag({'a': [1, 2], 'z': 1})

    def test_etag_differs_for_different_body(self) -> None:
        m = load_module()
        assert m.compute_etag({'a': 1}) != m.compute_etag({'a': 2})

    def test_unsanitizable_uid_is_fail_open_everywhere(self) -> None:
        m = load_module()
        fake = FakeRedis()
        # bump is a no-op, version read returns None, and nothing hits Redis
        m.bump_action_items_list_version('', redis_client=fake)
        assert m.get_action_items_list_version('  ', redis_client=fake) is None
        assert fake.commands == []
