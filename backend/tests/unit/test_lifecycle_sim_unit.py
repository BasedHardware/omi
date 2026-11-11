"""Credential refusal and deterministic single-use lifecycle fixture contracts."""

from concurrent.futures import ThreadPoolExecutor
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import io
from unittest.mock import AsyncMock, Mock
from types import SimpleNamespace

import pytest
from google.api_core.exceptions import PreconditionFailed

from testing.lifecycle_sim.clock import age_job_row, aged_job_fields
from testing.lifecycle_sim.faults import BoundaryFault, InjectedLifecycleFault, validate_fault_selector
from testing.lifecycle_sim.preflight import HermeticRefusal, preflight
from testing.lifecycle_sim import listener_faults
from testing.lifecycle_sim import run as simulator_runner
from testing.lifecycle_sim.storage import LifecycleBucket
from testing.lifecycle_sim.producers import CaptureRefused, begin_capture
from testing.listen_pusher_stack import run as stack_runner


@pytest.fixture
def environment(tmp_path):
    return {
        'HOME': str(tmp_path / 'home'),
        'GOOGLE_CLOUD_PROJECT': 'demo-lifecycle-sim',
        'FIRESTORE_EMULATOR_HOST': '127.0.0.1:8081',
        'CLOUDSDK_CONFIG': str(tmp_path / 'config/gcloud'),
    }


def test_preflight_accepts_only_isolated_loopback(environment, tmp_path):
    preflight(tmp_path, environ=environment)


def test_isolated_children_bound_numerical_pools_after_dropping_ambient_environment(monkeypatch, tmp_path):
    limits = (
        'OMP_NUM_THREADS',
        'OPENBLAS_NUM_THREADS',
        'MKL_NUM_THREADS',
        'VECLIB_MAXIMUM_THREADS',
        'NUMEXPR_NUM_THREADS',
        'BLIS_NUM_THREADS',
    )
    for key in limits:
        monkeypatch.setenv(key, '128')
    monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', '127.0.0.1:8081')
    monkeypatch.setattr(stack_runner.firestore, 'Client', Mock())
    child_env = stack_runner.Stack(tmp_path).env
    assert {key: child_env.get(key) for key in limits} == dict.fromkeys(limits, '1')


@pytest.mark.parametrize(
    'key,value',
    [
        ('GOOGLE_APPLICATION_CREDENTIALS', '/unopened/synthetic-key.json'),
        ('SERVICE_ACCOUNT_JSON', 'synthetic'),
        ('FIREBASE_AUTH_CREDENTIALS_PATH', '/unopened/synthetic.json'),
        ('GOOGLE_CLOUD_PROJECT', 'real-project'),
        ('GCLOUD_PROJECT', 'real-project'),
        ('FIREBASE_PROJECT_ID', 'real-project'),
        ('CLOUDSDK_AUTH_ACCESS_TOKEN_FILE', '/unopened/synthetic-token'),
        ('CLOUDSDK_CORE_PROJECT', 'real-project'),
        ('CLOUDSDK_CONFIG', '/outside-isolation'),
        ('FIRESTORE_EMULATOR_HOST', 'example.invalid:8081'),
        ('FIRESTORE_EMULATOR_HOST', '127.0.0.1.evil.invalid:8081'),
        ('FIRESTORE_EMULATOR_HOST', '127.0.0.1:0'),
        ('FIRESTORE_EMULATOR_HOST', ''),
    ],
)
def test_preflight_refuses_ambient_authority(environment, tmp_path, key, value):
    environment[key] = value
    with pytest.raises(HermeticRefusal):
        preflight(tmp_path, environ=environment)


@pytest.mark.parametrize('location', ['home/.config/gcloud', 'config/gcloud'])
def test_preflight_refuses_reachable_adc(environment, tmp_path, location):
    adc = tmp_path / location / 'application_default_credentials.json'
    adc.parent.mkdir(parents=True)
    adc.write_text('{}')
    with pytest.raises(HermeticRefusal, match='application default credentials'):
        preflight(tmp_path, environ=environment)


