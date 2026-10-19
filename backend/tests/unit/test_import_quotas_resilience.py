"""Hermetic unit tests for backend/database/import_quotas.py resilience."""

import pytest

from database import import_quotas


class _FakeRedisClient:
    def __init__(self, eval_return=1):
        self.eval_return = eval_return
        self.calls = []

    def eval(self, script, numkeys, *args):
        self.calls.append((script, numkeys, args))
        return self.eval_return


@pytest.mark.parametrize('bad_kind', ['', '   ', 'unknown', 'audio', None, 123])
def test_import_quota_limit_rejects_invalid_kind(bad_kind):
    with pytest.raises(ValueError, match="kind must be 'upload' or 'byte'"):
        import_quotas.import_quota_limit(bad_kind)


def test_import_quota_limit_falls_back_on_malformed_env_var(monkeypatch):
    monkeypatch.setenv('IMPORT_MONTHLY_UPLOAD_LIMIT', 'not-an-int')
    assert import_quotas.import_quota_limit('  UPLOAD  ') == 100
    monkeypatch.setenv('IMPORT_MONTHLY_BYTE_LIMIT', '-250')
    assert import_quotas.import_quota_limit('byte') == 0


@pytest.mark.parametrize(
    'bad_uid',
    ['', '   ', 'user/1', 'user\\1', 'user..1', 'user{tag}', 'user}tag', 'user:1', 'a' * 129, None, 123],
)
def test_quota_keys_rejects_unsafe_uid(bad_uid):
    with pytest.raises(ValueError, match='uid'):
        import_quotas._quota_keys(bad_uid, 'upload')


@pytest.mark.parametrize('bad_amount', [True, False, 0, -10, 1.5, '10', None])
def test_reserve_import_quota_rejects_invalid_amount(bad_amount):
    client = _FakeRedisClient()
    with pytest.raises(ValueError, match='amount must be a positive integer'):
        import_quotas.reserve_import_quota('user_1', 'upload', bad_amount, redis_client=client)
    assert client.calls == []


def test_reserve_import_quota_trims_inputs_and_uses_injected_redis_client(monkeypatch):
    monkeypatch.setenv('IMPORT_MONTHLY_BYTE_LIMIT', '2048')
    client = _FakeRedisClient(eval_return=1)
    token = import_quotas.reserve_import_quota('  user_1  ', '  BYTE  ', 512, redis_client=client)
    assert isinstance(token, str) and len(token) == 32
    assert len(client.calls) == 1
    _, numkeys, args = client.calls[0]
    assert numkeys == 2
    assert args[:5] == (
        'import:monthly:byte:{user_1}:events',
        'import:monthly:byte:{user_1}:amounts',
        import_quotas.IMPORT_QUOTA_WINDOW_SECONDS,
        2048,
        512,
    )
    assert args[5] == token


def test_reserve_import_quota_returns_none_when_denied():
    client = _FakeRedisClient(eval_return=0)
    assert import_quotas.reserve_import_quota('user_1', 'upload', 1, redis_client=client) is None


@pytest.mark.parametrize('bad_reservation', ['', '   ', 'tok\n1', 'tok\x001', None, 123])
def test_release_import_quota_skips_redis_call_on_blank_or_invalid_reservation(bad_reservation):
    client = _FakeRedisClient()
    import_quotas.release_import_quota('user_1', 'upload', bad_reservation, redis_client=client)
    assert client.calls == []


def test_release_import_quota_trims_identifiers_and_executes_lua():
    client = _FakeRedisClient()
    import_quotas.release_import_quota('  user_1  ', ' UPLOAD ', '  res_abc123  ', redis_client=client)
    assert len(client.calls) == 1
    _, numkeys, args = client.calls[0]
    assert numkeys == 2
    assert args == (
        'import:monthly:upload:{user_1}:events',
        'import:monthly:upload:{user_1}:amounts',
        'res_abc123',
    )
