"""No serving escape may dial the retired shared Parakeet/VAD services."""

from functools import lru_cache
from pathlib import Path
from unittest.mock import Mock
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

    assert service_models(['parakeet-window', 'modulate-velma-2']) == ['modulate-velma-2', 'soniox']
    assert default_models_for_surface(STTServingSurface.STREAMING) == ('modulate-velma-2', 'soniox')
    assert provider_is_enabled('modulate', STTServingSurface.STREAMING)
    assert default_models_for_surface(STTServingSurface.PRERECORDED) == ('modulate-velma-2',)
    assert default_models_for_surface(STTServingSurface.PTT) == ('modulate-velma-2',)
    assert provider_is_enabled('soniox', STTServingSurface.HELD_RECOVERY)
    assert provider_is_enabled('modulate', STTServingSurface.PRERECORDED)
    assert all(not provider_is_enabled('parakeet', surface) for surface in STTServingSurface)


def test_cost_router_and_explicit_registry_cannot_escape_retirement(retired):
    from config.live_stt_registry import Target
    from utils.stt.live_router import permission_reason

    parakeet = Target('parakeet-window', 'parakeet', 0)
    assert not parakeet.capable('en')
    assert permission_reason(parakeet, None, 'en', engine_models={'parakeet': 'parakeet-window'}) == 'capability'
    # Modulate is a vendor, not a fleet GPU: live residual stays on it instead of Soniox.
    modulate = Target('modulate-velma-2', 'modulate', 0)
    assert modulate.capable('en')
    assert permission_reason(modulate, None, 'en') != 'capability'
    assert Target('soniox', 'soniox', 0).capable('ja')


def test_language_probe_window_endpoint_and_idle_failback_do_not_dial_gpu(retired, monkeypatch):
    from config.policy.listen import window_pressure_allocation
    from config.parakeet_ja import window_endpoint
    from config.live_stt_idle import idle_parakeet_failback_enabled
    from utils.stt import language_gate

    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://retired.invalid')
    monkeypatch.setenv('STT_IDLE_PARAKEET_FAILBACK_ENABLED', 'true')
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '100')
    monkeypatch.setattr(language_gate.httpx, 'Client', lambda **kw: pytest.fail('retired language probe dialed'))
    assert language_gate.self_detect(b'audio', surface='batch') is None
    assert window_endpoint('en') == ''
    assert not idle_parakeet_failback_enabled()
    assert window_pressure_allocation() == 0


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
    assert selected[0] == streaming.STTService.modulate
    assert selected[0] != streaming.STTService.parakeet
    fallback = streaming.get_stt_service_for_language(language, exclude=frozenset({'soniox', 'modulate'}))
    assert fallback[0] is None


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


@lru_cache(maxsize=None)
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
    return [item for item in yaml.load_all(result, Loader=yaml.CSafeLoader) if item]


@pytest.mark.parametrize('chart', ['vad', 'diarizer'])
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


def test_parakeet_guard_is_retired_and_batch_keeps_own_replicas():
    baseline = resources('incluster-guards')
    assert next(o for o in baseline if o['kind'] == 'CronJob')['spec']['suspend'] is True
    guards = resources('incluster-guards', '--set', 'parakeetSuspended=true')
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
    batch = [o for o in yaml.load_all(result, Loader=yaml.CSafeLoader) if o]
    assert 'replicas' not in next(o for o in batch if o['kind'] == 'Deployment')['spec']
    assert next(o for o in batch if o['kind'] == 'HorizontalPodAutoscaler')['spec']['minReplicas'] == 1


@pytest.mark.parametrize(
    'extra', [(), ('--set', 'autoscaling.enabled=true,maintenanceMode=false,replicaCount=12,ja.enabled=true')]
)
@pytest.mark.parametrize('chart', ['parakeet'])
def test_prod_streaming_retirement_wins_over_warm_replica_and_autoscaler_settings(extra, chart):
    objects = resources(chart, *extra)
    deployments = [o for o in objects if o['kind'] == 'Deployment']
    assert deployments and all(o['spec']['replicas'] == 0 for o in deployments)
    assert not any(o['kind'] == 'HorizontalPodAutoscaler' for o in objects)
    assert not any(o['kind'] == 'Ingress' for o in objects)


