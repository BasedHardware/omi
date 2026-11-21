"""Pipeline lab, lane chain: stack config, network allowlist, clock, overlay and decisions."""

from contextlib import ExitStack
import datetime as dt
import hashlib
import json
import os
import socket
import sys
import time
import types

import pytest

from testing.pipeline_lab.stack import LAB_UID
from testing.pipeline_lab.stack.clock import LabClock, installed_clock, real_now
from testing.pipeline_lab.stack.config import LabStackConfig, StackConfigError
from testing.pipeline_lab.stack.env import compose_settings, lab_environment
from testing.pipeline_lab.stack.network import LabNetworkRefused, NetworkPolicy, guarded_network
from testing.pipeline_lab.stack.overlay import DecisionLog, Overlay, install_gate_pins, resolve_pins, trace_serving_for
from testing.pipeline_lab.stack.patching import replace_everywhere

T0 = dt.datetime(2026, 3, 14, 9, 30, tzinfo=dt.timezone.utc)


# -- config ---------------------------------------------------------------------------


def test_config_defaults_follow_dev_up_and_are_loopback():
    config = LabStackConfig.from_env({})
    assert config.firestore == ('127.0.0.1', 8085)
    assert config.uid == LAB_UID == 'local-dev-user'
    env = config.product_env()
    assert env['FIRESTORE_EMULATOR_HOST'] == '127.0.0.1:8085'
    assert env['OMI_LLM_GATEWAY_URL'] == config.llm_proxy_url
    assert env['GOOGLE_CLOUD_PROJECT'].startswith('demo-')
    assert env['POSTHOG_PROJECT_API_KEY'] == ''
    assert str(config.storage_root).endswith('stack/storage')


@pytest.mark.parametrize(
    'env',
    [
        {'FIRESTORE_EMULATOR_HOST': '10.0.0.5:8080'},
        {'OMI_PIPELINE_LAB_LLM_PROXY_URL': 'https://gateway.example.com'},
        {'OMI_PIPELINE_LAB_REDIS': 'redis.internal:6379'},
        {'FIRESTORE_EMULATOR_HOST': 'nonsense'},
    ],
)
def test_config_refuses_non_loopback_peers(env):
    with pytest.raises(StackConfigError):
        LabStackConfig.from_env(env)


def test_config_refuses_non_demo_project():
    config = LabStackConfig.from_env({'OMI_PIPELINE_LAB_PROJECT_ID': 'based-hardware'})
    with pytest.raises(StackConfigError):
        config.product_env()


# -- network --------------------------------------------------------------------------


def _policy(**kwargs):
    config = LabStackConfig.from_env({'OMI_PIPELINE_LAB_STT_ENDPOINTS': 'stt.vendor.example:443'})
    return NetworkPolicy.for_stack(config, **kwargs)


def test_network_policy_allows_only_listed_peers():
    policy = _policy()
    assert policy.address_allowed('127.0.0.1', 8085)
    assert policy.address_allowed('localhost', 9180)
    assert not policy.address_allowed('127.0.0.1', 5432)
    assert not policy.address_allowed('8.8.8.8', 443)
    assert policy.address_allowed('stt.vendor.example', 443)
    assert not policy.address_allowed('stt.vendor.example', 80)
    assert policy.host_allowed_for_dns('stt.vendor.example')
    assert not policy.host_allowed_for_dns('api.openai.com')


def test_network_guard_refuses_and_logs():
    seen = []
    policy = _policy(on_refusal=seen.append)
    before = socket.socket.connect
    with guarded_network(policy):
        with pytest.raises(LabNetworkRefused):
            socket.getaddrinfo('api.openai.com', 443)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with pytest.raises(LabNetworkRefused):
                sock.connect(('127.0.0.1', 5432))
        finally:
            sock.close()
        import grpc

        with pytest.raises(LabNetworkRefused):
            grpc.secure_channel('firestore.googleapis.com:443', None)
        with pytest.raises(LabNetworkRefused):
            grpc.insecure_channel('10.1.2.3:8085')
    assert [row['kind'] for row in seen] == ['dns', 'connect', 'grpc-secure', 'grpc']
    assert socket.socket.connect is before  # restored


def test_resolved_stt_ips_are_admitted_for_their_port_only():
    policy = _policy()
    policy.note_resolution('stt.vendor.example', 443, [(None, None, None, '', ('203.0.113.7', 443))])
    assert policy.address_allowed('203.0.113.7', 443)
    assert not policy.address_allowed('203.0.113.7', 22)
    policy.note_resolution('other.example', 443, [(None, None, None, '', ('198.51.100.1', 443))])
    assert not policy.address_allowed('198.51.100.1', 443)


# -- patching ---------------------------------------------------------------------------


