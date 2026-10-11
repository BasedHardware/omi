"""Bounded flag lookup, rollback latency, and content-free failure diagnostics."""

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from posthog.request import APIError

from config.proactivity_v2 import ProactivityDenied
from utils import proactivity_flags as flags


@pytest.fixture
def cache(monkeypatch):
    now = [100.0]
    client = Mock()
    monkeypatch.setattr(flags, '_flag_cache', OrderedDict())
    monkeypatch.setattr(flags, '_next_warning_at', 0.0)
    monkeypatch.setattr(flags, 'time', SimpleNamespace(monotonic=lambda: now[0]))
    monkeypatch.setattr(flags, 'flag_client', Mock(return_value=client))
    return SimpleNamespace(now=now, client=client, lookup=client.get_feature_variants)


@pytest.mark.parametrize('value', [True, False])
def test_success_cache_hit_miss_expiry_and_rollback(cache, value):
    cache.lookup.return_value = {'proactivity_v2': value}
    assert flags.enabled('synthetic') is value
    cache.lookup.return_value = {'proactivity_v2': not value}
    cache.now[0] += 299
    assert flags.enabled('synthetic') is value
    assert cache.lookup.call_count == 1
    assert flags.enabled('another') is not value
    assert cache.lookup.call_count == 2
    cache.now[0] += 1
    assert flags.enabled('synthetic') is not value
    assert cache.lookup.call_count == 3


@pytest.mark.parametrize('response', [{}, {'proactivity_v2': None}, {'proactivity_v2': 'true'}, {'proactivity_v2': 1}])
def test_only_boolean_true_enables_and_negative_is_cached(cache, response):
    cache.lookup.return_value = response
    assert flags.enabled('synthetic') is False
    assert flags.enabled('synthetic') is False
    cache.lookup.assert_called_once_with('synthetic')


@pytest.mark.parametrize('error', [ConnectionError('private-response'), APIError(429, 'private-response')])
def test_error_cache_fails_closed_and_recovers_at_60_seconds(cache, error):
    cache.lookup.side_effect = [error, {'proactivity_v2': True}]
    for elapsed in (0, 59):
        cache.now[0] = 100 + elapsed
        with pytest.raises(ProactivityDenied, match='flag_unavailable'):
            flags.enabled('synthetic')
    assert cache.lookup.call_count == 1
    assert flags._flag_cache['synthetic'].error_type == type(error).__name__
    cache.now[0] = 160
    assert flags.enabled('synthetic') is True
    assert cache.lookup.call_count == 2


@pytest.mark.parametrize('response', [None, [], 'private-response'])
def test_invalid_response_uses_short_error_cache(cache, response):
    cache.lookup.return_value = response
    for _ in range(2):
        with pytest.raises(ProactivityDenied, match='flag_unavailable'):
            flags.enabled('synthetic')
    cache.lookup.assert_called_once()
    assert flags._flag_cache['synthetic'].expires_at == 160


def test_client_construction_failure_is_cached(cache):
    flags.flag_client.side_effect = ModuleNotFoundError('private-key')
    for _ in range(2):
        with pytest.raises(ProactivityDenied, match='flag_unavailable'):
            flags.enabled('synthetic')
    flags.flag_client.assert_called_once()
    cache.lookup.assert_not_called()


@pytest.mark.parametrize('error', [False, True])
def test_lru_bounds_successes_and_errors(cache, monkeypatch, error):
    monkeypatch.setattr(flags, 'MAX_CACHE_ENTRIES', 2)
    cache.lookup.return_value = {'proactivity_v2': True}
    if error:
        cache.lookup.side_effect = ConnectionError('private-response')

    def resolve(uid):
        if error:
            with pytest.raises(ProactivityDenied):
                flags.enabled(uid)
        else:
            assert flags.enabled(uid) is True

    for uid in ('first', 'second', 'first', 'third'):
        resolve(uid)
    assert list(flags._flag_cache) == ['first', 'third']
    assert cache.lookup.call_count == 3
    resolve('second')
    assert len(flags._flag_cache) == 2
    assert cache.lookup.call_count == 4


