"""Rolling import quotas execute atomically against Redis, without live services."""

import concurrent.futures

import pytest

from database import import_quotas

fakeredis = pytest.importorskip('fakeredis')


@pytest.fixture
def quota(monkeypatch):
    client = fakeredis.FakeRedis()
    try:
        client.eval('return 1', 0)
    except Exception:
        pytest.skip('fakeredis with Lua support unavailable under the guarded runner')
    monkeypatch.setattr(import_quotas.redis_db, 'r', client)
    monkeypatch.setenv('IMPORT_MONTHLY_UPLOAD_LIMIT', '2')
    monkeypatch.setenv('IMPORT_MONTHLY_BYTE_LIMIT', '10')
    return client


def test_upload_limit_counts_requests_and_keeps_users_separate(quota):
    assert import_quotas.reserve_import_quota('u1', 'upload', 1)
    assert import_quotas.reserve_import_quota('u1', 'upload', 1)
    assert import_quotas.reserve_import_quota('u1', 'upload', 1) is None
    assert import_quotas.reserve_import_quota('u2', 'upload', 1)


def test_byte_reservations_release_only_their_own_charge_and_are_idempotent(quota):
    first = import_quotas.reserve_import_quota('u1', 'byte', 7)
    second = import_quotas.reserve_import_quota('u1', 'byte', 3)
    assert first and second
    assert import_quotas.reserve_import_quota('u1', 'byte', 1) is None
    import_quotas.release_import_quota('u1', 'byte', first)
    import_quotas.release_import_quota('u1', 'byte', first)
    assert import_quotas.reserve_import_quota('u1', 'byte', 7)
    assert import_quotas.reserve_import_quota('u1', 'byte', 1) is None


def test_rolling_window_prunes_old_events_but_preserves_recent_usage(quota):
    first = import_quotas.reserve_import_quota('u1', 'byte', 7)
    assert first
    assert import_quotas.reserve_import_quota('u1', 'byte', 3)
    events, amounts = import_quotas._quota_keys('u1', 'byte')
    now = quota.time()[0]
    quota.zadd(events, {first: now - import_quotas.IMPORT_QUOTA_WINDOW_SECONDS - 1})

    assert import_quotas.reserve_import_quota('u1', 'byte', 7)
    assert quota.hget(amounts, first) is None
    assert int(quota.hget(amounts, 'total')) == 10
    assert 0 < quota.ttl(events) <= import_quotas.IMPORT_QUOTA_WINDOW_SECONDS
    assert 0 < quota.ttl(amounts) <= import_quotas.IMPORT_QUOTA_WINDOW_SECONDS
    assert import_quotas.reserve_import_quota('u1', 'byte', 1) is None


def test_concurrent_reservations_cannot_overspend(quota):
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        reservations = list(pool.map(lambda _: import_quotas.reserve_import_quota('u1', 'byte', 1), range(30)))
    assert sum(reservation is not None for reservation in reservations) == 10


def test_default_limits_and_environment_overrides(monkeypatch):
    monkeypatch.delenv('IMPORT_MONTHLY_UPLOAD_LIMIT', raising=False)
    monkeypatch.delenv('IMPORT_MONTHLY_BYTE_LIMIT', raising=False)
    assert import_quotas.import_quota_limit('upload') == 100
    assert import_quotas.import_quota_limit('byte') == 1024 * 1024 * 1024
    monkeypatch.setenv('IMPORT_MONTHLY_UPLOAD_LIMIT', '0')
    assert import_quotas.import_quota_limit('upload') == 0
