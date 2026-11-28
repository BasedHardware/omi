"""Omi flag store: evaluation, snapshot refresh/fallback, /v1/flags, proactivity_v2 source switch, CLI rules."""

import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from posthog.feature_flags import _hash as posthog_hash

from config.proactivity_v2 import ProactivityDenied
from routers import omi_flags as flags_router
from database import omi_flags as omi_flags_store
from scripts import omi_flags as cli
from utils import omi_flags, proactivity_flags
from utils.omi_flag_metrics import OMI_FLAG_DUAL_READ_TOTAL
from utils.other.endpoints import get_current_user_uid


def rule(key='k', **doc):
    return omi_flags.FlagRule.from_doc(key, {'active': True, 'rollout_percentage': 100, **doc})


class FakeStore:
    def __init__(self, version=1, docs=None):
        self.version = version
        self.docs = docs or {}
        self.redis = None
        self.fail = False
        self.reads = 0
        self.configured = True
        self.client_error = None

    def store_target(self):
        return ('flags-project', '(default)') if self.configured else None

    def flags_client(self):
        if self.client_error:
            raise self.client_error
        return object() if self.configured else None

    def read_version(self, _client):
        if self.fail:
            raise TimeoutError('slow store')
        return self.version

    def read_all(self, _client):
        if self.fail:
            raise TimeoutError('slow store')
        self.reads += 1
        return self.version, dict(self.docs)

    def read_redis_version(self):
        return self.redis


@pytest.fixture
def store(monkeypatch):
    fake = FakeStore(docs={'proactivity_v2': {'active': True, 'rollout_percentage': 100, 'surfaces': ['backend']}})
    now = [1000.0]
    monkeypatch.setattr(omi_flags, 'store', fake)
    monkeypatch.setattr(omi_flags, 'time', SimpleNamespace(monotonic=lambda: now[0]))
    monkeypatch.setattr(omi_flags, '_cache', omi_flags._SnapshotCache())
    fake.now = now
    return fake


def test_rollout_hash_matches_posthog_so_imported_cohorts_do_not_move():
    for uid in ('uid-a', 'uid-b', 'Zx81'):
        assert omi_flags.rollout_hash('screen_activity_lossless_sync', uid) == posthog_hash(
            'screen_activity_lossless_sync', uid
        )


def test_evaluate_kill_deny_allow_and_percentage():
    assert omi_flags.evaluate(rule(active=False), 'u') == omi_flags.Resolved(False)
    assert omi_flags.evaluate(rule(deny_uids=['u']), 'u').enabled is False
    assert omi_flags.evaluate(rule(rollout_percentage=0, allow_uids=['u']), 'u').enabled is True
    assert omi_flags.evaluate(rule(rollout_percentage=0), 'u').enabled is False
    uids = [f'u{i}' for i in range(2000)]
    share = sum(omi_flags.evaluate(rule(rollout_percentage=25), u).enabled for u in uids) / len(uids)
    assert 0.2 < share < 0.3


def test_variant_and_payload_only_when_on():
    on = rule(variant='b', payload='{"x": 1}')
    assert omi_flags.evaluate(on, 'u') == omi_flags.Resolved(True, 'b', '{"x": 1}')
    off = rule(variant='b', payload='{"x": 1}', active=False)
    assert omi_flags.evaluate(off, 'u') == omi_flags.Resolved(False)


@pytest.mark.parametrize('platform', ['ios', 'android', None, 'macos'])
def test_empty_platforms_preserve_legacy_evaluation(platform):
    legacy = rule(rollout_percentage=5, variant='b', payload='{}', allow_uids=['allow'], deny_uids=['deny'])
    explicit_empty = rule(
        rollout_percentage=5, variant='b', payload='{}', allow_uids=['allow'], deny_uids=['deny'], platforms=[]
    )
    for uid in ('allow', 'deny', *(f'preview-{n}' for n in range(100))):
        assert omi_flags.evaluate(explicit_empty, uid, platform) == omi_flags.evaluate(legacy, uid)


@pytest.mark.parametrize('platform,enabled', [('ios', True), ('android', False), (None, False), ('macos', False)])
def test_evaluate_ios_target_and_uid_overrides(platform, enabled):
    targeted = rule(platforms=['ios'], allow_uids=['allowed', 'denied'], deny_uids=['denied'])
    canary = rule(platforms=['ios'], rollout_percentage=0, allow_uids=['allowed'])
    assert omi_flags.evaluate(targeted, 'bucketed', platform).enabled is enabled
    assert omi_flags.evaluate(targeted, 'denied', platform) == omi_flags.Resolved(False)
    assert omi_flags.evaluate(canary, 'allowed', platform).enabled is enabled
    assert omi_flags.evaluate(canary, 'bucketed', platform) == omi_flags.Resolved(False)


@pytest.mark.parametrize('platforms', [['windows'], ['IOS'], ['ios', None], 'ios', None])
def test_invalid_platforms_rejected_before_parsing_or_writing(platforms):
    with pytest.raises(ValueError, match='platforms'):
        rule(platforms=platforms)
    with pytest.raises(ValueError, match='platforms'):
        cli.merge_rule({'platforms': platforms}, ENTRY, {})
    client = Mock()
    with pytest.raises(ValueError, match='platforms'):
        omi_flags_store.write_rule(client, 'k', {'platforms': platforms}, actor='t', reason='r')
    assert not client.mock_calls


