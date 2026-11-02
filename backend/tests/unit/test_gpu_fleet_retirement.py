"""No serving escape may dial the retired shared Parakeet/VAD services."""

from pathlib import Path
import subprocess

import pytest
import yaml

from config.live_stt_gpu_fleet import gpu_fleet_off
from config.stt_provider_policy import STTServingSurface, default_models_for_surface, provider_is_enabled

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def retired(monkeypatch):
    monkeypatch.setenv('STT_GPU_FLEET_OFF', 'true')


@pytest.fixture(scope='module')
def streaming_module():
    from utils.stt import streaming

    return streaming


def test_switch_preserves_existing_routing_until_deployed(monkeypatch):
    monkeypatch.delenv('STT_GPU_FLEET_OFF', raising=False)
    assert not gpu_fleet_off()
    assert provider_is_enabled('parakeet', STTServingSurface.PRERECORDED)
    assert provider_is_enabled('modulate', STTServingSurface.STREAMING)


def test_retirement_preserves_batch_vendors_and_never_reactivates_gpu_defaults(retired):
    from config.policy.listen import service_models

    assert service_models(['parakeet-window', 'modulate-velma-2']) == ['soniox']
    assert default_models_for_surface(STTServingSurface.STREAMING) == ('soniox',)
    assert default_models_for_surface(STTServingSurface.PRERECORDED) == ('modulate-velma-2',)
    assert default_models_for_surface(STTServingSurface.PTT) == ('modulate-velma-2',)
    assert provider_is_enabled('soniox', STTServingSurface.HELD_RECOVERY)
    assert provider_is_enabled('modulate', STTServingSurface.PRERECORDED)
    assert all(not provider_is_enabled('parakeet', surface) for surface in STTServingSurface)


def test_cost_router_and_explicit_registry_cannot_escape_retirement(retired):
    from config.live_stt_registry import Target
    from utils.stt.live_router import permission_reason

    for family, target_id in [('parakeet', 'parakeet-window'), ('modulate', 'modulate-velma-2')]:
        target = Target(target_id, family, 0)
        assert not target.capable('en')
        assert permission_reason(target, None, 'en', engine_models={'parakeet': target_id}) == 'capability'
    assert Target('soniox', 'soniox', 0).capable('ja')


def test_language_probe_window_endpoint_and_idle_failback_do_not_dial_gpu(retired, monkeypatch):
    from config.parakeet_ja import window_endpoint
    from config.live_stt_idle import idle_parakeet_failback_enabled
    from utils.stt import language_gate

    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://retired.invalid')
    monkeypatch.setenv('STT_IDLE_PARAKEET_FAILBACK_ENABLED', 'true')
    monkeypatch.setattr(language_gate.httpx, 'Client', lambda **kw: pytest.fail('retired language probe dialed'))
    assert language_gate.self_detect(b'audio', surface='batch') is None
    assert window_endpoint('en') == ''
    assert not idle_parakeet_failback_enabled()


def test_retirement_requires_soniox_key_even_for_old_secret_model_chain(streaming_module):
    validate_streaming_stt_env = streaming_module.validate_streaming_stt_env

    with pytest.raises(RuntimeError, match='SONIOX_API_KEY'):
        validate_streaming_stt_env({'STT_GPU_FLEET_OFF': 'true', 'STT_SERVICE_MODELS': 'parakeet-window'})
    validate_streaming_stt_env({'STT_GPU_FLEET_OFF': 'true', 'SONIOX_API_KEY': 'test-key'})


@pytest.mark.parametrize('language', ['en', 'bg', 'ja', 'multi'])
def test_static_selection_and_preferred_gpu_cannot_bypass_retirement(retired, monkeypatch, language, streaming_module):
    streaming = streaming_module

    monkeypatch.setenv('SONIOX_API_KEY', 'test-key')
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://retired.invalid')
    selected = streaming.get_stt_service_for_language(
        language, preferred_service='parakeet', window_uid='synthetic-owner', prefer_window=True
    )
    assert selected[0] == streaming.STTService.soniox
    assert streaming.get_stt_service_for_language(language, exclude=frozenset({'soniox'}))[0] is None