@pytest.mark.parametrize('error', [False, True])
def test_concurrent_same_user_misses_share_one_request(cache, error):
    start = Barrier(9)
    requested, release = Event(), Event()

    def lookup(uid):
        requested.set()
        assert release.wait(5)
        if error:
            raise ConnectionError('private-response')
        return {'proactivity_v2': True}

    def resolve():
        start.wait(5)
        if error:
            with pytest.raises(ProactivityDenied):
                flags.enabled('synthetic')
            return False
        return flags.enabled('synthetic')

    cache.lookup.side_effect = lookup
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(resolve) for _ in range(8)]
        start.wait(5)
        try:
            assert requested.wait(5)
        finally:
            release.set()
        assert [future.result(timeout=5) for future in futures] == [not error] * 8
    cache.lookup.assert_called_once_with('synthetic')


@pytest.mark.parametrize('status,expected', [(429, '429'), ('503', '503'), ('private-response', 'unknown')])
def test_cohort_diagnostics_type_status_privacy_and_rate_limit(cache, monkeypatch, caplog, status, expected):
    monkeypatch.setenv('MENTOR_PIPELINE', 'cohort')
    cache.lookup.side_effect = APIError(status, 'private-response private-key')
    # Flag errors deny (fail closed) instead of selecting the deleted legacy lane.
    for uid in ('private-uid', 'private-uid', 'another-private-uid'):
        with pytest.raises(ProactivityDenied, match='flag_unavailable'):
            flags.mentor_pipeline(uid)
    warnings = [record.message for record in caplog.records]
    assert warnings == [f'proactivity_v2_flag_unavailable error_type=APIError http_status={expected}']
    assert 'private' not in caplog.text
    cache.now[0] += 60
    with pytest.raises(ProactivityDenied, match='flag_unavailable'):
        flags.mentor_pipeline('private-uid')
    assert len(caplog.records) == 2


@pytest.mark.parametrize('value', [True, False])
def test_cohort_resolves_v2_only_for_flagged_users(cache, monkeypatch, value):
    monkeypatch.setenv('MENTOR_PIPELINE', 'cohort')
    cache.lookup.return_value = {'proactivity_v2': value}
    assert flags.mentor_pipeline('synthetic') == ('v2' if value else None)
    cache.lookup.assert_called_once_with('synthetic')


@pytest.mark.parametrize('pipeline', ['legacy', 'v2', 'typo', None])
def test_non_cohort_env_denies_without_flag_lookup(cache, monkeypatch, pipeline):
    if pipeline is None:
        monkeypatch.delenv('MENTOR_PIPELINE', raising=False)
    else:
        monkeypatch.setenv('MENTOR_PIPELINE', pipeline)
    assert flags.mentor_pipeline('synthetic') is None
    cache.lookup.assert_not_called()


@pytest.mark.parametrize('value', [True, False, 'error'])
def test_cache_hit_does_not_wait_for_colliding_network_lookup(cache, monkeypatch, value):
    monkeypatch.setattr(flags, '_lookup_locks', (Lock(),))
    cache.lookup.return_value = {'proactivity_v2': value}
    if value == 'error':
        cache.lookup.side_effect = ConnectionError('private-response')
        with pytest.raises(ProactivityDenied):
            flags.enabled('cached')
    else:
        assert flags.enabled('cached') is value
    requested, release = Event(), Event()

    def lookup(uid):
        requested.set()
        assert release.wait(5)
        return {'proactivity_v2': True}

    def cached():
        if value == 'error':
            with pytest.raises(ProactivityDenied):
                flags.enabled('cached')
            return 'error'
        return flags.enabled('cached')

    cache.lookup.side_effect = lookup
    with ThreadPoolExecutor(max_workers=2) as executor:
        miss = executor.submit(flags.enabled, 'uncached')
        try:
            assert requested.wait(5)
            hit = executor.submit(cached)
            assert hit.result(timeout=1) == value
        finally:
            release.set()
        assert miss.result(timeout=5) is True
    assert cache.lookup.call_count == 2


def test_non_api_error_diagnostic_includes_exception_type(cache, caplog):
    cache.lookup.side_effect = TimeoutError('private-response')
    with pytest.raises(ProactivityDenied):
        flags.enabled('private-uid')
    assert 'error_type=TimeoutError http_status=unknown' in caplog.text
    assert 'private' not in caplog.text