def test_runner_refuses_before_constructing_stack(monkeypatch, tmp_path):
    construct = Mock()
    monkeypatch.setattr(simulator_runner, 'Stack', construct)
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'real-project')
    monkeypatch.setattr(sys, 'argv', ['simulator', '--state-dir', str(tmp_path)])
    with pytest.raises(HermeticRefusal):
        simulator_runner.main()
    construct.assert_not_called()


def test_local_stream_upload_preserves_create_only_and_generation_fences(tmp_path):
    bucket = LifecycleBucket(tmp_path, 'synthetic-artifacts')
    blob = bucket.blob('synthetic.enc')
    blob.upload_from_file(io.BytesIO(b'encrypted-fixture'), if_generation_match=0)
    generation = blob.generation
    assert generation > 0
    assert blob.download_as_bytes(if_generation_match=generation) == b'encrypted-fixture'
    with pytest.raises(PreconditionFailed):
        blob.upload_from_file(io.BytesIO(b'replacement'), if_generation_match=0)
    with pytest.raises(PreconditionFailed):
        bucket.blob('synthetic.enc', generation=generation + 1).download_as_bytes()


@pytest.mark.parametrize('explicit', [False, True])
def test_runner_only_cleans_its_fresh_temporary_root(monkeypatch, tmp_path, explicit):
    root = tmp_path / 'state'
    root.mkdir()
    witness = root / 'caller-owned.txt'
    witness.write_text('preserve')
    outside = tmp_path / 'outside.txt'
    outside.write_text('outside')
    stack = Mock(env={})
    monkeypatch.setattr(simulator_runner, 'Stack', Mock(return_value=stack))
    monkeypatch.setattr(simulator_runner, 'preflight', Mock())
    monkeypatch.setattr(simulator_runner.tempfile, 'mkdtemp', Mock(return_value=str(root)))
    monkeypatch.setattr(simulator_runner.subprocess, 'run', Mock(return_value=SimpleNamespace(returncode=0)))
    monkeypatch.setattr(sys, 'argv', ['simulator', '--state-dir', str(root)] if explicit else ['simulator'])
    assert simulator_runner.main() == 0
    if explicit:
        assert witness.read_text() == 'preserve'
    else:
        assert not root.exists()
    assert outside.read_text() == 'outside'
    stack.close.assert_called_once()


@pytest.mark.parametrize('failure', ['preflight', 'constructor'])
def test_runner_cleans_automatic_root_when_setup_refuses(monkeypatch, tmp_path, failure):
    root = tmp_path / 'owned'
    root.mkdir()
    monkeypatch.setattr(simulator_runner.tempfile, 'mkdtemp', Mock(return_value=str(root)))
    monkeypatch.setattr(sys, 'argv', ['simulator'])
    monkeypatch.setattr(
        simulator_runner, 'preflight', Mock(side_effect=HermeticRefusal('refused') if failure == 'preflight' else None)
    )
    construct = Mock(side_effect=RuntimeError('constructor failed'))
    monkeypatch.setattr(simulator_runner, 'Stack', construct)
    with pytest.raises((HermeticRefusal, RuntimeError)):
        simulator_runner.main()
    assert not root.exists()
    if failure == 'preflight':
        construct.assert_not_called()


