from __future__ import annotations

import pytest
import redis

from database import redis_db


def _reset_scripts() -> None:
    redis_db._filter_trim_script = None
    redis_db._filter_admit_script = None


def _trim_lua_body() -> str:
    src = redis_db._FILTER_TRIM_LUA
    if src.startswith('#!'):
        return src.split('\n', 1)[1]
    return src


@pytest.fixture
def fake_r(monkeypatch):
    try:
        import fakeredis
    except Exception as exc:
        pytest.skip(f'fakeredis unavailable: {exc}')
    client = fakeredis.FakeRedis()
    _reset_scripts()
    monkeypatch.setattr(redis_db, 'r', client)
    # fakeredis cannot parse Redis 7 shebang flags; prod Redis 7.4 can.
    redis_db._filter_trim_script = client.register_script(_trim_lua_body())
    redis_db._filter_admit_script = client.register_script(redis_db._FILTER_ADMIT_LUA)
    yield client
    _reset_scripts()


def test_missing_key_adds_first_member(fake_r) -> None:
    redis_db.add_filter_category_item('u1', 'topics', 'alpha')
    assert fake_r.smembers('users:u1:filters:topics') == {b'alpha'}


def test_grows_to_cap(fake_r) -> None:
    for i in range(499):
        redis_db.add_filter_category_item('u1', 'topics', f't{i}')
    assert fake_r.scard('users:u1:filters:topics') == 499
    redis_db.add_filter_category_item('u1', 'topics', 'last')
    assert fake_r.scard('users:u1:filters:topics') == 500


def test_refuse_at_cap_without_removal(fake_r) -> None:
    for i in range(500):
        fake_r.sadd('users:u1:filters:topics', f't{i}')
    before = fake_r.smembers('users:u1:filters:topics')
    redis_db.add_filter_category_item('u1', 'topics', 'new-member')
    after = fake_r.smembers('users:u1:filters:topics')
    assert after == before
    assert b'new-member' not in after


def test_duplicate_at_capacity_does_not_remove(fake_r) -> None:
    for i in range(500):
        fake_r.sadd('users:u1:filters:topics', f't{i}')
    redis_db.add_filter_category_item('u1', 'topics', 't0')
    assert fake_r.scard('users:u1:filters:topics') == 500
    assert fake_r.sismember('users:u1:filters:topics', 't0')


@pytest.mark.parametrize('start,expect_removed', [(501, 1), (628, 128), (629, 128)])
def test_legacy_trim_batch(fake_r, start, expect_removed) -> None:
    for i in range(start):
        fake_r.sadd('users:u1:filters:topics', f't{i}')
    redis_db.add_filter_category_item('u1', 'topics', 'new')
    assert fake_r.scard('users:u1:filters:topics') == start - expect_removed
    assert not fake_r.sismember('users:u1:filters:topics', 'new')


def test_repeated_trim_stops_at_cap(fake_r) -> None:
    for i in range(600):
        fake_r.sadd('users:u1:filters:topics', f't{i}')
    for _ in range(5):
        redis_db.add_filter_category_item('u1', 'topics', 'ignored')
    assert fake_r.scard('users:u1:filters:topics') == 500


def test_does_not_touch_other_keys(fake_r) -> None:
    fake_r.set('translate:v1:abc:en', '1')
    fake_r.set('memories-visibility:cid1', 'u1')
    fake_r.sadd('users:u2:filters:topics', 'keep')
    fake_r.sadd('users:u1:filters:people', 'bob')
    redis_db.add_filter_category_item('u1', 'topics', 'alpha')
    assert fake_r.get('translate:v1:abc:en') == b'1'
    assert fake_r.get('memories-visibility:cid1') == b'u1'
    assert fake_r.smembers('users:u2:filters:topics') == {b'keep'}
    assert fake_r.smembers('users:u1:filters:people') == {b'bob'}


def test_invalid_category_is_noop(fake_r) -> None:
    redis_db.add_filter_category_item('u1', 'nope', 'x')
    redis_db.add_filter_category_item('u1', 'topics', '')
    assert fake_r.dbsize() == 0


def test_redis_error_fail_open_no_uncapped_write(fake_r, monkeypatch) -> None:
    recorded = []

    def boom(*_a, **_k):
        raise redis.exceptions.RedisError('OOM')  # type: ignore[attr-defined]

    monkeypatch.setattr(redis_db, '_filter_category_scripts', boom)
    monkeypatch.setattr(
        'utils.observability.fallback.record_fallback',
        lambda **kwargs: recorded.append(kwargs),
    )
    redis_db.add_filter_category_item('u1', 'topics', 'alpha')
    assert fake_r.dbsize() == 0
    assert recorded and recorded[0]['outcome'] == 'degraded'