def test_from_doc_clamps_and_ignores_garbage():
    parsed = omi_flags.FlagRule.from_doc('k', {'active': 'true', 'rollout_percentage': 250, 'variant': 3})
    assert parsed.active is False and parsed.rollout_percentage == 100 and parsed.variant is None


def test_unconfigured_store_resolves_none(store):
    store.configured = False
    assert omi_flags.resolve('proactivity_v2', 'u') is None
    assert omi_flags.resolve_surface('u', 'macos') == (None, {})


def test_absent_key_is_none_so_callers_keep_their_source(store):
    assert omi_flags.resolve('not-migrated', 'u') is None
    assert omi_flags.resolve('proactivity_v2', 'u') == omi_flags.Resolved(True)


def test_refresh_polls_version_and_reloads_only_on_change(store):
    omi_flags.resolve('proactivity_v2', 'u')
    assert store.reads == 1
    store.now[0] += 59
    store.docs['proactivity_v2']['active'] = False
    assert omi_flags.resolve('proactivity_v2', 'u').enabled is True  # not due yet
    store.now[0] += 1
    assert omi_flags.resolve('proactivity_v2', 'u').enabled is True  # version unchanged: no reload
    assert store.reads == 1
    store.version = 2
    store.now[0] += 60
    assert omi_flags.resolve('proactivity_v2', 'u').enabled is False
    assert store.reads == 2


def test_redis_signal_reloads_before_the_store_poll(store):
    omi_flags.resolve('proactivity_v2', 'u')
    store.version = store.redis = 2
    store.docs['proactivity_v2']['active'] = False
    store.now[0] += 15
    assert omi_flags.resolve('proactivity_v2', 'u').enabled is False


def test_store_failure_keeps_last_known_good(store, monkeypatch):
    recorded = Mock()
    monkeypatch.setattr(omi_flags, 'record_fallback', recorded)
    omi_flags.resolve('proactivity_v2', 'u')
    store.fail = True
    store.now[0] += 60
    assert omi_flags.resolve('proactivity_v2', 'u') == omi_flags.Resolved(True)
    assert recorded.call_args.kwargs['to_mode'] == 'last_known_good'


def test_invalid_platforms_disable_only_that_rule_and_allow_refresh(store, monkeypatch):
    recorded = Mock()
    monkeypatch.setattr(omi_flags, 'record_fallback', recorded)
    store.docs = {
        'targeted': {'active': True, 'rollout_percentage': 100, 'surfaces': ['mobile'], 'platforms': ['ios']},
        'legacy': {'active': False, 'surfaces': ['mobile']},
    }
    assert omi_flags.resolve_surface('u', 'mobile', 'ios')[1]['targeted'] == omi_flags.Resolved(True)
    store.docs['targeted']['platforms'] = ['invalid']
    store.docs['legacy'].update(active=True, rollout_percentage=100)
    store.version = 2
    store.now[0] += 60
    assert omi_flags.resolve_surface('u', 'mobile', 'ios') == (
        2,
        {'legacy': omi_flags.Resolved(True), 'targeted': omi_flags.Resolved(False)},
    )
    assert recorded.call_args.kwargs['failure_subtype'] == 'invalid_rule_platforms'


def test_client_construction_failure_degrades_like_a_read_failure(store, monkeypatch):
    recorded = Mock()
    monkeypatch.setattr(omi_flags, 'record_fallback', recorded)
    store.client_error = ValueError('no default credentials')
    assert omi_flags.resolve('proactivity_v2', 'u') is None
    assert recorded.call_args.kwargs['to_mode'] == 'none'
    store.client_error = None
    store.now[0] += 60
    assert omi_flags.resolve('proactivity_v2', 'u') == omi_flags.Resolved(True)


def test_first_load_failure_resolves_none(store, monkeypatch):
    monkeypatch.setattr(omi_flags, 'record_fallback', Mock())
    store.fail = True
    assert omi_flags.resolve('proactivity_v2', 'u') is None


def test_client_flags_endpoint_filters_by_surface(store):
    store.docs = {
        'mac-on': {'active': True, 'rollout_percentage': 100, 'surfaces': ['macos'], 'payload': '{"a":1}'},
        'mac-off': {'active': False, 'surfaces': ['macos', 'mobile']},
        'mobile-only': {'active': True, 'rollout_percentage': 100, 'surfaces': ['mobile']},
    }
    app = FastAPI()
    app.include_router(flags_router.router)
    app.dependency_overrides[get_current_user_uid] = lambda: 'u'
    response = TestClient(app).get('/v1/flags', params={'surface': 'macos'})
    assert response.status_code == 200
    assert response.json() == {
        'version': 1,
        'flags': [
            {'key': 'mac-off', 'enabled': False, 'variant': None, 'payload_json': None},
            {'key': 'mac-on', 'enabled': True, 'variant': None, 'payload_json': '{"a":1}'},
        ],
    }
    assert TestClient(app).get('/v1/flags', params={'surface': 'backend'}).status_code == 422