@pytest.mark.parametrize('raw', ['phc_token\n', '  phc_token \r\n'])
def test_flag_client_reads_only_dedicated_token_and_strips_whitespace(monkeypatch, raw):
    constructed = {}

    class FakePosthog:
        def __init__(self, **kwargs):
            constructed.update(kwargs)

    monkeypatch.setenv('PROACTIVITY_V2_POSTHOG_TOKEN', raw)
    monkeypatch.setenv('POSTHOG_PROJECT_API_KEY', 'disabled')
    monkeypatch.setenv('POSTHOG_API_KEY', 'shared-key-must-not-be-read')
    monkeypatch.setenv('PROACTIVITY_V2_POSTHOG_HOST', 'https://us.posthog.com\n')
    monkeypatch.setenv('POSTHOG_HOST', 'https://shared-host.invalid')
    monkeypatch.setattr(flags.importlib, 'import_module', lambda name: SimpleNamespace(Posthog=FakePosthog))
    flags.flag_client.cache_clear()
    try:
        flags.flag_client()
    finally:
        flags.flag_client.cache_clear()
    assert constructed['project_api_key'] == 'phc_token'
    assert constructed['host'] == 'https://us.posthog.com'


@pytest.mark.parametrize('raw', [None, '', ' \n', 'disabled', 'phx_personal-key', 'private-token'])
def test_unavailable_dedicated_token_never_falls_back_and_logs_once(monkeypatch, caplog, raw):
    if raw is None:
        monkeypatch.delenv('PROACTIVITY_V2_POSTHOG_TOKEN', raising=False)
    else:
        monkeypatch.setenv('PROACTIVITY_V2_POSTHOG_TOKEN', raw)
    # Even usable shared keys cannot grant v2 admission.
    monkeypatch.setenv('POSTHOG_PROJECT_API_KEY', 'phc_shared-project')
    monkeypatch.setenv('POSTHOG_API_KEY', 'phc_shared-legacy')
    monkeypatch.setenv('MENTOR_PIPELINE', 'cohort')
    factory = Mock()
    monkeypatch.setattr(flags, 'importlib', SimpleNamespace(import_module=factory))
    monkeypatch.setattr(flags, '_flag_cache', OrderedDict())
    monkeypatch.setattr(flags, '_next_warning_at', 0.0)
    now = [100.0]
    monkeypatch.setattr(flags, 'time', SimpleNamespace(monotonic=lambda: now[0]))
    flags.flag_client.cache_clear()
    try:
        with pytest.raises(ProactivityDenied, match='flag_unavailable'):
            flags.flag_client()
        for uid in ('private-uid', 'private-uid', 'another-private-uid'):
            with pytest.raises(ProactivityDenied, match='flag_unavailable'):
                flags.enabled(uid)
        with pytest.raises(ProactivityDenied, match='flag_unavailable'):
            flags.mentor_pipeline('private-uid')
        assert len(caplog.records) == 1
        assert (
            caplog.records[0].message
            == 'proactivity_v2_flag_unavailable error_type=ProactivityDenied http_status=unknown'
        )
        assert 'private' not in caplog.text and 'phc_' not in caplog.text
        now[0] += 60
        with pytest.raises(ProactivityDenied, match='flag_unavailable'):
            flags.enabled('private-uid')
        assert len(caplog.records) == 2
        factory.assert_not_called()
    finally:
        flags.flag_client.cache_clear()


@pytest.mark.parametrize('host', [None, '', ' \n', ' https://flag-host.invalid/ \n'])
def test_flag_client_dedicated_host_and_us_default(monkeypatch, host):
    monkeypatch.setenv('PROACTIVITY_V2_POSTHOG_TOKEN', 'phc_token')
    monkeypatch.setenv('POSTHOG_HOST', 'https://shared-host.invalid')
    if host is None:
        monkeypatch.delenv('PROACTIVITY_V2_POSTHOG_HOST', raising=False)
    else:
        monkeypatch.setenv('PROACTIVITY_V2_POSTHOG_HOST', host)
    factory = Mock()
    monkeypatch.setattr(
        flags, 'importlib', SimpleNamespace(import_module=lambda name: SimpleNamespace(Posthog=factory))
    )
    flags.flag_client.cache_clear()
    try:
        flags.flag_client()
        factory.assert_called_once_with(
            project_api_key='phc_token',
            host=(host or '').strip() or 'https://us.posthog.com',
            send=False,
            sync_mode=True,
            feature_flags_request_timeout_seconds=2,
        )
    finally:
        flags.flag_client.cache_clear()
