"""Real Lua classification and encrypted response freshness for polling cuts."""

from types import SimpleNamespace
from unittest.mock import Mock

import fakeredis
import pytest
from fastapi import Request, Response

from utils import external_list_reads as cache, external_polling_cache as policy


def test_disabled_policy_does_not_touch_request_identity(monkeypatch):
    monkeypatch.setenv('OMI_EXTERNAL_LIST_POLLING_CACHE_ENABLED', 'false')
    touched = []

    class UnusableRequest:
        @property
        def headers(self):
            touched.append('headers')
            raise AssertionError('identity must be untouched while off')

        @property
        def url(self):
            touched.append('url')
            raise AssertionError('route must be untouched while off')

    client = Mock()
    request = UnusableRequest()
    assert policy.adaptive_ttl(client, request, 'owner', object()) == 10
    assert policy.negative_key(request, 'owner', object(), 'item') is None
    assert touched == []
    client.eval.assert_not_called()


def test_enabled_policy_with_unusable_identity_bypasses_without_breaking_source(monkeypatch):
    monkeypatch.setenv('OMI_EXTERNAL_LIST_POLLING_CACHE_ENABLED', 'true')
    monkeypatch.setenv('OMI_EXTERNAL_LIST_POLLING_CACHE_PERCENT', '100')
    monkeypatch.setenv('OMI_EXTERNAL_LIST_CACHE_ENABLED', 'true')
    request = Request(
        {'type': 'http', 'method': 'GET', 'path': '/v1/dev/user/memories', 'headers': [], 'query_string': b''}
    )
    context = SimpleNamespace(app_id=object(), key_id='key')
    client = Mock()
    assert policy.adaptive_ttl(client, request, 'owner', context) == 10
    assert policy.negative_key(request, 'owner', context, 'item') is None
    client.eval.assert_not_called()


@pytest.fixture
def polling(monkeypatch):
    client = fakeredis.FakeRedis()
    now = [1000.0]
    monkeypatch.setattr(cache, '_client', client)
    monkeypatch.setattr(cache.time, 'time', lambda: now[0])
    monkeypatch.setenv('OMI_EXTERNAL_LIST_POLLING_CACHE_ENABLED', 'true')
    monkeypatch.setenv('OMI_EXTERNAL_LIST_POLLING_CACHE_PERCENT', '100')
    monkeypatch.setenv('OMI_EXTERNAL_LIST_SINGLE_FLIGHT_ENABLED', 'false')
    monkeypatch.setenv('OMI_EXTERNAL_LIST_CACHE_ENABLED', 'true')
    return client, now


def lookup(token='synthetic', path='/v1/dev/user/memories'):
    request = Request(
        {
            'type': 'http',
            'method': 'GET',
            'path': path,
            'headers': [(b'authorization', token.encode())],
            'query_string': b'',
        }
    )
    response = Response()
    hit = cache.cached_list_response(
        request, response, uid='owner', context=SimpleNamespace(app_id='app', key_id='key'), query={'limit': 25}
    )
    return request, response, hit


def test_only_proven_fast_pollers_can_reuse_an_unversioned_list_after_ten_seconds(polling):
    _, now = polling
    for moment in [1000, 1020]:
        now[0] = moment
        request, response, _ = lookup()
        assert request.state.external_list_cache_entry.ttl == 10
    now[0] = 1040
    request, response, _ = lookup()
    assert request.state.external_list_cache_entry.ttl == 60
    assert 'max-age=60' in response.headers['X-Omi-List-Cache']
    request.state.external_list_cache_entry.store(Response(b'["before-write"]', headers=response.headers))
    now[0] = 1060
    assert lookup()[2].body == b'["before-write"]'
    # A different key does not inherit poller status or the stale list.
    request, response, hit = lookup(token='ordinary')
    assert hit is None and request.state.external_list_cache_entry.ttl == 10
    request.state.external_list_cache_entry.store(Response(b'["fresh"]'))
    now[0] = 1071
    assert lookup(token='ordinary')[2] is None


def test_slow_gap_and_kill_switch_immediately_make_extended_entries_unreachable(polling, monkeypatch):
    client, now = polling
    for moment in range(1000, 1021, 2):
        now[0] = moment
        request, response, _ = lookup()
    assert request.state.external_list_cache_entry.ttl == 300
    extended_key = request.state.external_list_cache_entry.key
    request.state.external_list_cache_entry.store(Response(b'[]', headers=response.headers))
    monkeypatch.setenv('OMI_EXTERNAL_LIST_POLLING_CACHE_ENABLED', 'false')
    assert lookup()[2] is None
    monkeypatch.setenv('OMI_EXTERNAL_LIST_POLLING_CACHE_ENABLED', 'true')
    now[0] = 1081
    assert client.get(extended_key) is not None  # Still inside its original 300s lifetime.
    request, _, hit = lookup()
    assert hit is None and request.state.external_list_cache_entry.ttl == 10


