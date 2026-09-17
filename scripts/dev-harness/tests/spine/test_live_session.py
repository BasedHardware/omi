"""V1 builder acceptance. Only pending decorator removal is permitted."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import getpass
import json
import os
from pathlib import Path
import platform
import selectors
import subprocess
import sys
import threading

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dev_harness import live_session as live, session_evidence as se
from .pending import pending


class Child:
    def __init__(self, mode, transcript, app_id, device, cwd=None):
        self.process = subprocess.Popen(
            [sys.executable, '-u', str(Path(__file__).with_name('fake_flutter.py')), mode,
             str(transcript), app_id, device], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, bufsize=0, cwd=cwd)
        self.readable = selectors.DefaultSelector()
        self.readable.register(self.process.stdout, selectors.EVENT_READ)

    def send(self, line):
        self.process.stdin.write(line.encode())
        self.process.stdin.flush()

    def receive(self, timeout_s):
        if not self.readable.select(timeout_s):
            raise TimeoutError('machine deadline')
        line = self.process.stdout.readline()
        return line.decode() if line else None

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
        self.process.wait(timeout=5)
        self.readable.close()
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()


@pytest.fixture
def rig(tmp_path):
    class Rig:
        def __init__(self):
            self.directory = tmp_path / 'oms-fixture'
            self.directory.mkdir()
            self.stamp = live.SourceStamp('a' * 40, 'clean', 'b' * 64, 'c' * 64)
            self.lease = {'schema_version': 1, 'session_id': 'oms-fixture', 'generation': 1,
                'owner': {'host': platform.node(), 'user': getpass.getuser(), 'pid': os.getpid()},
                'platform': 'ios-simulator', 'flavor': 'dev', 'profile': 'local_dev',
                'app_id': 'com.friend-app-with-wearable.ios12.development',
                'device': {'udid': 'fixture-device', 'owner': 'session', 'kind': 'simulator'},
                'default_auth_uid': 'fixture-user', 'fixture_version': 'v1', 'status': 'seeded',
                'harness_instance': 'fixture', 'ports': {'backend': 8100, 'auth': 9199, 'firestore': 8185,
                'redis': 6479}, 'source_at_acquire': {'git_sha': 'a' * 40, 'dirty_digest': 'clean'}}
            (self.directory / 'seed.json').write_text(json.dumps({
                'schema_version': 1, 'uid': 'fixture-user', 'fixture_version': 'v1',
                'provider': 'local_dev', 'seeded_at': '2026-09-17T00:00:00Z'}))
            self.children, self.specs, self.shots = [], [], []
            self.mode = 'ok'
            self.transcript = self.directory / 'transcript.jsonl'
            self.entered, self.resume = threading.Event(), threading.Event()
            self.pause = False
            (tmp_path / 'app').mkdir()
            (tmp_path / 'app' / '.dev.env').write_text('API_BASE_URL=\n')
            # Cold artifact fixture; engine must preserve this identity after reload.
            self.artifact = self.directory / 'fixture.apk'
            self.artifact.write_bytes(b'fixture cold artifact')
            self.evidence = se.build_evidence(session_id='oms-fixture',
                source={'git_sha': 'a' * 40, 'dirty_digest': 'clean', 'repo': 'BasedHardware/omi'},
                target={'platform': 'ios-simulator', 'app_id': self.lease['app_id'], 'flavor': 'dev', 'profile': 'local_dev'},
                endpoints={'api_base_url': 'http://127.0.0.1:8100/', 'auth_emulator_host': '127.0.0.1:9199',
                    'firestore_emulator_host': '127.0.0.1:8185', 'egress_policy': 'loopback-only'},
                fixtures={'fixture_version': 'v1'}, runners={'flutter': '3.44.5'},
                status={'state': 'ready'}, timestamps={'created_at': '2026-09-17T00:00:00Z'},
                artifact={'kind': 'ios-app-bundle', 'sha256': se.file_sha256(self.artifact), 'git_sha': 'a' * 40,
                          'path': 'fixture.apk'})
            se.write_evidence(self.directory / 'evidence.json', self.evidence)

        def factory(self, spec):
            self.specs.append(spec)
            child = Child(self.mode, self.transcript, 'app-fixture', spec.device_id, cwd=spec.cwd)
            self.children.append(child)
            original = child.send
            def send(line):
                if self.pause and json.loads(line)[0]['method'] == 'app.restart':
                    self.entered.set()
                    assert self.resume.wait(5), 'test synchronization deadline'
                original(line)
            child.send = send
            return child

        def screenshot(self, device, path):
            self.shots.append((device, path))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'\x89PNG\r\n\x1a\nfixture')

        def engine(self):
            return live.LiveSession(tmp_path, self.directory, load_lease=lambda: self.lease,
                source=lambda: self.stamp, factory=self.factory, screenshot=self.screenshot)

        def calls(self):
            return [json.loads(line) for line in self.transcript.read_text().splitlines()]

    value = Rig()
    yield value
    value.resume.set()
    for child in value.children:
        child.close()


@pending("V1")
def test_reload_really_sends_machine_rpc_and_binds_loaded_inputs(rig):
    engine = rig.engine()
    assert engine.start()['outcome'] == 'ok'
    spec, = rig.specs
    for argument in ('run', '--machine', '--debug', '--flavor', 'dev',
                     '--dart-define=OMI_APP_PROFILE=local_dev', '--dart-define=OMI_DEV_CONTROLS=1'):
        assert argument in spec.argv
    assert spec.device_id == 'fixture-device'
    rig.stamp = replace(rig.stamp, dirty_digest='dirty:sha256:' + 'd' * 64, inputs_sha256='e' * 64)
    reply = engine.request('reload', generation=1)
    assert reply['outcome'] == 'ok'
    calls = [c for c in rig.calls() if c['method'] == 'app.restart']
    assert len(calls) == 1
    assert calls[0]['params']['appId'] == 'app-fixture'
    assert calls[0]['params']['fullRestart'] is False
    assert calls[0]['params']['pause'] is False
    receipt = reply['evidence']
    assert receipt['artifact'] == rig.evidence['artifact']
    assert receipt['source'] == rig.evidence['source']
    assert receipt['live']['loaded_source']['inputs_sha256'] == 'e' * 64
    assert receipt['live']['requested_source'] == receipt['live']['loaded_source']
    assert receipt['live']['operation'] == 'reload'
    assert receipt['live']['daemon_code'] == 0
    assert receipt['live']['generation'] == 1
    assert receipt['live']['finished_at'] >= receipt['live']['started_at']
    assert receipt['live']['elapsed_ms'] >= 0
    assert se.validate_evidence(receipt) == []
    assert 'private-vm-auth' not in json.dumps(reply)
    op = receipt['live']['operation_id']
    assert se.read_evidence(rig.directory / 'operations' / op / 'evidence.json') == receipt


@pending("V1")
@pytest.mark.parametrize('mode,outcome', [('reject', 'rejected'), ('missing-code', 'blocked'),
                                          ('die', 'blocked'), ('wedge', 'blocked')])
def test_failed_reload_never_advances_loaded_identity(rig, mode, outcome):
    rig.mode = mode
    engine = rig.engine()
    before = engine.start()['evidence']['live']['loaded_source']
    rig.stamp = replace(rig.stamp, inputs_sha256='f' * 64)
    reply = engine.request('reload', generation=1, timeout_s=0.2)
    assert reply['outcome'] == outcome
    assert reply['error_code'] == {'reject': 'reload-rejected', 'missing-code': 'malformed-response',
                                   'die': 'daemon-exited', 'wedge': 'deadline'}[mode]
    assert reply['evidence']['live']['loaded_source'] == before
    assert reply['evidence']['live']['requested_source']['inputs_sha256'] == 'f' * 64
    if mode == 'reject':
        assert reply['evidence']['live']['daemon_code'] == 1
    assert len([c for c in rig.calls() if c['method'] == 'app.restart']) == 1


@pending("V1")
def test_hot_restart_is_explicit_and_revalidates_controls(rig):
    engine = rig.engine()
    engine.start()
    before = len(rig.calls())
    assert engine.request('restart', generation=1)['outcome'] == 'ok'
    calls = rig.calls()[before:]
    assert calls[0]['method'] == 'app.restart'
    assert calls[0]['params']['fullRestart'] is True
    assert any(c['method'] == 'app.callServiceExtension' and
               c['params']['methodName'] == 'ext.omi.controls.state' for c in calls)


@pending("V1")
def test_native_input_change_requires_cold_start_without_sending_reload(rig):
    engine = rig.engine()
    engine.start()
    rig.stamp = replace(rig.stamp, restart_sha256='d' * 64)
    assert engine.request('reload', generation=1)['outcome'] == 'restart-required'
    assert not any(c['method'] == 'app.restart' for c in rig.calls())


@pending("V1")
def test_second_mutation_rejected_while_status_remains_available(rig):
    engine = rig.engine()
    engine.start()
    rig.pause = True
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(engine.request, 'reload', generation=1)
        try:
            assert rig.entered.wait(5)
            with pytest.raises(live.LiveError) as error:
                engine.request('restart', generation=1)
            assert error.value.code == 'busy'
            assert engine.request('status', generation=1)['result']['state'] == 'busy'
        finally:
            rig.resume.set()
        assert future.result(timeout=5)['outcome'] == 'ok'
    assert len([c for c in rig.calls() if c['method'] == 'app.restart']) == 1


@pending("V1")
def test_source_edit_during_reload_is_not_attributed_to_either_version(rig):
    engine = rig.engine()
    before = engine.start()['evidence']['live']['loaded_source']
    rig.pause = True
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(engine.request, 'reload', generation=1)
        try:
            assert rig.entered.wait(5)
            rig.stamp = replace(rig.stamp, inputs_sha256='e' * 64)
        finally:
            rig.resume.set()
        reply = future.result(timeout=5)
    assert reply['outcome'] == 'blocked'
    assert reply['evidence']['live']['loaded_source'] == before
    assert engine.request('status', generation=1)['result']['state'] == 'blocked'


@pending("V1")
@pytest.mark.parametrize('field,value', [('profile', 'mobile_beta'), ('profile', 'local_prod'),
    ('profile', ''), ('flavor', 'prod'), ('flavor', ''), ('app_id', 'com.friend.ios')])
def test_wrong_launch_identity_refused_before_spawn(rig, field, value):
    rig.lease[field] = value
    engine = rig.engine()
    with pytest.raises(live.LiveError) as error:
        engine.start()
    assert error.value.code == 'unsafe-config'
    assert rig.specs == []


@pending("V1")
@pytest.mark.parametrize('mode', ['wrong-runtime', 'unready'])
def test_app_started_without_correct_runtime_readiness_is_blocked(rig, mode):
    rig.mode = mode
    engine = rig.engine()
    assert engine.start()['outcome'] == 'blocked'
    assert len(rig.children) == 1
    names = [c['params'].get('methodName') for c in rig.calls() if c['method'] == 'app.callServiceExtension']
    assert 'ext.omi.controls.capabilities' in names
    assert any(n in names for n in ('ext.omi.controls.state', 'ext.omi.controls.wait_ready'))
    if mode == 'unready':
        assert 'ext.omi.controls.wait_ready' in names


@pending("V1")
def test_generation_checked_against_current_lease_before_mutation(rig):
    engine = rig.engine()
    engine.start()
    rig.lease['generation'] = 2
    with pytest.raises(live.LiveError) as error:
        engine.request('reload', generation=1)
    assert error.value.code == 'stale-session'
    assert not any(c['method'] == 'app.restart' for c in rig.calls())


@pending("V1")
def test_screenshot_uses_owned_device_and_has_hash_and_identity(rig):
    engine = rig.engine()
    engine.start()
    reply = engine.request('screenshot', generation=1)
    assert reply['outcome'] == 'ok'
    device, path = rig.shots[0]
    assert device == 'fixture-device'
    assert path.is_relative_to(rig.directory)
    shot = reply['evidence']['live']['screenshot']
    assert shot == {'path': str(path.relative_to(rig.directory)), 'sha256': se.file_sha256(path)}
    assert reply['evidence']['live']['loaded_source']['inputs_sha256'] == rig.stamp.inputs_sha256


@pending("V1")
def test_controls_pass_actual_extension_and_params_and_refuse_arbitrary_rpc(rig):
    engine = rig.engine()
    engine.start()
    reply = engine.request('controls', generation=1, params={'method': 'navigate', 'params': {'destination': 'chat'}})
    assert reply['result'] == {'ok': True}
    sent = rig.calls()[-1]
    assert sent['method'] == 'app.callServiceExtension'
    assert sent['params']['methodName'] == 'ext.omi.controls.navigate'
    assert sent['params']['params'] == {'destination': 'chat'}
    for method in ('evaluate', 'ext.marionette.tap', 'action', 'unknown'):
        with pytest.raises(live.LiveError) as error:
            engine.request('controls', generation=1, params={'method': method, 'params': {}})
        assert error.value.code == 'unsupported-operation'
    failed = engine.request('controls', generation=1, params={'method': 'fault', 'params': {'fault': 'unknown'}})
    assert failed['outcome'] == 'rejected'
    assert rig.calls()[-1]['params'] == {'appId': 'app-fixture',
        'methodName': 'ext.omi.controls.fault', 'params': {'fault': 'unknown'}}


@pending("V1")
def test_stop_is_idempotent_and_stops_only_owned_child(rig):
    engine = rig.engine()
    engine.start()
    engine.close()
    engine.close()
    assert rig.children[0].process.poll() is not None
    assert len([c for c in rig.calls() if c['method'] == 'app.stop']) == 1


@pending("V1")
@pytest.mark.parametrize('field,value', [('host', 'other-host'), ('user', 'other-user')])
def test_foreign_owner_refused_before_spawn(rig, field, value):
    rig.lease['owner'][field] = value
    engine = rig.engine()
    with pytest.raises(live.LiveError):
        engine.start()
    assert rig.specs == []


@pending("V1")
def test_nonloopback_env_is_refused_before_spawn(rig):
    (rig.directory.parent / 'app' / '.dev.env').write_text('API_BASE_URL=https://example.invalid/\n')
    engine = rig.engine()
    with pytest.raises(live.LiveError) as error:
        engine.start()
    assert error.value.code == 'unsafe-config'
    assert rig.specs == []


@pending("V1")
def test_logs_are_owned_bounded_and_do_not_expose_vm_auth(rig):
    engine = rig.engine()
    engine.start()
    engine.request('reload', generation=1)
    reply = engine.request('logs', generation=1, params={'cursor': 0, 'limit': 1})
    assert reply['outcome'] == 'ok'
    assert len(reply['result']['entries']) == 1
    assert reply['result']['entries'][0]['message'] == 'fixture progress'
    assert isinstance(reply['result']['next_cursor'], int)
    assert 'private-vm-auth' not in json.dumps(reply)


@pending("V1")
def test_unloaded_source_cannot_be_captured_as_current(rig):
    engine = rig.engine()
    engine.start()
    rig.stamp = replace(rig.stamp, inputs_sha256='f' * 64)
    reply = engine.request('screenshot', generation=1)
    assert reply['outcome'] == 'blocked'
    assert rig.shots == []


@pending("V1")
@pytest.mark.parametrize('operation', ['stop', 'reset', 'recover', 'release'])
def test_session_lifecycle_tears_down_live_before_other_resources(tmp_path, monkeypatch, operation):
    from dev_harness import mobile_session as ms
    from dev_harness import cli
    root = Path(__file__).resolve().parents[4]
    env = {'OMI_LOCAL_STATE_ROOT': str(tmp_path / 'state')}
    lease = ms.acquire(root, env, name='lifecycle', listeners=lambda p: ())
    lease['device'] = {'kind': 'simulator', 'udid': 'owned-device', 'owner': 'session'}
    ms._save_json_atomic(ms.session_dir(root, lease['session_id'], env) / 'lease.json', lease)
    order = []
    monkeypatch.setattr(ms.DeviceController, 'detach', lambda self, platform, device: order.append('device'))
    def teardown(*args, **kwargs):
        assert ms._load_lease(ms.session_dir(root, lease['session_id'], env) / 'lease.json')['generation'] == 1
        order.append('live')
    monkeypatch.setattr(live, 'teardown', teardown)
    monkeypatch.setattr(cli, 'cmd_down', lambda *args: order.append('services') or 0)
    kwargs = {'harness_reset': lambda *args: order.append('reset') or 0} if operation == 'reset' else {}
    getattr(ms, operation)(root, lease['session_id'], env, **kwargs)
    assert order and order[0] == 'live'
    if operation in ('stop', 'release'):
        assert order == ['live', 'services', 'device']
    elif operation == 'recover':
        assert order == ['live', 'services']
        assert ms._load_lease(ms.session_dir(root, lease['session_id'], env) / 'lease.json')['generation'] == 2
    else:
        assert order == ['live', 'reset']


@pending("V1")
@pytest.mark.parametrize('operation', ['stop', 'reset', 'recover', 'release'])
def test_unproven_live_ownership_blocks_destructive_lifecycle(tmp_path, monkeypatch, operation):
    from dev_harness import mobile_session as ms
    from dev_harness import cli
    root = Path(__file__).resolve().parents[4]
    env = {'OMI_LOCAL_STATE_ROOT': str(tmp_path / 'state')}
    lease = ms.acquire(root, env, name='foreign-process', listeners=lambda p: ())
    path = ms.session_dir(root, lease['session_id'], env) / 'lease.json'
    original = path.read_bytes()
    def refuse(*args, **kwargs):
        raise live.LiveError('unsafe-config', 'process marker mismatch')
    monkeypatch.setattr(live, 'teardown', refuse)
    touched = []
    monkeypatch.setattr(cli, 'cmd_down', lambda *args: touched.append('services') or 0)
    kwargs = {'harness_reset': lambda *args: touched.append('reset') or 0} if operation == 'reset' else {}
    with pytest.raises(live.LiveError):
        getattr(ms, operation)(root, lease['session_id'], env, **kwargs)
    assert touched == []
    assert path.read_bytes() == original


@pending("V1")
def test_live_receipt_validates_structure_and_cross_field_claims(rig):
    import copy
    document = copy.deepcopy(rig.evidence)
    stamp = {'git_sha': 'a' * 40, 'dirty_digest': 'clean', 'inputs_sha256': 'b' * 64}
    document['live'] = {'generation': 1, 'operation_id': 'op-1', 'operation': 'reload', 'outcome': 'ok',
        'requested_source': stamp, 'loaded_source': dict(stamp), 'loaded_sequence': 1,
        'restart_sha256': 'c' * 64, 'daemon_code': 0, 'started_at': '2026-09-17T00:00:00Z',
        'finished_at': '2026-09-17T00:00:01Z', 'elapsed_ms': 1000}
    assert se.validate_evidence(document) == []
    invalid = [
        lambda d: d['live'].update({'generation': 0}),
        lambda d: d['live'].update({'daemon_code': 1}),
        lambda d: d['live'].update({'loaded_source': None}),
        lambda d: d['live']['loaded_source'].update({'inputs_sha256': 'd' * 64}),
        lambda d: d['live'].update({'finished_at': '2026-09-16T23:59:00Z'}),
        lambda d: d['live'].update({'elapsed_ms': -1}),
        lambda d: d['live'].update({'unknown': True}),
        lambda d: d['live'].update({'screenshot': {'path': '../escape.png', 'sha256': 'b' * 64}}),
        lambda d: d['live'].update({'screenshot': {'path': 'ok.png', 'sha256': 'not-a-hash'}}),
        lambda d: d['target'].update({'flavor': 'prod', 'profile': 'local_prod'}),
    ]
    for mutate in invalid:
        candidate = copy.deepcopy(document)
        mutate(candidate)
        assert se.validate_evidence(candidate), candidate


@pending("V1")
def test_two_sessions_have_independent_process_device_and_build_roots(rig):
    import copy
    first = rig.engine()
    assert first.start()['outcome'] == 'ok'
    second_root = rig.directory.parent / 'second-checkout'
    (second_root / 'app').mkdir(parents=True)
    (second_root / 'app' / '.dev.env').write_text('API_BASE_URL=\n')
    second_dir = second_root / 'oms-second'
    second_dir.mkdir()
    (second_dir / 'seed.json').write_bytes((rig.directory / 'seed.json').read_bytes())
    lease = copy.deepcopy(rig.lease)
    lease.update({'session_id': 'oms-second', 'harness_instance': 'second',
                  'ports': {key: value + 100 for key, value in lease['ports'].items()}})
    lease['device']['udid'] = 'second-device'
    evidence = copy.deepcopy(rig.evidence)
    evidence['session_id'] = 'oms-second'
    (second_dir / 'fixture.apk').write_bytes(rig.artifact.read_bytes())
    se.write_evidence(second_dir / 'evidence.json', evidence)
    second = live.LiveSession(second_root, second_dir, load_lease=lambda: lease,
        source=lambda: rig.stamp, factory=rig.factory, screenshot=rig.screenshot)
    assert second.start()['outcome'] == 'ok'
    a, b = rig.specs
    assert a.cwd != b.cwd
    assert a.build_dir != b.build_dir
    assert a.device_id != b.device_id
    assert rig.children[0].process.pid != rig.children[1].process.pid
    duplicate = live.LiveSession(rig.directory.parent, second_dir, load_lease=lambda: lease,
        source=lambda: rig.stamp, factory=rig.factory, screenshot=rig.screenshot)
    with pytest.raises(live.LiveError) as busy:
        duplicate.start()
    assert busy.value.code == 'worktree-busy'
    assert len(rig.children) == 2
    first.close()
    assert rig.children[1].process.poll() is None
    assert second.request('reload', generation=1)['outcome'] == 'ok'


@pending("V1")
def test_live_verify_admission_requires_matching_loaded_build_and_real_selection(rig):
    import copy
    engine = rig.engine()
    receipt = engine.start()['evidence']
    live.admit_attachment(rig.lease, receipt, rig.stamp, ready=True, supported=['j2'], selected=['j2'])
    for change, code in [('generation', 'stale-session'), ('inputs', 'stale-build'),
                         ('artifact', 'stale-build'), ('profile', 'unsafe-config'),
                         ('ready', 'unready'), ('unsupported', 'unsupported-operation'),
                         ('empty', 'unsupported-operation')]:
        lease, evidence = copy.deepcopy(rig.lease), copy.deepcopy(receipt)
        stamp, ready, selected = rig.stamp, True, ['j2']
        if change == 'generation':
            lease['generation'] += 1
        elif change == 'inputs':
            stamp = replace(stamp, inputs_sha256='f' * 64)
        elif change == 'artifact':
            evidence.pop('artifact')
        elif change == 'profile':
            lease['profile'] = 'mobile_beta'
        elif change == 'ready':
            ready = False
        elif change == 'unsupported':
            selected = ['j1']
        else:
            selected = []
        with pytest.raises(live.LiveError) as error:
            live.admit_attachment(lease, evidence, stamp, ready=ready, supported=['j2'], selected=selected)
        assert error.value.code == code


@pending("V1")
def test_live_verify_preserves_selection_drift_without_contacting_broker(monkeypatch):
    from dev_harness import mobile_verify as verify
    calls = []
    monkeypatch.setattr(live, 'dispatch', lambda *args, **kwargs: calls.append(args))
    assert verify.main(['fast', '--session', 'oms-fixture', '--filter', 'no-such-journey']) == 65
    assert calls == []


@pending("V1")
def test_process_teardown_requires_full_identity_not_pid_or_heartbeat():
    record = live.BrokerIdentity('host', 'user', 'boot-1', 1234, 'start-1', 'random-marker',
                                1, '/fixture/worktree', 'oms-fixture')
    signaled = []
    live.stop_owned_broker(record, record, signaled.append)
    assert signaled == [1234]
    live.stop_owned_broker(record, None, signaled.append)
    assert signaled == [1234]
    for field, replacement in [('host', 'other'), ('user', 'other'), ('boot_id', 'boot-2'),
                               ('process_start', 'reused-pid'), ('ownership_marker', 'foreign'),
                               ('generation', 2), ('worktree', '/other'), ('session_id', 'oms-other')]:
        with pytest.raises(live.LiveError):
            live.stop_owned_broker(record, replace(record, **{field: replacement}), signaled.append)
    assert signaled == [1234]
    with pytest.raises(live.LiveError):
        live.stop_owned_broker(replace(record, ownership_marker=''), replace(record, ownership_marker=''), signaled.append)
    assert signaled == [1234]


@pending("V1")
def test_broker_wire_rejects_unbound_requests_and_unknown_fields():
    request = {'version': 'live-session/v1', 'id': 'request-1', 'session_id': 'oms-fixture',
               'generation': 1, 'operation': 'reload', 'params': {}, 'timeout_ms': 30000}
    def encode(value):
        return (json.dumps(value) + '\n').encode()
    assert live.decode_request(encode(request), session_id='oms-fixture', generation=1) == request
    mutations = [dict(request, generation=2), dict(request, session_id='oms-other'),
                 dict(request, version='live-session/v2'), dict(request, extra=True),
                 dict(request, operation='eval'), dict(request, timeout_ms=0),
                 dict(request, params={'shell': 'anything'}), dict(request, id='../escape')]
    for candidate in mutations:
        with pytest.raises(live.LiveError):
            live.decode_request(encode(candidate), session_id='oms-fixture', generation=1)
    for raw in (b'not-json\n', encode([request]), b'x' * (1024 * 1024 + 1)):
        with pytest.raises(live.LiveError):
            live.decode_request(raw, session_id='oms-fixture', generation=1)
