"""Credential refusal and deterministic single-use lifecycle fixture contracts."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import sys
from unittest.mock import AsyncMock, Mock

import pytest

from testing.lifecycle_sim.clock import age_job_row, aged_job_fields
from testing.lifecycle_sim.faults import BoundaryFault, InjectedLifecycleFault
from testing.lifecycle_sim.preflight import HermeticRefusal, preflight
from testing.lifecycle_sim import listener_faults
from testing.lifecycle_sim import run as simulator_runner


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


def test_age_job_preserves_evidence_and_shifts_numeric_and_datetime_deadlines():
    stamp = datetime.fromtimestamp(1000, timezone.utc)
    row = {'enqueued_at': 1000.0, 'available_at': 1060.0, 'committed_at': stamp, 'state': 'record_pending'}
    ref = Mock()
    ref.get.return_value.to_dict.return_value = row
    updates = age_job_row(ref, 120)
    assert updates == {
        'enqueued_at': 880.0,
        'available_at': 940.0,
        'committed_at': datetime.fromtimestamp(880, timezone.utc),
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
async def test_listener_installer_fails_the_real_callsite_once(monkeypatch, boundary):
    seal, register, admit = Mock(return_value=None), Mock(return_value=True), AsyncMock(return_value='admitted')
    monkeypatch.setattr(listener_faults.record_audio, 'seal_record_audio', seal)
    monkeypatch.setattr(listener_faults.live, 'register_recording', register)
    monkeypatch.setattr(listener_faults.finalizer, 'register_recording', register)
    monkeypatch.setattr(listener_faults.live, 'admit_recording', admit)
    listener_faults.install_boundary_fault({'phase': boundary, 'uid': 'synthetic', 'conversation_id': 'capture'})
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