def test_replace_everywhere_swaps_bound_names_and_restores():
    def original():
        return 'real'

    def replacement():
        return 'lab'

    mod_a = types.ModuleType('plab_fixture_a')
    mod_b = types.ModuleType('plab_fixture_b')
    mod_a.f = original
    mod_b.alias = original
    sys.modules.update({'plab_fixture_a': mod_a, 'plab_fixture_b': mod_b})
    try:
        with ExitStack() as stack:
            assert replace_everywhere(stack, original, replacement) == 2
            assert mod_a.f() == 'lab' and mod_b.alias() == 'lab'
        assert mod_a.f() == 'real' and mod_b.alias() == 'real'
    finally:
        sys.modules.pop('plab_fixture_a')
        sys.modules.pop('plab_fixture_b')


# -- clock ----------------------------------------------------------------------------------


def test_clock_patches_product_scope_only_then_restores():
    source = (
        'from datetime import datetime, timezone, date\nimport datetime as dtmod\nimport time\n'
        'def now():\n    return datetime.now(timezone.utc)\n'
        'def via_module():\n    return dtmod.datetime.now(dtmod.timezone.utc)\n'
        'def utc():\n    return datetime.utcnow()\n'
        'def today():\n    return date.today()\n'
        'def ts():\n    return time.time()\n'
    )
    fixture = types.ModuleType('plab_clock_fixture')
    library = types.ModuleType('plab_clock_library')
    exec(source, fixture.__dict__)
    exec(source, library.__dict__)
    sys.modules.update({'plab_clock_fixture': fixture, 'plab_clock_library': library})
    try:
        clock = LabClock(T0, tick=False)
        with installed_clock(clock, scope=('plab_clock_fixture',)):
            assert fixture.now() == T0 and fixture.via_module() == T0
            assert fixture.now().__class__ is real_now().__class__  # plain datetime, nothing lab-typed leaks
            assert fixture.utc() == T0.replace(tzinfo=None)
            assert fixture.today() == T0.astimezone().date()
            assert fixture.ts() == T0.timestamp() == library.ts()  # time.time is process-wide
            # Out-of-scope code (pydantic, protobuf, Firestore) keeps the real classes and real now.
            assert library.datetime is dt.datetime and library.now() != T0
            assert isinstance(real_now(), fixture.datetime)  # isinstance against the lab type still works
            assert fixture.datetime(2020, 1, 1).year == 2020
            assert fixture.datetime.fromisoformat('2020-01-02T00:00:00+00:00').day == 2
            assert fixture.dtmod.timedelta is dt.timedelta
            clock.set(T0 + dt.timedelta(days=1))
            assert fixture.now() == T0 + dt.timedelta(days=1)
            assert time.monotonic() > 0  # monotonic is untouched
        assert abs(fixture.ts() - time.time()) < 5
        assert fixture.datetime is dt.datetime and fixture.dtmod is dt
        # Transport libraries keep real time.time even under the clock: gRPC deadlines are wall-clock.
        grpc_like = types.ModuleType('grpc._plab_fixture')
        exec('import time\ndef deadline():\n    return time.time() + 1\n', grpc_like.__dict__)
        with installed_clock(LabClock(T0, tick=False), scope=('plab_clock_fixture',)):
            assert abs(grpc_like.deadline() - real_now().timestamp() - 1) < 5
            assert real_now().timestamp() - T0.timestamp() > 3600
            assert fixture.ts() == T0.timestamp()
    finally:
        sys.modules.pop('plab_clock_fixture')
        sys.modules.pop('plab_clock_library')


def test_global_clock_scope_patches_the_datetime_module():
    with installed_clock(LabClock(T0, tick=False), scope=None):
        assert dt.datetime.now(dt.timezone.utc) == T0
    assert dt.datetime.now(dt.timezone.utc) != T0 and dt.datetime.__name__ == 'datetime'


def test_ticking_clock_advances_from_the_set_instant():
    clock = LabClock(T0)
    first = clock.timestamp()
    time.sleep(0.02)
    assert clock.timestamp() > first
    assert clock.timestamp() - T0.timestamp() < 5


def test_clock_rejects_naive_instants_and_double_install():
    with pytest.raises(ValueError):
        LabClock(dt.datetime(2026, 1, 1))
    with installed_clock(LabClock(T0, tick=False)):
        with pytest.raises(RuntimeError):
            with installed_clock(LabClock(T0, tick=False)):
                pass


# -- overlay and decisions ---------------------------------------------------------------


def test_overlay_pins_cohorts_through_digest_lists():
    overlay = Overlay.from_mapping(
        {
            'serving': {'NOTES_PACKET_V2_MODE': True, 'ACTION_ITEMS_V2_MODE': False},
            'env': {'NOTES_PACKET_V2_MODE': 'shadow'},
        }
    )
    env = overlay.render_env(LAB_UID)
    digest = hashlib.sha256(LAB_UID.encode()).hexdigest()
    assert env['NOTES_PACKET_V2_MODE_SERVE_UID_SHA256S'] == digest
    assert env['NOTES_PACKET_V2_MODE_SERVE_PERCENT'] == '0'
    assert env['ACTION_ITEMS_V2_MODE_SERVE_UID_SHA256S'] == ''
    assert env['LISTEN_FINALIZATION_DISPATCH_MODE'] == 'inline'
    from config import refactor_modes

    assert refactor_modes.serving_for('NOTES_PACKET_V2_MODE', LAB_UID, environ=env) is True
    assert refactor_modes.serving_for('ACTION_ITEMS_V2_MODE', LAB_UID, environ=env) is False