@pytest.mark.parametrize(
    'platform_headers,enabled',
    [
        pytest.param((), False, id='missing'),
        pytest.param(('',), False, id='empty'),
        pytest.param(('macos',), False, id='macos'),
        pytest.param(('fuchsia',), False, id='fuchsia'),
        pytest.param(('iOS',), False, id='mixed-case'),
        pytest.param(('IOS',), False, id='uppercase'),
        pytest.param((' ios',), False, id='leading-space'),
        pytest.param(('ios ',), False, id='trailing-space'),
        pytest.param(('ios,android',), False, id='comma-separated'),
        pytest.param(('ios', 'android'), False, id='repeated-different'),
        pytest.param(('ios', 'ios'), False, id='repeated-identical'),
        pytest.param(('ios',), True, id='ios'),
        pytest.param(('android',), False, id='android'),
    ],
)
def test_client_flags_endpoint_requires_one_exact_platform(store, platform_headers, enabled):
    store.docs = {'ios-only': {'active': True, 'rollout_percentage': 100, 'surfaces': ['mobile'], 'platforms': ['ios']}}
    app = FastAPI()
    app.include_router(flags_router.router)
    app.dependency_overrides[get_current_user_uid] = lambda: 'u'
    headers = [('X-App-Platform', value) for value in platform_headers]
    response = TestClient(app).get('/v1/flags', params={'surface': 'mobile'}, headers=headers)
    assert response.status_code == 200
    assert response.json() == {
        'version': 1,
        'flags': [{'key': 'ios-only', 'enabled': enabled, 'variant': None, 'payload_json': None}],
    }


def test_legacy_client_flags_use_percentage_without_platform_header(store):
    legacy_rule = {'active': True, 'rollout_percentage': 50, 'surfaces': ['mobile']}
    store.docs = {'legacy-a': legacy_rule, 'legacy-b': legacy_rule}
    app = FastAPI()
    app.include_router(flags_router.router)
    app.dependency_overrides[get_current_user_uid] = lambda: 'u'
    response = TestClient(app).get('/v1/flags', params={'surface': 'mobile'})
    assert response.status_code == 200
    # uid "u" buckets below 50% for legacy-a and above 50% for legacy-b.
    assert {flag['key']: flag['enabled'] for flag in response.json()['flags']} == {'legacy-a': True, 'legacy-b': False}


def test_legacy_client_flag_response_is_byte_identical_across_platforms(store):
    store.docs = {
        'off': {'active': True, 'rollout_percentage': 100, 'surfaces': ['mobile'], 'deny_uids': ['u'], 'payload': '{}'},
        'on': {'active': True, 'surfaces': ['mobile'], 'allow_uids': ['u'], 'variant': 'b', 'payload': '{}'},
    }
    app = FastAPI()
    app.include_router(flags_router.router)
    app.dependency_overrides[get_current_user_uid] = lambda: 'u'
    client = TestClient(app)
    expected = (
        b'{"version":1,"flags":[{"key":"off","enabled":false,"variant":null,"payload_json":null},'
        b'{"key":"on","enabled":true,"variant":"b","payload_json":"{}"}]}'
    )
    for headers in ({}, {'X-App-Platform': 'ios'}, {'X-App-Platform': 'android'}, {'X-App-Platform': 'unknown'}):
        response = client.get('/v1/flags', params={'surface': 'mobile'}, headers=headers)
        assert response.status_code == 200
        assert response.content == expected


def _dual_count(outcome):
    return OMI_FLAG_DUAL_READ_TOTAL.labels(flag='proactivity_v2', outcome=outcome)._value.get()