def test_relative_state_root_has_one_absolute_parent_child_identity(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    stack = Mock(env={})
    construct = Mock(return_value=stack)
    child = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(simulator_runner, 'Stack', construct)
    monkeypatch.setattr(simulator_runner, 'preflight', Mock())
    monkeypatch.setattr(simulator_runner.subprocess, 'run', child)
    monkeypatch.setattr(sys, 'argv', ['simulator', '--state-dir', 'relative-state'])
    assert simulator_runner.main() == 0
    root = tmp_path / 'relative-state'
    construct.assert_called_once_with(root)
    assert child.call_args.kwargs['env']['LIFECYCLE_SIM_STATE_DIR'] == str(root)
    assert root.is_dir()


@pytest.mark.parametrize('only', [False, True])
def test_shell_routes_retained_diagnostics_to_its_own_subdirectory(tmp_path, only):
    executables = tmp_path / 'bin'
    executables.mkdir()
    capture = tmp_path / 'firebase-args'
    for name, body in {
        'java': 'exit 0',
        'node': 'if [ "$#" -eq 2 ]; then printf "%s\\n" 49999; fi',
        'npx': 'printf "%s\\n" "$@" > "$CAPTURE"',
    }.items():
        path = executables / name
        path.write_text('#!/bin/sh\n' + body + '\n')
        path.chmod(0o700)
    state = tmp_path / 'caller state'
    script = Path(__file__).resolve().parents[2] / 'testing/listen_pusher_stack/run.sh'
    command = ['bash', str(script)] + (['--lifecycle-only'] if only else [])
    command += ['--keep', '--state-dir', str(state)]
    subprocess.run(
        command,
        env=os.environ
        | {
            'PATH': str(executables) + os.pathsep + os.environ['PATH'],
            'CAPTURE': str(capture),
            'TMPDIR': str(tmp_path),
        },
        check=True,
    )
    final_command = capture.read_text().splitlines()[-1]
    lifecycle_command = shlex.split(final_command.split('&&')[-1])
    assert '--keep' in lifecycle_command
    assert lifecycle_command[lifecycle_command.index('--state-dir') + 1] == str(
        state if only else state / 'lifecycle-sim'
    )


def test_age_job_preserves_evidence_and_shifts_numeric_and_datetime_deadlines():
    stamp = datetime.fromtimestamp(1000, timezone.utc)
    row = {
        'enqueued_at': 1000.0,
        'available_at': 1060.0,
        'committed_at': stamp,
        'state': 'record_pending',
        'held_deadline_at': 2000.0,
        'held_expired_at': 1000.0,
    }
    ref = Mock()
    ref.get.return_value.to_dict.return_value = row
    updates = age_job_row(ref, 120)
    assert updates == {
        'enqueued_at': 880.0,
        'available_at': 940.0,
        'committed_at': datetime.fromtimestamp(880, timezone.utc),
        'held_deadline_at': 1880.0,
        'held_expired_at': 880.0,
    }
    ref.update.assert_called_once_with(updates)
    assert row['enqueued_at'] == 1000.0
    assert 'state' not in updates


@pytest.mark.parametrize('seconds', [-1, float('inf'), float('nan')])
def test_age_refuses_invalid_elapsed_time(seconds):
    with pytest.raises(ValueError):
        aged_job_fields({'enqueued_at': 1000}, seconds)


@pytest.mark.parametrize('row', [None, {'state': 'record_pending'}])
def test_age_refuses_absent_or_unclocked_jobs(row):
    reference = Mock()
    reference.get.return_value.to_dict.return_value = row
    with pytest.raises(ValueError):
        age_job_row(reference, 60)
    reference.update.assert_not_called()


@pytest.mark.parametrize('boundary', ['seal', 'register', 'admit'])
def test_fault_targets_one_operation_once_even_when_concurrent(boundary):
    fault = BoundaryFault(boundary, 'synthetic', 'capture')
    fault.check(boundary, 'other', 'capture')
    fault.check(boundary, 'synthetic', 'other')

    def attempt(_):
        try:
            fault.check(boundary, 'synthetic', 'capture')
        except InjectedLifecycleFault:
            return 1
        return 0

    with ThreadPoolExecutor(max_workers=4) as executor:
        assert sum(executor.map(attempt, range(12))) == 1
    assert fault.fired


@pytest.mark.asyncio
@pytest.mark.parametrize('boundary', ['seal', 'register', 'admit'])
async def test_listener_installer_fails_the_real_callsite_once(monkeypatch, tmp_path, boundary):
    seal, register, admit = Mock(return_value=None), Mock(return_value=True), AsyncMock(return_value='admitted')
    monkeypatch.setattr(listener_faults.record_audio, 'seal_record_audio', seal)
    monkeypatch.setattr(listener_faults.live, 'register_recording', register)
    monkeypatch.setattr(listener_faults.finalizer, 'register_recording', register)
    monkeypatch.setattr(listener_faults.live, 'admit_recording', admit)
    selector = {'phase': boundary, 'uid': 'synthetic', 'conversation_id': 'capture'}
    listener_faults.install_boundary_fault(selector, state_dir=tmp_path)
    if boundary == 'seal':
        with pytest.raises(InjectedLifecycleFault):
            listener_faults.record_audio.seal_record_audio('synthetic', 'capture')
        listener_faults.record_audio.seal_record_audio('synthetic', 'capture')
        seal.assert_called_once_with('synthetic', 'capture')
    elif boundary == 'register':
        with pytest.raises(InjectedLifecycleFault):
            listener_faults.finalizer.register_recording('synthetic', {'id': 'capture'})
        listener_faults.live.register_recording('synthetic', {'id': 'capture'})
        register.assert_called_once_with('synthetic', {'id': 'capture'})
    else:
        pending = {'owner_id': 'synthetic', 'conversation_id': 'capture'}
        with pytest.raises(InjectedLifecycleFault):
            await listener_faults.live.admit_recording(None, pending)
        assert await listener_faults.live.admit_recording(None, pending) == 'admitted'
        admit.assert_awaited_once_with(None, pending)
    events = [json.loads(line) for line in (tmp_path / 'recording_lifecycle_fault.jsonl').read_text().splitlines()]
    assert events == [{'event': 'write_failed', 'scope': 'conversation', **selector}]


def test_boundary_selector_refuses_to_silently_widen_a_session_scope():
    with pytest.raises(ValueError, match='exactly'):
        listener_faults.install_boundary_fault(
            {'phase': 'seal', 'uid': 'synthetic', 'conversation_id': 'capture', 'recording_session_id': 'session'}
        )


@pytest.mark.parametrize(
    'phase', ['seal', 'register', 'admit', 'in_progress', 'processing', 'completed', 'failed', 'discarded']
)
def test_selector_preserves_conversation_and_legacy_session_identity(phase):
    selector = {'uid': 'synthetic', 'conversation_id': 'capture', 'phase': phase}
    if phase not in {'seal', 'register', 'admit'}:
        selector['recording_session_id'] = 'session'
    validate_fault_selector(selector)
    if 'recording_session_id' in selector:
        selector.pop('recording_session_id')
    else:
        selector['recording_session_id'] = 'session'
    with pytest.raises(ValueError, match='exactly'):
        validate_fault_selector(selector)


@pytest.mark.asyncio
async def test_producer_driver_reserves_inflight_capacity_and_duplicate_identity():
    entered, release = asyncio.Event(), asyncio.Event()

    class Barrier:
        def __init__(self, _uid):
            self.upload_sessions = {}

        async def begin_recording(self, cid):
            entered.set()
            await release.wait()
            self.upload_sessions[cid] = 'synthetic token'

    barriers = {}
    first = asyncio.create_task(begin_capture(barriers, 'synthetic-lifecycle-a', 'first', make_barrier=Barrier))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        with pytest.raises(CaptureRefused):
            await begin_capture(barriers, 'synthetic-lifecycle-a', 'first', make_barrier=Barrier)
        barriers.update({str(index): object() for index in range(3)})
        with pytest.raises(CaptureRefused):
            await begin_capture(barriers, 'synthetic-lifecycle-b', 'fifth', make_barrier=Barrier)
    finally:
        release.set()
        await first
    assert len(barriers) == 4


@pytest.mark.asyncio
async def test_cancelled_producer_driver_releases_its_inflight_reservation():
    entered = asyncio.Event()

    class Barrier:
        async def begin_recording(self, _cid):
            entered.set()
            await asyncio.Event().wait()

    barriers = {}
    task = asyncio.create_task(
        begin_capture(barriers, 'synthetic-lifecycle-a', 'capture', make_barrier=lambda uid: Barrier())
    )
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not barriers


@pytest.mark.asyncio
async def test_cancelled_old_producer_preserves_a_replacement_reservation():
    entered = asyncio.Event()

    class Barrier:
        async def begin_recording(self, _cid):
            entered.set()
            await asyncio.Event().wait()

    barriers = {}
    task = asyncio.create_task(
        begin_capture(barriers, 'synthetic-lifecycle-a', 'capture', make_barrier=lambda uid: Barrier())
    )
    await asyncio.wait_for(entered.wait(), 1)
    replacement = object()
    barriers['capture'] = replacement
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert barriers['capture'] is replacement
