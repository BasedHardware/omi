from unittest.mock import MagicMock
import pytest
import redis as redis_pkg

from database import action_items_cache


def test_bump_version_valid():
    client = MagicMock()
    pipe = MagicMock()
    client.pipeline.return_value = pipe

    action_items_cache.bump_action_items_list_version('user_123', redis_client=client)

    client.pipeline.assert_called_once()
    pipe.incr.assert_called_once_with('ail:ver:user_123')
    pipe.expire.assert_called_once_with('ail:ver:user_123', action_items_cache._VERSION_TTL_SECONDS)
    pipe.execute.assert_called_once()


@pytest.mark.parametrize('bad_uid', ['', '  ', None, 123, 'user\r\nSET bad 1', 'user\ninject', 'user name'])
def test_bump_version_invalid_uid_noop(bad_uid):
    client = MagicMock()
    action_items_cache.bump_action_items_list_version(bad_uid, redis_client=client)
    client.pipeline.assert_not_called()


def test_bump_version_redis_error_fails_open():
    client = MagicMock()
    pipe = MagicMock()
    pipe.execute.side_effect = redis_pkg.exceptions.ConnectionError('Redis offline')
    client.pipeline.return_value = pipe

    # Must fail open and not raise
    action_items_cache.bump_action_items_list_version('user_123', redis_client=client)


def test_get_version_valid():
    client = MagicMock()
    client.get.return_value = b'42'

    version = action_items_cache.get_action_items_list_version('user_123', redis_client=client)
    assert version == 42
    client.get.assert_called_once_with('ail:ver:user_123')


def test_get_version_missing_returns_zero():
    client = MagicMock()
    client.get.return_value = None

    version = action_items_cache.get_action_items_list_version('user_new', redis_client=client)
    assert version == 0


def test_get_version_redis_error_returns_none():
    client = MagicMock()
    client.get.side_effect = redis_pkg.exceptions.TimeoutError('Redis timeout')

    version = action_items_cache.get_action_items_list_version('user_123', redis_client=client)
    assert version is None


@pytest.mark.parametrize('bad_uid', ['', '  ', None, 'user\r\ninject', 'bad user'])
def test_get_version_invalid_uid_returns_none(bad_uid):
    client = MagicMock()
    version = action_items_cache.get_action_items_list_version(bad_uid, redis_client=client)
    assert version is None
    client.get.assert_not_called()


def test_read_cached_list_hit():
    client = MagicMock()
    client.get.return_value = b'{"etag": "W/\\"abc\\"", "body": {"items": [1, 2]}}'

    data = action_items_cache.read_cached_list('ail:user_1:1:fingerprint', redis_client=client)
    assert data is not None
    assert data['etag'] == 'W/"abc"'
    assert data['body'] == {'items': [1, 2]}


def test_read_cached_list_corrupted_json_returns_none():
    client = MagicMock()
    client.get.return_value = b'not valid json {'

    assert action_items_cache.read_cached_list('key', redis_client=client) is None


def test_read_cached_list_malformed_shape_returns_none():
    client = MagicMock()
    client.get.return_value = b'{"no_etag": true}'

    assert action_items_cache.read_cached_list('key', redis_client=client) is None


def test_write_cached_list_valid():
    client = MagicMock()
    action_items_cache.write_cached_list(
        'key_123',
        body={'foo': 'bar'},
        etag='W/"123"',
        ttl=30,
        redis_client=client,
    )
    client.set.assert_called_once()
    assert client.set.call_args[0][0] == 'key_123'
    assert client.set.call_args[1]['ex'] == 30


def test_write_cached_list_zero_ttl_noop():
    client = MagicMock()
    action_items_cache.write_cached_list(
        'key_123',
        body={'foo': 'bar'},
        etag='W/"123"',
        ttl=0,
        redis_client=client,
    )
    client.set.assert_not_called()


def test_write_cached_list_redis_error_fails_open():
    client = MagicMock()
    client.set.side_effect = redis_pkg.exceptions.ConnectionError('Down')
    # Must not raise
    action_items_cache.write_cached_list(
        'key_123',
        body={'foo': 'bar'},
        etag='W/"123"',
        ttl=30,
        redis_client=client,
    )


def test_compute_etag_deterministic():
    body1 = {'b': 2, 'a': 1}
    body2 = {'a': 1, 'b': 2}
    assert action_items_cache.compute_etag(body1) == action_items_cache.compute_etag(body2)
    assert action_items_cache.compute_etag(body1).startswith('W/"')


@pytest.mark.parametrize(
    'header,etag,expected',
    [
        ('W/"abc"', 'W/"abc"', True),
        ('"abc"', 'W/"abc"', True),
        ('abc', 'W/"abc"', True),
        ('W/"abc"', '"abc"', True),
        ('*', 'W/"abc"', True),
        ('W/"xyz", W/"abc"', 'W/"abc"', True),
        ('W/"different"', 'W/"abc"', False),
        ('', 'W/"abc"', False),
        (None, 'W/"abc"', False),
    ],
)
def test_if_none_match_matches_robust(header, etag, expected):
    assert action_items_cache.if_none_match_matches(header, etag) is expected