def test_overlay_rejects_raw_cohort_env_and_unknown_keys():
    with pytest.raises(ValueError):
        Overlay.from_mapping({'env': {'X_MODE_SERVE_PERCENT': '100'}})
    with pytest.raises(ValueError):
        Overlay.from_mapping({'flags': {}})
    with pytest.raises(ValueError):
        Overlay.from_mapping({'gates': {'no_colon': True}})


def test_resolve_pins_logs_decisions_and_conflicts(tmp_path):
    overlay = Overlay.from_mapping({'serving': {'A_MODE': True, 'B_MODE': True}, 'env': {'B_MODE': 'off'}})
    log = DecisionLog(tmp_path / 'decisions.jsonl')
    resolve_pins(overlay, log, environ=overlay.render_env())
    rows = [json.loads(line) for line in (tmp_path / 'decisions.jsonl').read_text().splitlines()]
    assert {(r['name'], r['source']) for r in rows} >= {('A_MODE', 'overlay'), ('B_MODE', 'overlay_conflict')}
    for row in rows:
        assert {'at', 'name', 'mode', 'source'} <= set(row)
    assert all(LAB_UID not in json.dumps(row) for row in rows)


def test_trace_serving_for_logs_unpinned_and_strict_refuses(tmp_path):
    from config import refactor_modes

    fixture = types.ModuleType('plab_serving_fixture')
    fixture.serving_for = refactor_modes.serving_for
    sys.modules['plab_serving_fixture'] = fixture
    try:
        log = DecisionLog(None)
        with ExitStack() as stack:
            trace_serving_for(stack, Overlay(), log)
            assert fixture.serving_for('UNPINNED_X_MODE', LAB_UID, environ={}) is False
        assert log.rows[-1]['source'] == 'unpinned'
        with ExitStack() as stack:
            trace_serving_for(stack, Overlay(strict=True), log)
            with pytest.raises(Exception, match='not pinned'):
                fixture.serving_for('UNPINNED_X_MODE', LAB_UID, environ={})
        assert fixture.serving_for is refactor_modes.serving_for
    finally:
        sys.modules.pop('plab_serving_fixture')


def test_gate_pins_replace_helpers_and_log_calls():
    gates = types.ModuleType('plab_gate_fixture')
    gates.budget_allowed = lambda uid: False
    consumer = types.ModuleType('plab_gate_consumer')
    consumer.budget_allowed = gates.budget_allowed
    sys.modules.update({'plab_gate_fixture': gates, 'plab_gate_consumer': consumer})
    try:
        overlay = Overlay(gates={'plab_gate_fixture:budget_allowed': True, 'plab_missing_module:x': 1})
        log = DecisionLog(None)
        with ExitStack() as stack:
            # Only this test's gate: defaults name product modules a unit test must not import.
            overlay.effective_gates = lambda: dict(overlay.gates)
            install_gate_pins(stack, overlay, log)
            assert consumer.budget_allowed('u') is True
        assert consumer.budget_allowed('u') is False
        sources = {(r['name'], r['source'], r['mode']) for r in log.rows}
        assert ('plab_gate_fixture:budget_allowed', 'gate_pin', True) in sources
        assert ('plab_missing_module:x', 'gate_pin', 'missing') in sources
    finally:
        sys.modules.pop('plab_gate_fixture')
        sys.modules.pop('plab_gate_consumer')


def test_overlay_may_not_rebind_stack_settings():
    config = LabStackConfig.from_env({})
    with pytest.raises(ValueError, match='rebind'):
        compose_settings(config, Overlay(env={'FIRESTORE_EMULATOR_HOST': '127.0.0.1:1'}))


def test_lab_environment_env_layer_clears_ambient_settings(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-ambient-should-vanish')
    monkeypatch.setenv('SOME_AMBIENT_FLAG', '1')
    config = LabStackConfig.from_env({'OMI_PIPELINE_LAB_ROOT': str(tmp_path)})
    with lab_environment(config, Overlay(name='t'), run_dir=tmp_path, install_product=False) as env:
        assert os.environ['OPENAI_API_KEY'].startswith('pipeline-lab-placeholder')
        assert 'SOME_AMBIENT_FLAG' not in os.environ
        assert os.environ['FIRESTORE_EMULATOR_HOST'] == config.firestore_host
        with pytest.raises(LabNetworkRefused):
            socket.getaddrinfo('example.com', 443)
    assert os.environ['SOME_AMBIENT_FLAG'] == '1'
    rows = [json.loads(line) for line in (tmp_path / 'decisions.jsonl').read_text().splitlines()]
    assert rows[0]['name'] == 'overlay' and rows[0]['overlay_name'] == 't'
    assert env.network.refusals and env.network.refusals[0]['kind'] == 'dns'
