"""Production operator pins must survive composition and actual Helm rendering."""

from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
PINS = {
    'backend-listen': {
        'MEDIA_NOISE_MODE': 'shadow',
        'MEDIA_NOISE_MODE_SERVE_PERCENT': '0',
        'NOTES_SHORT_CLIP_FLOOR': 'true',
    },
    'pusher': {
        'LIVE_CAPTURE_WINDOW_RETENTION': 'false',
        'LIVE_CAPTURE_WINDOW_STRICT_PROJECTION': 'false',
        'NOTES_SHORT_CLIP_FLOOR': 'true',
        'REPEAT_WORK_LLM_VERSION': '2026-10-16-v1',
    },
}


@pytest.mark.parametrize('host', PINS)
def test_operator_pins_survive_actual_helm_render_and_composition(host):
    chart = ROOT / 'backend/charts' / host
    values = chart / f'prod_omi_{host.replace("-", "_")}_values.yaml'
    result = subprocess.run(
        [
            'helm',
            'template',
            f'prod-omi-{host}',
            str(chart),
            '-f',
            str(values),
            '--set-string',
            'image.repository=test.invalid/backend',
            '--set-string',
            'image.tag=test',
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    deployment = next(doc for doc in yaml.safe_load_all(result.stdout) if doc and doc['kind'] == 'Deployment')
    entries = deployment['spec']['template']['spec']['containers'][0]['env']
    env = {e['name']: e for e in entries}
    assert len(entries) == len(env), 'Duplicate env entries break Helm strategic merge'
    manifest = yaml.safe_load((ROOT / 'backend/deploy/runtime_env.yaml').read_text())
    composed = manifest['environments']['prod']['gke'][host]['env']
    for key, value in PINS[host].items():
        assert env[key]['value'] == value
        assert composed[key]['value'] == value
    assert env['FSR_USAGE_MONTH_TOTAL_EPOCH']['value'] == 'c2fs_20261026_r1'
    for key in (
        'RECORD_TOKEN_LEASE_MODE',
        'RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT',
        'RECORD_TOKEN_LEASE_SECONDS',
        'RECORD_TOKEN_LEASE_DEPLOYED_AT',
    ):
        assert env[key]['valueFrom']['configMapKeyRef'] == {'name': 'prod-omi-backend-config', 'key': key}
    assert env['PRERECORDED_SONIOX_FAILOVER_ENABLED']['value'] == 'true'