def test_dual_read_scrape_exports_all_outcomes_before_any_evaluation():
    # A fresh process proves startup registration without creating children in
    # the test or inheriting comparisons performed by another test.
    result = subprocess.run(
        [
            sys.executable,
            '-c',
            'from utils.metrics import metrics_response; print(metrics_response().body.decode())',
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    samples = {line for line in result.stdout.splitlines() if line.startswith('omi_flag_dual_read_total{')}
    assert samples == {
        f'omi_flag_dual_read_total{{flag="proactivity_v2",outcome="{outcome}"}} 0.0'
        for outcome in ('match', 'mismatch', 'omi_absent', 'omi_error')
    }


def test_flag_metric_import_preserves_created_series_for_other_collectors():
    # Exercise this module independently of the shared exporter's existing policy.
    result = subprocess.run(
        [
            sys.executable,
            '-c',
            'from utils import omi_flag_metrics; '
            'from prometheus_client import Counter, generate_latest; '
            'Counter("unrelated_probe_total", "Unrelated collector"); '
            'print(generate_latest().decode())',
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert 'unrelated_probe_created ' in result.stdout


def test_proactivity_default_source_is_posthog(store, monkeypatch):
    monkeypatch.delenv('OMI_FLAGS_SOURCE', raising=False)
    monkeypatch.setattr(proactivity_flags, '_posthog_enabled', Mock(return_value=False))
    assert proactivity_flags.enabled('u') is False
    assert store.reads == 0


@pytest.mark.parametrize('posthog_value,outcome', [(True, 'match'), (False, 'mismatch')])
def test_proactivity_dual_serves_posthog_and_counts(store, monkeypatch, posthog_value, outcome):
    monkeypatch.setenv('OMI_FLAGS_SOURCE', 'dual')
    monkeypatch.setattr(proactivity_flags, '_posthog_enabled', Mock(return_value=posthog_value))
    before = _dual_count(outcome)
    assert proactivity_flags.enabled('u') is posthog_value
    assert _dual_count(outcome) == before + 1


def test_proactivity_omi_source_and_absent_fails_closed(store, monkeypatch):
    monkeypatch.setenv('OMI_FLAGS_SOURCE', 'omi')
    posthog = Mock(side_effect=AssertionError('PostHog must not be called'))
    monkeypatch.setattr(proactivity_flags, '_posthog_enabled', posthog)
    monkeypatch.setattr(proactivity_flags, '_next_warning_at', 0.0)
    assert proactivity_flags.enabled('u') is True
    store.docs = {}
    store.version = 2
    store.now[0] += 60
    with pytest.raises(ProactivityDenied, match='flag_unavailable'):
        proactivity_flags.enabled('u')


ENTRY = {'key': 'k', 'surfaces': ['macos'], 'lifecycle': 'rollout'}
MOBILE_ENTRY = {**ENTRY, 'surfaces': ['mobile']}


def test_posthog_import_converts_only_simple_rows():
    row = {'key': 'k', 'active': True, 'filters': {'groups': [{'properties': [], 'rollout_percentage': 10}]}}
    converted, _ = cli.rule_from_posthog_row(row, ENTRY)
    assert converted['rollout_percentage'] == 10 and converted['surfaces'] == ['macos']
    whole = {'key': 'k', 'active': True, 'filters': {'groups': [{'properties': []}], 'payloads': {'true': {'a': 1}}}}
    converted, _ = cli.rule_from_posthog_row(whole, ENTRY)
    assert converted['rollout_percentage'] == 100 and json.loads(converted['payload']) == {'a': 1}
    for blocked in (
        {**row, 'active': False},
        {'active': True, 'filters': {'groups': [{'properties': [{'key': 'email'}], 'rollout_percentage': 100}]}},
        {'active': True, 'filters': {'groups': [{'properties': []}], 'multivariate': {'variants': [{'key': 'a'}]}}},
    ):
        assert cli.rule_from_posthog_row(blocked, ENTRY)[0] is None
    assert cli.rule_from_posthog_row(row, {**ENTRY, 'lifecycle': 'experiment'})[0] is None


def test_mirror_keeps_kill_rows_active_at_zero_and_refuses_what_posthog_cannot_express():
    row = {'key': 'k', 'filters': {'groups': [{'properties': [], 'rollout_percentage': 100}]}}
    killed = cli.merge_rule(None, ENTRY, {'active': False})
    assert cli.posthog_mirror_body(row, killed) == {
        'active': True,
        'filters': {'groups': [{'properties': [], 'rollout_percentage': 0}], 'payloads': {}},
    }
    with_payload = {**row, 'filters': {**row['filters'], 'payloads': {'true': '{"v":1}'}}}
    ramped = cli.merge_rule(None, ENTRY, {'active': True, 'rollout_percentage': 50, 'payload': '{"v":2}'})
    assert cli.posthog_mirror_body(with_payload, ramped)['filters']['payloads'] == {'true': '{"v":2}'}
    with pytest.raises(cli.FlagCliError):
        cli.posthog_mirror_body(row, {**killed, 'allow_uids': ['u']})


def test_merge_rule_validates_and_copies_registry_surfaces():
    merged = cli.merge_rule(
        {'active': True, 'rollout_percentage': 5, 'surfaces': ['old']}, ENTRY, {'rollout_percentage': 50}
    )
    assert merged['active'] is True and merged['rollout_percentage'] == 50 and merged['surfaces'] == ['macos']
    with pytest.raises(cli.FlagCliError):
        cli.merge_rule(None, ENTRY, {'rollout_percentage': 101})
    with pytest.raises(ValueError):
        cli.merge_rule(None, ENTRY, {'payload': 'not json'})


def test_merge_rule_preserves_platforms_unless_replaced_or_cleared():
    current = {'platforms': ['ios']}
    assert cli.merge_rule(current, MOBILE_ENTRY, {'rollout_percentage': 10})['platforms'] == ['ios']
    assert cli.merge_rule(current, MOBILE_ENTRY, {'platforms': ['ios', 'android']})['platforms'] == ['ios', 'android']
    assert cli.merge_rule(current, MOBILE_ENTRY, {'platforms': []})['platforms'] == []
    assert current == {'platforms': ['ios']}


@pytest.mark.parametrize('surfaces', [['macos'], ['backend', 'mobile']])
def test_merge_rule_refuses_platform_targeting_for_non_mobile_only_keys(surfaces):
    with pytest.raises(cli.FlagCliError, match='requires a mobile-only flag'):
        cli.merge_rule(None, {**ENTRY, 'surfaces': surfaces}, {'platforms': ['ios']})


def test_set_refuses_platform_targeted_mirror_before_external_checks(monkeypatch, capsys):
    monkeypatch.setattr(cli, 'load_registry', lambda: {'k': MOBILE_ENTRY})
    monkeypatch.setattr(cli, '_client', lambda args: object())
    monkeypatch.setattr(cli.store, 'read_all', lambda client: (1, {'k': {'platforms': ['ios']}}))
    require, posthog, write = Mock(), Mock(), Mock()
    monkeypatch.setattr(cli.live_preflight, 'require', require)
    monkeypatch.setattr(cli, 'posthog_rows', posthog)
    monkeypatch.setattr(cli.store, 'write_rule', write)
    assert cli.main(['set', 'k', '--rollout', '5', '--reason', 'ramp', '--yes', '--mirror-posthog']) == 2
    assert 'platform targeting cannot be mirrored' in capsys.readouterr().err
    require.assert_not_called()
    posthog.assert_not_called()
    write.assert_not_called()


def test_preview_reads_once_and_never_writes_or_prints_stored_uids(monkeypatch, capsys):
    current = {'active': False, 'allow_uids': ['stored-allow'], 'deny_uids': ['stored-deny']}
    key = 'mobile-batch-upload-hold'
    client = object()
    read = Mock(return_value=(3, {key: current}))
    write, publish, require = Mock(), Mock(), Mock()
    monkeypatch.setattr(cli, '_client', lambda args: client)
    monkeypatch.setattr(cli.store, 'read_all', read)
    monkeypatch.setattr(cli.store, 'write_rule', write)
    monkeypatch.setattr(cli.store, 'publish_redis_version', publish)
    monkeypatch.setattr(cli.live_preflight, 'require', require)
    assert cli.main(['preview', key, '--active', '--rollout', '5', '--platforms', 'ios']) == 0
    read.assert_called_once_with(client)
    write.assert_not_called()
    publish.assert_not_called()
    require.assert_not_called()
    assert current == {'active': False, 'allow_uids': ['stored-allow'], 'deny_uids': ['stored-deny']}
    output = capsys.readouterr().out
    assert 'stored-allow' not in output and 'stored-deny' not in output
    preview = json.loads(output)
    assert preview['rule']['key'] == key
    assert preview['rule']['platforms'] == ['ios']
    assert preview['rule']['active'] is True
    assert preview['rule']['rollout_percentage'] == 5
    assert preview['rule']['allow_count'] == preview['rule']['deny_count'] == 1
    assert preview['synthetic_uid_count'] == 10_000
    expected_ios = sum(posthog_hash(key, f'preview-{n}') < 0.05 for n in range(10_000))
    assert preview['exposure'] == {
        'ios': {'enabled': expected_ios, 'percentage': expected_ios / 100},
        'android': {'enabled': 0, 'percentage': 0},
        'missing_header': {'enabled': 0, 'percentage': 0},
    }


@pytest.mark.parametrize('options', [['--platforms', 'ios', 'android'], ['--all-platforms']])
def test_set_platform_expansion_requires_live_preflight(monkeypatch, options):
    current = {'active': True, 'rollout_percentage': 100, 'platforms': ['ios']}
    monkeypatch.setattr(cli, 'load_registry', lambda: {'k': MOBILE_ENTRY})
    monkeypatch.setattr(cli, '_client', lambda args: object())
    monkeypatch.setattr(cli.store, 'read_all', lambda client: (1, {'k': current}))
    require = Mock(side_effect=SystemExit(4))
    write = Mock()
    monkeypatch.setattr(cli.live_preflight, 'require', require)
    monkeypatch.setattr(cli, '_write', write)
    with pytest.raises(SystemExit) as error:
        cli.main(['set', 'k', *options, '--reason', 'expand', '--yes'])
    assert error.value.code == 4
    require.assert_called_once_with('k', 100, None)
    write.assert_not_called()


@pytest.fixture(scope='module')
def registry_rows():
    # Real manifest loading is setup; the call-phase guard measures refusal logic.
    return cli.load_registry()


def test_registry_refuses_unknown_keys_and_experiments(registry_rows):
    registry = registry_rows
    assert registry['proactivity_v2']['surfaces'] == ['backend', 'llm-gateway']
    with pytest.raises(cli.FlagCliError):
        cli.registry_entry(registry, 'paywall-variant')
    with pytest.raises(cli.FlagCliError):
        cli.registry_entry(registry, 'not-a-flag')


@pytest.mark.parametrize('force_python', [False, True])
def test_registry_safe_parsers_preserve_posthog_filtering(tmp_path, monkeypatch, force_python):
    if force_python:
        monkeypatch.setattr(yaml, '__with_libyaml__', False)
    path = tmp_path / 'flags.yaml'
    path.write_text(
        "flags:\n  - {key: visible, kind: posthog, surfaces: [backend, llm-gateway]}\n"
        "  - {key: compute_floor, kind: env, surfaces: [backend]}\n"
    )
    assert cli.load_registry(path) == {
        'visible': {'key': 'visible', 'kind': 'posthog', 'surfaces': ['backend', 'llm-gateway']}
    }


@pytest.mark.parametrize('force_python', [False, True])
def test_registry_safe_parsers_reject_python_constructor_tags(tmp_path, monkeypatch, force_python):
    if force_python:
        monkeypatch.setattr(yaml, '__with_libyaml__', False)
    path = tmp_path / 'flags.yaml'
    path.write_text("!!python/object/apply:builtins.str ['unsafe']")
    with pytest.raises(yaml.constructor.ConstructorError):
        cli.load_registry(path)


@pytest.mark.parametrize(
    'old,new,active,inactive,gated',
    [
        (0, 5, False, False, True),
        (5, 25, False, False, True),
        (25, 5, True, False, 'mixed'),
        (25, 5, False, False, False),
        (25, 100, False, True, 'mixed'),
        (25, 25, False, True, False),
        (25, 25, False, False, False),
        (25, 25, True, False, True),
    ],
)
def test_cli_raise_matrix_and_rollback_without_any_prod_preflight_read(monkeypatch, old, new, active, inactive, gated):
    current = {'active': not active, 'rollout_percentage': old}
    monkeypatch.setattr(cli, 'load_registry', lambda: {'k': ENTRY})
    monkeypatch.setattr(cli, '_client', lambda args: object())
    monkeypatch.setattr(cli.store, 'read_all', lambda client: (1, {'k': current}))
    writer = Mock()
    monkeypatch.setattr(cli, '_write', writer)
    # Every preflight read fails; rollback paths must never reach even the prover.
    check = Mock(side_effect=SystemExit(4))
    monkeypatch.setattr(cli.live_preflight, 'require', check)
    args = ['set', 'k', '--rollout', str(new), '--reason', 'ramp', '--yes']
    if active:
        args.append('--active')
    if inactive:
        args.append('--inactive')
    if gated == 'mixed':
        assert cli.main(args) == 2
        check.assert_not_called()
        writer.assert_not_called()
    elif gated:
        with pytest.raises(SystemExit) as error:
            cli.main(args)
        assert error.value.code == 4
        writer.assert_not_called()
    else:
        assert cli.main(args) == 0
        check.assert_not_called()
        writer.assert_called_once()


def test_cli_override_is_in_existing_audit_reason(monkeypatch):
    monkeypatch.setattr(cli, 'load_registry', lambda: {'k': ENTRY})
    monkeypatch.setattr(cli, '_client', lambda args: object())
    monkeypatch.setattr(cli.store, 'read_all', lambda client: (1, {'k': {'active': True, 'rollout_percentage': 5}}))
    monkeypatch.setattr(cli.live_preflight, 'require', Mock())
    writer = Mock()
    monkeypatch.setattr(cli, '_write', writer)
    reason = 'Approved deliberate exception'
    assert cli.main(['set', 'k', '--rollout', '25', '--reason', 'ramp', '--yes', '--accept-not-live', reason]) == 0
    assert writer.call_args.args[-1] == 'ramp accept_not_live:' + reason
    assert cli.main(['set', 'k', '--rollout', '25', '--reason', 'ramp', '--yes', '--accept-not-live', 'short']) == 2
    assert writer.call_count == 1


@pytest.mark.parametrize(
    'rule,gated',
    [
        ({'active': False, 'rollout_percentage': 100}, True),
        ({'active': True, 'rollout_percentage': 25}, True),
        ({'active': True, 'rollout_percentage': 100, 'deny_uids': ['denied']}, True),
        ({'active': True, 'rollout_percentage': 100}, False),
        ({'active': True, 'rollout_percentage': 100, 'allow_uids': ['allowed'], 'deny_uids': []}, False),
    ],
)
def test_delete_preflights_posthog_handoff_unless_already_fully_exposed(monkeypatch, rule, gated):
    monkeypatch.setattr(cli, '_client', lambda args: object())
    monkeypatch.setattr(cli.store, 'read_all', lambda client: (1, {'k': rule}))
    check = Mock(side_effect=None if gated else AssertionError('prod read'))
    monkeypatch.setattr(cli.live_preflight, 'require', check)
    writer = Mock()
    monkeypatch.setattr(cli, '_write', writer)
    assert cli.main(['delete', 'k', '--reason', 'handoff', '--yes']) == 0
    if gated:
        check.assert_called_once_with('k', 100)
    else:
        check.assert_not_called()
    writer.assert_called_once_with(writer.call_args.args[0], 'k', None, 'handoff', expected=rule)


@pytest.mark.parametrize('exit_code', [3, 4])
def test_delete_preflight_refusal_preserves_rule(monkeypatch, capsys, exit_code):
    rule = {'active': False, 'rollout_percentage': 25}
    docs = {'k': rule}
    monkeypatch.setattr(cli, '_client', lambda args: object())
    monkeypatch.setattr(cli.store, 'read_all', lambda client: (1, docs))
    monkeypatch.setattr(cli.live_preflight, 'require', Mock(side_effect=SystemExit(exit_code)))
    writer = Mock(side_effect=lambda client, key, after, reason, **kwargs: docs.pop(key))
    monkeypatch.setattr(cli, '_write', writer)
    with pytest.raises(SystemExit) as error:
        cli.main(['delete', 'k', '--reason', 'handoff', '--yes'])
    assert error.value.code == exit_code
    writer.assert_not_called()
    assert docs == {'k': rule}
    assert capsys.readouterr().out == ''


def test_posthog_import_apply_cannot_bypass_raise_preflight(monkeypatch):
    monkeypatch.setattr(cli, 'load_registry', lambda: {'k': ENTRY})
    monkeypatch.setattr(cli, '_client', lambda args: object())
    monkeypatch.setattr(cli.store, 'read_all', lambda client: (1, {}))
    monkeypatch.setattr(
        cli,
        'posthog_rows',
        lambda: {'k': {'key': 'k', 'active': True, 'filters': {'groups': [{'rollout_percentage': 25}]}}},
    )
    check = Mock(side_effect=SystemExit(3))
    writer = Mock()
    monkeypatch.setattr(cli.live_preflight, 'require', check)
    monkeypatch.setattr(cli, '_write', writer)
    assert cli.main(['import-posthog']) == 0
    check.assert_not_called()
    with pytest.raises(SystemExit) as error:
        cli.main(['import-posthog', '--apply'])
    assert error.value.code == 3
    writer.assert_not_called()


def test_percentage_raise_on_inactive_rule_is_still_gated(monkeypatch):
    monkeypatch.setattr(cli, 'load_registry', lambda: {'k': ENTRY})
    monkeypatch.setattr(cli, '_client', lambda args: object())
    monkeypatch.setattr(cli.store, 'read_all', lambda client: (1, {'k': {'active': False, 'rollout_percentage': 0}}))
    check = Mock(side_effect=SystemExit(4))
    writer = Mock()
    monkeypatch.setattr(cli.live_preflight, 'require', check)
    monkeypatch.setattr(cli, '_write', writer)
    with pytest.raises(SystemExit):
        cli.main(['set', 'k', '--rollout', '25', '--reason', 'ramp', '--yes'])
    writer.assert_not_called()
    # Reasserting inactive is a no-op, not an exposure decrease to pair with the raise.
    with pytest.raises(SystemExit) as error:
        cli.main(['set', 'k', '--rollout', '25', '--inactive', '--reason', 'kill', '--yes'])
    assert error.value.code == 4
    assert check.call_count == 2


@pytest.mark.parametrize(
    'active,pct,allow,options,gated',
    [
        (True, 0, [], ['--allow', 'new'], True),
        (False, 0, [], ['--allow', 'new'], True),
        (False, 0, ['existing'], ['--active'], True),
        (True, 0, ['existing'], ['--allow', 'existing'], False),
        (True, 0, ['existing'], ['--unallow', 'existing'], False),
        (True, 0, ['existing'], ['--deny', 'new'], False),
        (True, 25, [], ['--allow', 'new', '--rollout', '5'], 'mixed'),
        (True, 25, ['existing'], ['--rollout', '5', '--unallow', 'existing', '--deny', 'new', '--inactive'], False),
        (True, 0, [], ['--allow', 'new', '--inactive'], 'mixed'),
        (True, 0, ['existing'], ['--allow', 'new', '--unallow', 'existing'], 'mixed'),
        (True, 0, [], ['--allow', 'new', '--unallow', 'new'], False),
    ],
)
def test_allowlist_raise_and_rollback_matrix(monkeypatch, active, pct, allow, options, gated):
    current = {'active': active, 'rollout_percentage': pct, 'allow_uids': allow}
    monkeypatch.setattr(cli, 'load_registry', lambda: {'k': ENTRY})
    monkeypatch.setattr(cli, '_client', lambda args: object())
    monkeypatch.setattr(cli.store, 'read_all', lambda client: (1, {'k': current}))
    writer = Mock()
    monkeypatch.setattr(cli, '_write', writer)
    check = Mock(side_effect=SystemExit(4))
    monkeypatch.setattr(cli.live_preflight, 'require', check)
    args = ['set', 'k', '--reason', 'allowlist regression', '--yes', *options]
    if gated == 'mixed':
        assert cli.main(args) == 2
        check.assert_not_called()
        writer.assert_not_called()
    elif gated:
        with pytest.raises(SystemExit) as error:
            cli.main(args)
        assert error.value.code == 4
        check.assert_called_once()
        writer.assert_not_called()
    else:
        assert cli.main(args) == 0
        check.assert_not_called()
        writer.assert_called_once()


@pytest.mark.parametrize('active,pct', [(True, 100), (True, 0), (False, 0)])
def test_deny_removal_widens_exposure_before_any_write(monkeypatch, active, pct):
    current = {'active': active, 'rollout_percentage': pct, 'deny_uids': ['denied']}
    monkeypatch.setattr(cli, 'load_registry', lambda: {'k': ENTRY})
    monkeypatch.setattr(cli, '_client', lambda args: object())
    monkeypatch.setattr(cli.store, 'read_all', lambda client: (1, {'k': current}))
    check = Mock(side_effect=SystemExit(4))
    writer = Mock()
    monkeypatch.setattr(cli.live_preflight, 'require', check)
    monkeypatch.setattr(cli, '_write', writer)
    with pytest.raises(SystemExit) as error:
        cli.main(['set', 'k', '--undeny', 'denied', '--reason', 'raise', '--yes'])
    assert error.value.code == 4
    check.assert_called_once_with('k', pct, None)
    writer.assert_not_called()


@pytest.mark.parametrize(
    'options',
    [
        ['--rollout', '5', '--allow', 'new'],
        ['--rollout', '5', '--active'],
        ['--rollout', '50', '--deny', 'new'],
        ['--rollout', '50', '--unallow', 'allowed'],
        ['--rollout', '5', '--undeny', 'denied'],
        ['--undeny', 'denied', '--deny', 'new'],
        ['--allow', 'new', '--inactive'],
    ],
)
@pytest.mark.parametrize('override', [False, True])
def test_mixed_flag_write_refused_before_evidence_or_mirror(monkeypatch, capsys, options, override):
    current = {
        'active': '--active' not in options,
        'rollout_percentage': 25,
        'allow_uids': ['allowed'],
        'deny_uids': ['denied'],
    }
    monkeypatch.setattr(cli, 'load_registry', lambda: {'k': ENTRY})
    monkeypatch.setattr(cli, '_client', lambda args: object())
    monkeypatch.setattr(cli.store, 'read_all', lambda client: (1, {'k': current}))
    guards = [Mock(side_effect=AssertionError('mixed write must not perform IO')) for _ in range(5)]
    for owner, name, guard in zip(
        [cli.live_preflight, cli.live_preflight, cli.live_preflight, cli, cli],
        ['require', 'run', 'read_json', 'posthog_rows', '_write'],
        guards,
    ):
        monkeypatch.setattr(owner, name, guard)
    args = ['set', 'k', '--reason', 'mixed regression', '--yes', '--mirror-posthog', *options]
    if override:
        args += ['--accept-not-live', 'Approved deliberate exception']
    assert cli.main(args) == 2
    assert 'RAMP_PREFLIGHT REFUSE mixed_write' in capsys.readouterr().err
    for guard in guards:
        guard.assert_not_called()


def test_import_classifies_all_rules_before_any_live_evidence(monkeypatch, capsys):
    monkeypatch.setattr(cli, 'load_registry', lambda: {'k': ENTRY, 'k2': {**ENTRY, 'key': 'k2'}})
    monkeypatch.setattr(cli, '_client', lambda args: object())
    monkeypatch.setattr(cli.store, 'read_all', lambda client: (1, {}))
    monkeypatch.setattr(cli, 'posthog_rows', lambda: {'k': {}, 'k2': {}})
    rules = {
        'k': {'active': True, 'rollout_percentage': 25},
        'k2': {'active': True, 'rollout_percentage': 0, 'deny_uids': ['denied']},
    }
    monkeypatch.setattr(cli, 'rule_from_posthog_row', lambda row, entry: (rules[entry['key']], 'ok'))
    check = Mock(side_effect=AssertionError('mixed import must not read live evidence'))
    writer = Mock()
    monkeypatch.setattr(cli.live_preflight, 'require', check)
    monkeypatch.setattr(cli, '_write', writer)
    assert cli.main(['import-posthog', '--apply', '--accept-not-live', 'Approved deliberate exception']) == 2
    assert 'mixed_write' in capsys.readouterr().err
    check.assert_not_called()
    writer.assert_not_called()


class _Doc(SimpleNamespace):
    def to_dict(self):
        return self.data


def _fake_flag_client(stored):
    """A client whose transaction reads ``stored`` for the flag doc and records writes."""
    writes = []
    refs = {}

    def document(name=None):
        ref = refs.setdefault(name, Mock(name=f'ref:{name}'))
        if name == 'k':
            ref.get = lambda transaction=None: _Doc(exists=stored is not None, data=stored)
        elif name is not None:
            ref.get = lambda transaction=None: _Doc(exists=True, data={'version': 7})
        return ref

    transaction = Mock()
    transaction.set.side_effect = lambda ref, data: writes.append(('set', ref, data))
    transaction.delete.side_effect = lambda ref: writes.append(('delete', ref))
    client = Mock()
    client.collection.return_value.document.side_effect = document
    client.transaction.return_value = transaction
    return client, writes


@pytest.mark.parametrize(
    'stored, expected, stale',
    [
        ({'active': True, 'rollout_percentage': 100, 'version': 5}, {'active': True, 'version': 5}, False),
        ({'active': False, 'rollout_percentage': 100, 'version': 6}, {'active': True, 'version': 5}, True),
        (None, None, False),
        ({'active': True, 'version': 6}, None, True),
        (None, {'active': True, 'version': 5}, True),
        ({'active': True, 'rollout_percentage': 100}, {'active': True, 'rollout_percentage': 100}, False),
        ({'active': False, 'rollout_percentage': 100}, {'active': True, 'rollout_percentage': 100}, True),
        ({'active': True, 'version': 5}, {'active': True}, True),
    ],
)
def test_write_rule_refuses_when_stored_rule_changed_since_read(monkeypatch, stored, expected, stale):
    monkeypatch.setattr(omi_flags_store.firestore, 'transactional', lambda function: function)
    client, writes = _fake_flag_client(stored)
    if stale:
        with pytest.raises(omi_flags_store.StaleRuleError):
            omi_flags_store.write_rule(client, 'k', None, actor='t', reason='r', expected=expected)
        assert writes == []
    else:
        assert omi_flags_store.write_rule(client, 'k', None, actor='t', reason='r', expected=expected) == 8
        assert writes[0][0] == 'delete'


def test_write_rule_without_expected_keeps_last_writer_wins(monkeypatch):
    monkeypatch.setattr(omi_flags_store.firestore, 'transactional', lambda function: function)
    client, writes = _fake_flag_client({'active': False, 'version': 6})
    assert omi_flags_store.write_rule(client, 'k', {'active': True}, actor='t', reason='r') == 8
    assert writes[0][0] == 'set'


@pytest.mark.parametrize('command', [['delete', 'k'], ['set', 'k', '--rollout', '5']])
def test_cli_write_on_a_stale_snapshot_aborts_without_writing(monkeypatch, capsys, command):
    rule = {'active': True, 'rollout_percentage': 100, 'version': 5}
    monkeypatch.setattr(cli, 'load_registry', lambda: {'k': ENTRY})
    monkeypatch.setattr(cli, '_client', lambda args: object())
    monkeypatch.setattr(cli.store, 'read_all', lambda client: (5, {'k': rule}))
    monkeypatch.setattr(cli.live_preflight, 'require', Mock(side_effect=AssertionError('prod read')))
    seen = {}

    def stale(client, key, after, *, actor, reason, expected):
        seen['expected'] = expected
        raise cli.store.StaleRuleError(key)

    monkeypatch.setattr(cli.store, 'write_rule', stale)
    assert cli.main([*command, '--reason', 'r', '--yes']) != 0
    assert seen['expected'] is rule
    assert 'rule changed since it was read; nothing written' in capsys.readouterr().err
