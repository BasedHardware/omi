"""CPU LID release isolation and backend endpoint admission (offline Helm render)."""

from pathlib import Path
import subprocess

import pytest
import yaml

from scripts.runtime_env_parakeet_contract import validate_parakeet_admission_contract
from scripts.runtime_env_validation.manifest import _validate_prerecorded_stt_contract

ROOT = Path(__file__).resolve().parents[3]


def test_cpu_lid_chart_renders_an_independent_cpu_release():
    rendered = subprocess.run(
        [
            'helm',
            'template',
            'prod-omi-parakeet-lid',
            str(ROOT / 'backend/charts/parakeet'),
            '-f',
            str(ROOT / 'backend/charts/parakeet/prod_omi_parakeet_lid_values.yaml'),
            '--set-string',
            'image.tag=local-contract-test',
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    objects = list(yaml.safe_load_all(rendered.stdout))
    deployment = next(o for o in objects if o and o['kind'] == 'Deployment')
    pod = deployment['spec']['template']['spec']
    container = pod['containers'][0]
    assert deployment['metadata']['name'] == 'prod-omi-parakeet-lid'
    assert pod['nodeSelector'] == {'service': 'backend-listen', 'env': 'prod', 'type': 'high-cpu'}
    for section in container['resources'].values():
        assert not any('gpu' in k for k in section)
    env = {e['name']: e['value'] for e in container['env']}
    assert env['PARAKEET_DEVICE'] == 'cpu'
    assert env['PARAKEET_LID_ONLY'] == 'true'
    assert env['PARAKEET_LID_MODEL'] == 'whisper-base'
    assert container['startupProbe']['httpGet']['path'] == '/health'
    assert container['readinessProbe']['httpGet']['path'] == '/health'
    hpa = next(o for o in objects if o and o['kind'] == 'HorizontalPodAutoscaler')['spec']
    assert (hpa['minReplicas'], hpa['maxReplicas']) == (4, 16)
    assert hpa['metrics'] == [
        {'type': 'Resource', 'resource': {'name': 'cpu', 'target': {'type': 'Utilization', 'averageUtilization': 60}}}
    ]
    route = next(o for o in objects if o and o['kind'] == 'HTTPRoute')
    assert route['spec']['rules'][0]['matches'][0]['path']['value'] == '/lid'
    backend = next(o for o in objects if o and o['kind'] == 'BackendConfig')
    assert backend['metadata']['name'] == 'parakeet-lid-backend-config'
    manifest = yaml.load((ROOT / 'backend/deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)
    declared = manifest['environments']['prod']['gke']['parakeet-lid']['env']
    assert all(env[name] == entry['value'] for name, entry in declared.items())
    # Callers stay off the CPU release until it passes acceptance (runbook step 4); a URL
    # without the release makes every probe 404 into paid vendor LID.
    for peer in ('pusher', 'backend-listen'):
        assert manifest['environments']['prod']['gke'][peer]['env']['HOSTED_LID_API_URL']['value'] == ''
    services = manifest['environments']['prod']['cloud_run']['services']
    for service in services.values():
        if 'HOSTED_LID_API_URL' in service.get('env', {}):
            assert service['env']['HOSTED_LID_API_URL']['value'] == ''


@pytest.mark.parametrize(
    'url,valid',
    [
        ('', True),
        ('http://172.16.160.20/lid', True),
        ('ws://retired.test', False),
        ('http://lid.prod.svc.cluster.local:8080', False),
        ('http://user:password@lid', False),
        ('http://', False),
        ('https://lid?token=private', False),
    ],
)
def test_dedicated_lid_url_deploy_admission(url, valid):
    errors = _validate_prerecorded_stt_contract(
        'prod', {'cloud_run': {'services': {'test-lid': {'env': {'HOSTED_LID_API_URL': {'value': url}}}}}}
    )
    assert (not errors) is valid


@pytest.mark.parametrize(
    'key,value', [('PARAKEET_DEVICE', 'cuda:0'), ('PARAKEET_LID_ONLY', 'false'), ('PARAKEET_LID_MODEL', 'off')]
)
def test_cpu_lid_deploy_contract_rejects_asr_or_disabled_lid(key, value):
    lid_env = {
        k: {'value': v}
        for k, v in {
            'PARAKEET_DEVICE': 'cpu',
            'PARAKEET_LID_ONLY': 'true',
            'PARAKEET_LID_MODEL': 'whisper-base',
        }.items()
    }
    lid_env[key]['value'] = value
    config = {
        'gke': {
            'parakeet-lid': {'env': lid_env},
            'parakeet': {
                'env': {
                    'PARAKEET_STREAM_CAPACITY': {'value': '25'},
                    'PARAKEET_STREAM_ALLOCATION_PERCENT': {'value': '100'},
                }
            },
        }
    }
    errors = validate_parakeet_admission_contract('prod', config)
    assert len(errors) == 1
    assert key in errors[0].message