def test_direct_prerecorded_call_preserves_audio_and_language_contract(retired, monkeypatch):
    from utils.stt import pre_recorded

    calls = []
    expected = ([{'text': 'vendor words'}], 'de')

    def vendor(audio, **kwargs):
        calls.append((audio, kwargs))
        return expected

    monkeypatch.delenv('HOSTED_PARAKEET_API_URL', raising=False)
    monkeypatch.setattr(pre_recorded, 'modulate_prerecorded_from_bytes', vendor)
    assert pre_recorded.parakeet_prerecorded_from_bytes(b'wav', language='de', return_language=True) == expected
    assert calls[0][0] == b'wav'
    assert calls[0][1]['language'] == 'de'
    assert calls[0][1]['return_language'] is True
    assert pre_recorded.get_prerecorded_service('de')[0] == 'modulate'
    assert pre_recorded.get_prerecorded_service('bg')[0] == 'modulate'


def test_hosted_vad_is_bypassed_without_waiting_for_failure(retired, monkeypatch):
    from utils.stt import vad

    monkeypatch.setenv('HOSTED_VAD_API_URL', 'http://retired.invalid/v1/vad')
    monkeypatch.setattr(vad.requests, 'post', lambda *a, **kw: pytest.fail('retired VAD dialed'))
    monkeypatch.setattr(vad, '_run_file_vad', lambda path: [{'start': 0, 'end': 1}])
    assert vad.vad_is_empty('unused.wav', return_segments=True) == [{'start': 0, 'end': 1}]


def resources(chart, *extra):
    path = ROOT / 'backend/charts' / chart
    image_args = [] if chart == 'incluster-guards' else ['--set-string', 'image.tag=retirement-contract-test']
    result = subprocess.check_output(
        [
            'helm',
            'template',
            'prod-omi-' + chart,
            str(path),
            '-n',
            'prod-omi-backend',
            '-f',
            str(path / f'prod_omi_{chart.replace("-", "_")}_values.yaml'),
            *image_args,
            *extra,
        ],
        text=True,
    )
    return [item for item in yaml.safe_load_all(result) if item]


@pytest.mark.parametrize('chart', ['parakeet', 'vad', 'diarizer'])
def test_maintenance_zero_preserves_every_object_and_model(chart):
    baseline = resources(chart)
    stopped = resources(chart, '--set', 'maintenanceMode=true')
    assert {(o['kind'], o['metadata']['name']) for o in stopped} == {
        (o['kind'], o['metadata']['name']) for o in baseline
    }
    deployment = next(o for o in stopped if o['kind'] == 'Deployment')
    prior = next(o for o in baseline if o['kind'] == 'Deployment')
    assert deployment['spec']['replicas'] == 0
    assert deployment['spec']['template'] == prior['spec']['template']
    hpa = next(o for o in stopped if o['kind'] == 'HorizontalPodAutoscaler')
    assert hpa['spec']['minReplicas'] > 0


def test_parakeet_guard_is_suspended_and_batch_release_keeps_own_replicas():
    guards = resources('incluster-guards')
    cron = next(o for o in guards if o['kind'] == 'CronJob' and o['metadata']['name'] == 'prod-omi-incluster-guards')
    assert cron['spec']['suspend'] is True
    assert any(o['kind'] == 'ConfigMap' and o['metadata']['name'].endswith('-state') for o in guards)
    path = ROOT / 'backend/charts/diarizer'
    result = subprocess.check_output(
        [
            'helm',
            'template',
            'prod-omi-diarizer-batch',
            str(path),
            '-f',
            str(path / 'prod_omi_diarizer_values.yaml'),
            '-f',
            str(path / 'prod_omi_diarizer_batch_values.yaml'),
            '--set-string',
            'image.tag=retirement-contract-test',
        ],
        text=True,
    )
    batch = [o for o in yaml.safe_load_all(result) if o]
    assert 'replicas' not in next(o for o in batch if o['kind'] == 'Deployment')['spec']
    assert next(o for o in batch if o['kind'] == 'HorizontalPodAutoscaler')['spec']['minReplicas'] == 1


def test_retirement_is_declared_on_every_prod_routing_runtime_only():
    manifest = yaml.safe_load((ROOT / 'backend/deploy/runtime_env.yaml').read_text())
    # The composed document owns runtime identity, independent from chart defaults.
    for environment, config in manifest['environments'].items():
        envs = [config['gke'][name]['env'] for name in ('backend-listen', 'pusher')]
        envs.extend(
            config['cloud_run']['services'][name]['env']
            for name in ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')
        )
        for env in envs:
            if environment == 'prod':
                assert env['STT_GPU_FLEET_OFF']['value'] == 'true'
            else:
                assert 'STT_GPU_FLEET_OFF' not in env