def test_retired_guard_cannot_write_hpa_or_render_a_floor_even_with_stale_schedule():
    objects = resources('incluster-guards', '--set', 'floorSchedule.enabled=true')
    role = next(o for o in objects if o['kind'] == 'Role')
    hpa_rule = next(r for r in role['rules'] if r['resources'] == ['horizontalpodautoscalers'])
    assert hpa_rule['verbs'] == ['get']
    script = next(o for o in objects if o['kind'] == 'ConfigMap' and o['metadata']['name'].endswith('-script'))
    assert 'floors.json' not in script['data']


@pytest.mark.parametrize('chart', ['parakeet'])
def test_bare_chart_defaults_cannot_restore_gpu_capacity(chart):
    output = subprocess.check_output(
        [
            'helm',
            'template',
            'prod-omi-' + chart,
            str(ROOT / 'backend/charts' / chart),
            '--set',
            'image.tag=test,autoscaling.enabled=true,replicaCount=12,ingress.enabled=true,ja.enabled=true',
        ],
        text=True,
    )
    objects = [o for o in yaml.safe_load_all(output) if o]
    assert all(o['spec']['replicas'] == 0 for o in objects if o['kind'] == 'Deployment')
    assert not any(o['kind'] in ('HorizontalPodAutoscaler', 'Ingress') for o in objects)


def test_cpu_language_id_release_remains_independent_and_scalable():
    path = ROOT / 'backend/charts/parakeet'
    output = subprocess.check_output(
        [
            'helm',
            'template',
            'prod-omi-parakeet-lid',
            str(path),
            '-f',
            str(path / 'prod_omi_parakeet_lid_values.yaml'),
            '--set-string',
            'image.tag=test',
        ],
        text=True,
    )
    objects = [o for o in yaml.safe_load_all(output) if o]
    deployment = next(o for o in objects if o['kind'] == 'Deployment')
    assert 'replicas' not in deployment['spec']
    assert 'nvidia.com/gpu' not in deployment['spec']['template']['spec']['containers'][0]['resources']['requests']
    assert next(o for o in objects if o['kind'] == 'HorizontalPodAutoscaler')['spec']['minReplicas'] == 4


def test_retirement_is_declared_on_every_prod_routing_runtime_only():
    manifest = runtime_manifest()
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


@pytest.mark.parametrize('service', ['backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration'])
def test_cloud_run_retirement_configuration_can_pass_real_startup(service, streaming_module):
    manifest = runtime_manifest()
    config = manifest['environments']['prod']['cloud_run']['services'][service]
    # All four roles already use this runtime identity; reuse the existing secret,
    # with no new key or IAM change, rather than weakening the startup key guard.
    assert config['service_account'] == 'backend-runtime@based-hardware.iam.gserviceaccount.com'
    assert config['secrets']['SONIOX_API_KEY'] == {'secret': 'SONIOX_API_KEY', 'version': 'latest'}
    environment = {name: binding['value'] for name, binding in config['env'].items() if 'value' in binding}
    environment.update({name: 'configured-binding' for name in config['secrets']})
    assert environment['STT_GPU_FLEET_OFF'] == 'true'
    streaming_module.validate_streaming_stt_env(environment)


def test_windows_ptt_still_selects_modulate_after_fleet_off(retired, streaming_module):
    assert (
        streaming_module.get_stt_service_for_language('en', surface=STTServingSurface.PTT)[0]
        == streaming_module.STTService.modulate
    )