def test_subsecond_fanout_does_not_qualify_and_ttl_is_bounded(polling):
    client, now = polling
    request, _, _ = lookup()
    context = SimpleNamespace(app_id='app', key_id='key')
    for _ in range(20):
        assert policy.adaptive_ttl(client, request, 'owner', context) == 10
    observed = []
    for _ in range(15):
        now[0] += 2
        observed.append(policy.adaptive_ttl(client, request, 'owner', context))
    assert set(observed) == {10, 60, 120, 300}
    assert observed[-1] == 300


def test_missing_response_disclosure_surface_cannot_use_extended_entries(polling):
    _, now = polling
    for moment in [1000, 1020, 1040]:
        now[0] = moment
        request, response, _ = lookup()
    request.state.external_list_cache_entry.store(Response(b'[]', headers=response.headers))
    hit = cache.cached_list_response(
        request, None, uid='owner', context=SimpleNamespace(app_id='app', key_id='key'), query={'limit': 25}
    )
    assert hit is None and request.state.external_list_cache_entry.ttl == 10


def test_redis_failure_default_off_and_non_developer_routes_keep_ten_seconds(polling, monkeypatch):
    client, _ = polling
    monkeypatch.setattr(client, 'eval', lambda *args: (_ for _ in ()).throw(ConnectionError()))
    assert lookup()[0].state.external_list_cache_entry.ttl == 10
    monkeypatch.delenv('OMI_EXTERNAL_LIST_POLLING_CACHE_ENABLED')
    assert lookup()[0].state.external_list_cache_entry.ttl == 10
    monkeypatch.setenv('OMI_EXTERNAL_LIST_POLLING_CACHE_ENABLED', 'true')
    assert lookup(path='/v1/mcp/memories')[0].state.external_list_cache_entry.ttl == 10


@pytest.mark.parametrize('percent', ['0', 'invalid', '-1', '101'])
def test_closed_or_invalid_cohort_performs_no_polling_io(polling, monkeypatch, percent):
    client, _ = polling
    monkeypatch.setenv('OMI_EXTERNAL_LIST_POLLING_CACHE_PERCENT', percent)
    evaluate = Mock()
    monkeypatch.setattr(client, 'eval', evaluate)
    request, _, _ = lookup()
    assert request.state.external_list_cache_entry.ttl == 10
    assert policy.negative_key(request, 'owner', None, 'missing') is None
    evaluate.assert_not_called()


def test_pages_filters_and_cursors_do_not_inherit_another_querys_cadence(polling):
    client, now = polling
    request, _, _ = lookup()
    context = SimpleNamespace(app_id='app', key_id='key')
    for moment in [1000, 1020, 1040]:
        now[0] = moment
        ttl = policy.adaptive_ttl(client, request, 'owner', context, {'limit': 25})
    assert ttl == 60
    assert policy.adaptive_ttl(client, request, 'owner', context, {'limit': 30}) == 10
    assert policy.adaptive_ttl(client, request, 'owner', context, {'limit': 25, 'cursor': 'opaque'}) == 10


def test_negative_entries_are_isolated_bounded_and_contain_no_identifiers(polling):
    client, now = polling
    request, _, _ = lookup()
    context = SimpleNamespace(app_id='app', key_id='key')
    first = policy.negative_key(request, 'owner', context, 'missing-item')
    second = policy.negative_key(request, 'owner', context, 'other-item')
    policy.remember_missing(client, first)
    assert policy.missing(client, first) and not policy.missing(client, second)
    assert all(value not in first.key for value in ['owner', 'synthetic', 'missing-item'])
    now[0] += 11
    assert not policy.missing(client, first)


def test_late_negative_population_and_retained_expired_bytes_cannot_extend_absence(polling):
    client, now = polling
    request, _, _ = lookup()
    entry = policy.negative_key(request, 'owner', None, 'missing')
    now[0] += 11
    policy.remember_missing(client, entry)
    assert client.get(entry.key) is None
    client.set(entry.key, str(entry.expires_at).encode(), px=100000)
    assert not policy.missing(client, entry)
