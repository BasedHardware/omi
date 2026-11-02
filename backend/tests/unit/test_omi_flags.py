"""Omi flag store: evaluation, snapshot refresh/fallback, /v1/flags, proactivity_v2 source switch, CLI rules."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient
from posthog.feature_flags import _hash as posthog_hash

from config.proactivity_v2 import ProactivityDenied
from routers import omi_flags as flags_router
from scripts import omi_flags as cli
from utils import omi_flags, proactivity_flags
from utils.metrics import OMI_FLAG_DUAL_READ_TOTAL
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


def _dual_count(outcome):
    return OMI_FLAG_DUAL_READ_TOTAL.labels(flag='proactivity_v2', outcome=outcome)._value.get()


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