@lru_cache(maxsize=1)
def runtime_manifest():
    return yaml.load((ROOT / 'backend/deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)


@lru_cache(maxsize=None)
def production_caller_env(source):
    """Load real declarations; secret values are synthetic and never fetched."""
    if source.startswith('chart:'):
        chart = source.split(':', 1)[1]
        objects = resources(chart)
        deployment = next(o for o in objects if o['kind'] == 'Deployment')
        entries = deployment['spec']['template']['spec']['containers'][0]['env']
        return {entry['name']: entry.get('value', 'configured-binding') for entry in entries}
    config = runtime_manifest()['environments']['prod']
    if source in ('backend-listen', 'pusher'):
        caller = config['gke'][source]
        # GKE's manifest is an overlay on its chart, where vendor secrets live.
        env = dict(production_caller_env('chart:' + source))
    else:
        caller = config['cloud_run']['services'][source]
        env = {}
    env.update({name: entry.get('value', 'configured-binding') for name, entry in caller['env'].items()})
    env.update({name: 'configured-binding' for name in caller.get('secrets', {})})
    return env


@pytest.mark.parametrize(
    'source',
    [
        'backend-listen',
        'pusher',
        'backend',
        'backend-sync',
        'backend-sync-backfill',
        'backend-integration',
        'chart:backend-listen',
        'chart:pusher',
    ],
)
def test_production_callers_cannot_resolve_retired_endpoints(source, monkeypatch, streaming_module):
    from config.parakeet_ja import window_endpoint
    from config.prerecorded_stt import providers_for_model_config
    from utils.stt import language_gate, pre_recorded, vad

    env = production_caller_env(source)
    assert env['STT_GPU_FLEET_OFF'] == 'true'
    assert env['SONIOX_API_KEY']
    assert env['MODULATE_API_KEY']
    # The checks must work from checked-in config, independently of the test runner's env.
    for name in ('STT_GPU_FLEET_OFF', 'HOSTED_LID_API_URL', 'STT_SERVICE_MODELS', 'STT_PRERECORDED_MODEL'):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, str(value))
    # Some endpoints are retained for warm rollback or bound only in live config.
    # Poison both paths to prove the switch wins over those bindings too.
    monkeypatch.setenv('HOSTED_VAD_API_URL', 'http://retired.invalid/v1/vad')
    monkeypatch.setenv('HOSTED_PARAKEET_JA_API_URL', 'http://retired.invalid')
    dedicated_lid = str(env.get('HOSTED_LID_API_URL') or '').strip().rstrip('/')

    class DedicatedLidOnly:
        # Only the separately qualified CPU LID service may be dialed; never the shared pool.
        def __init__(self, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, url, **kw):
            if not dedicated_lid or not url.startswith(dedicated_lid + '/'):
                pytest.fail('retired LID dialed')
            return language_gate.httpx.Response(503)

    monkeypatch.setattr(language_gate.httpx, 'Client', DedicatedLidOnly)
    monkeypatch.setattr(vad.requests, 'post', lambda *a, **kw: pytest.fail('retired VAD dialed'))
    monkeypatch.setattr(vad, '_run_file_vad', lambda path: [{'start': 0, 'end': 1}])
    monkeypatch.setattr(pre_recorded, 'modulate_prerecorded_from_bytes', lambda *a, **kw: ['vendor words'])
    streaming_module.validate_streaming_stt_env(env)
    for language in ('en', 'ja', 'multi'):
        selected = streaming_module.get_stt_service_for_language(
            language, preferred_service='parakeet', window_uid='synthetic-owner', prefer_window=True
        )
        assert selected[0] == streaming_module.STTService.modulate
        assert pre_recorded.get_prerecorded_service(language)[0] == 'modulate'
        assert (
            streaming_module.get_stt_service_for_language(language, surface=STTServingSurface.PTT)[0]
            == streaming_module.STTService.modulate
        )
        assert window_endpoint(language) == ''
    assert providers_for_model_config(env.get('STT_PRERECORDED_MODEL', '')) == ('modulate',)
    assert pre_recorded.parakeet_prerecorded_from_bytes(b'wav') == ['vendor words']
    assert language_gate.self_detect(b'wav', surface='batch') is None
    assert vad.vad_is_empty('unused.wav', return_segments=True) == [{'start': 0, 'end': 1}]


@pytest.mark.parametrize('fleet_off', ['true', 'false'])
@pytest.mark.parametrize('fails', [False, True])
def test_dedicated_lid_precedes_shared_endpoint_and_failure_keeps_vendor(monkeypatch, fleet_off, fails):
    from utils.stt import language_gate

    monkeypatch.setenv('STT_GPU_FLEET_OFF', fleet_off)
    monkeypatch.setenv('HOSTED_LID_API_URL', ' http://cpu-lid.invalid/lid/ ')
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://retired.invalid')
    client = Mock()
    response = Mock(status_code=200)
    response.json.return_value = {
        'language': 'de',
        'language_probability': 0.99,
        'p_supported': 0.99,
        'audio_seconds': 6,
    }
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.post.return_value = response
    if fails:
        client.post.side_effect = language_gate.httpx.TimeoutException('unavailable')
    monkeypatch.setattr(language_gate.httpx, 'Client', lambda **kw: client)
    verdict = language_gate.self_detect(b'wav', surface='batch')
    if fails:
        assert verdict is None
    else:
        assert verdict.language == 'de'
    assert client.post.call_count == 1
    assert client.post.call_args.args == ('http://cpu-lid.invalid/lid/v2/language',)


def test_notifications_job_has_no_shared_gpu_bindings():
    config = runtime_manifest()['environments']['prod']['cloud_run']['jobs']['notifications-job']
    for key in ('HOSTED_VAD_API_URL', 'HOSTED_PARAKEET_API_URL'):
        assert key not in config['env']
        assert key not in config.get('secrets', {})
