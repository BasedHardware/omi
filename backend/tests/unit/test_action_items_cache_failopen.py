"""#20106 — the action-items list cache must fail open when Redis is absent.

redis_db.r is None during cold init / local dev / tests. Accessing .get()/.set()
on None raised AttributeError — not RedisError — which escaped every helper's
fail-open contract. All helpers now gate on _client() first, and write TTLs are
clamped to a documented max.
"""

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import database.action_items_cache as cache
from database import redis_db


def _no_redis(monkeypatch):
    monkeypatch.setattr(redis_db, 'r', None)


def test_all_helpers_fail_open_without_client(monkeypatch):
    _no_redis(monkeypatch)
    cache.bump_action_items_list_version('u1')  # no AttributeError
    assert cache.get_action_items_list_version('u1') is None
    assert cache.read_cached_list('k') is None
    cache.write_cached_list('k', body={'a': 1}, etag='e', ttl=60)  # no AttributeError


def test_bump_uses_pipeline_and_expire(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(redis_db, 'r', client)
    cache.bump_action_items_list_version('u1')
    pipe = client.pipeline.return_value
    pipe.incr.assert_called_once()
    pipe.expire.assert_called_once()
    pipe.execute.assert_called_once()


def test_get_version_parses_int_and_handles_bad(monkeypatch):
    client = MagicMock()
    client.get.return_value = b'7'
    monkeypatch.setattr(redis_db, 'r', client)
    assert cache.get_action_items_list_version('u1') == 7
    client.get.return_value = b'garbage'
    assert cache.get_action_items_list_version('u1') == 0  # unparseable = treat as never-written


def test_write_clamps_oversized_ttl(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(redis_db, 'r', client)
    cache.write_cached_list('k', body={}, etag='e', ttl=10**9)
    assert client.set.call_args.kwargs['ex'] == cache._TTL_MAX_SECONDS


def test_write_rejects_bad_ttl_and_bool(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(redis_db, 'r', client)
    for bad_ttl in (0, -5, True, '60'):
        cache.write_cached_list('k', body={}, etag='e', ttl=bad_ttl)
    client.set.assert_not_called()


def test_redis_error_still_fails_open(monkeypatch):
    client = MagicMock()
    client.get.side_effect = cache.redis_pkg.exceptions.RedisError('down')
    monkeypatch.setattr(redis_db, 'r', client)
    assert cache.read_cached_list('k') is None
    assert cache.get_action_items_list_version('u1') is None
