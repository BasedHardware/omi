"""Unit tests for the import quota input hardening.

Verifies:
- ``_quota_keys`` builds a Redis Cluster hash tag from a validated uid and kind.
- Unusable uids, kinds and amounts reserve nothing and never reach Redis.
- Malformed ``IMPORT_MONTHLY_*_LIMIT`` values fall back to the default instead of
  raising, and unknown kinds raise a stable ``ValueError``.
- ``release_import_quota`` ignores malformed reservations and keys.
"""

from unittest.mock import MagicMock

import pytest

import database.import_quotas as import_quotas


@pytest.fixture
def redis_client(monkeypatch):
    client = MagicMock()
    client.eval.return_value = 1
    monkeypatch.setattr(import_quotas, 'redis_db', MagicMock(r=client))
    return client


def test_quota_keys_use_the_uid_as_a_hash_tag():
    events, amounts = import_quotas._quota_keys('user-1', 'upload')
    assert events == 'import:monthly:upload:{user-1}:events'
    assert amounts == 'import:monthly:upload:{user-1}:amounts'


@pytest.mark.parametrize('uid', ['', '   ', None, True, 42, 'a}b', 'a{b', 'a:b', 'a/b', 'a\\b', '..', 'a..b', 'u' * 129])
def test_reserve_rejects_unusable_uids(redis_client, uid):
    assert import_quotas.reserve_import_quota(uid, 'upload', 1) is None
    assert redis_client.eval.call_args_list == []


@pytest.mark.parametrize('uid', ['a\x00b', 'a\x1fb', 'a\x7fb'])
def test_reserve_rejects_control_characters_in_uids(redis_client, uid):
    assert import_quotas.reserve_import_quota(uid, 'upload', 1) is None
    assert redis_client.eval.call_args_list == []


@pytest.mark.parametrize('kind', ['', 'uploads', None, True, 'UPLOAD', 'byte '])
def test_reserve_rejects_unknown_kinds(redis_client, kind):
    assert import_quotas.reserve_import_quota('user-1', kind, 1) is None
    assert redis_client.eval.call_args_list == []


@pytest.mark.parametrize('amount', [True, False, 0, -1, -500, 1.5, '10', None])
def test_reserve_rejects_unusable_amounts(redis_client, amount):
    assert import_quotas.reserve_import_quota('user-1', 'upload', amount) is None
    assert redis_client.eval.call_args_list == []


def test_reserve_admits_and_returns_the_reservation(redis_client):
    reservation = import_quotas.reserve_import_quota('user-1', 'byte', 2048)
    assert isinstance(reservation, str) and len(reservation) == 32
    (script, numkeys, events, amounts, window, limit, amount, member), _ = redis_client.eval.call_args_list[0]
    assert script == import_quotas._RESERVE_IMPORT_QUOTA_LUA
    assert numkeys == 2
    assert events == 'import:monthly:byte:{user-1}:events'
    assert amounts == 'import:monthly:byte:{user-1}:amounts'
    assert window == import_quotas.IMPORT_QUOTA_WINDOW_SECONDS
    assert limit == import_quotas._IMPORT_QUOTA_DEFAULTS['byte']
    assert amount == 2048
    assert member == reservation


def test_reserve_reports_a_spent_budget(redis_client):
    redis_client.eval.return_value = 0
    assert import_quotas.reserve_import_quota('user-1', 'upload', 1) is None


def test_reserve_propagates_redis_errors(redis_client):
    redis_client.eval.side_effect = RuntimeError('redis down')
    with pytest.raises(RuntimeError):
        import_quotas.reserve_import_quota('user-1', 'upload', 1)


def test_limit_uses_the_default(monkeypatch):
    monkeypatch.delenv('IMPORT_MONTHLY_UPLOAD_LIMIT', raising=False)
    assert import_quotas.import_quota_limit('upload') == 100


def test_limit_reads_the_environment(monkeypatch):
    monkeypatch.setenv('IMPORT_MONTHLY_UPLOAD_LIMIT', '7')
    assert import_quotas.import_quota_limit('upload') == 7


@pytest.mark.parametrize('raw', ['', '  ', 'lots', '1e3', '10.5', 'ten'])
def test_limit_falls_back_on_malformed_values(monkeypatch, raw):
    monkeypatch.setenv('IMPORT_MONTHLY_BYTE_LIMIT', raw)
    assert import_quotas.import_quota_limit('byte') == import_quotas._IMPORT_QUOTA_DEFAULTS['byte']


def test_limit_never_goes_negative(monkeypatch):
    monkeypatch.setenv('IMPORT_MONTHLY_UPLOAD_LIMIT', '-5')
    assert import_quotas.import_quota_limit('upload') == 0


def test_limit_rejects_unknown_kinds():
    with pytest.raises(ValueError):
        import_quotas.import_quota_limit('uploads')


def test_release_drops_a_valid_reservation(redis_client):
    import_quotas.release_import_quota('user-1', 'upload', 'res-1')
    (script, numkeys, events, amounts, member), _ = redis_client.eval.call_args_list[0]
    assert script == import_quotas._RELEASE_IMPORT_QUOTA_LUA
    assert numkeys == 2
    assert events == 'import:monthly:upload:{user-1}:events'
    assert amounts == 'import:monthly:upload:{user-1}:amounts'
    assert member == 'res-1'


@pytest.mark.parametrize(
    'reservation', ['', '   ', None, True, 7, ' res-1', 'res-1 ', 'a/b', 'a\\b', '..', 'a..b', 'r' * 65, 'a\x00b']
)
def test_release_ignores_unusable_reservations(redis_client, reservation):
    import_quotas.release_import_quota('user-1', 'upload', reservation)
    assert redis_client.eval.call_args_list == []


def test_release_ignores_unusable_keys(redis_client):
    import_quotas.release_import_quota('user/1', 'upload', 'res-1')
    import_quotas.release_import_quota('user-1', 'nope', 'res-1')
    assert redis_client.eval.call_args_list == []


def test_release_is_repeatable(redis_client):
    import_quotas.release_import_quota('user-1', 'upload', 'res-1')
    import_quotas.release_import_quota('user-1', 'upload', 'res-1')
    assert redis_client.eval.call_count == 2
