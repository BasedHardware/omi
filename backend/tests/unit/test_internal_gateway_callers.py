"""Caller migration keeps every speaker-ID host and chart on the same route."""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


def _chart(chart, env):
    path = ROOT / f'backend/charts/{chart}/{env}_omi_{chart.replace("-", "_")}_values.yaml'
    return {entry['name']: entry.get('value') for entry in yaml.load(path.read_text(), Loader=yaml.CSafeLoader)['env']}


@pytest.mark.parametrize('env,ip,domain', [('dev', '172.16.48.49', 'omiapi.com'), ('prod', '172.16.160.20', 'omi.me')])
def test_gateway_caller_bindings_cover_all_speaker_id_hosts(env, ip, domain):
    manifest = yaml.load((ROOT / 'backend/deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)[
        'environments'
    ][env]
    overlay = yaml.load((ROOT / f'backend/deploy/runtime_env/{env}.overlay.yaml').read_text(), Loader=yaml.CSafeLoader)[
        'overlay'
    ]
    embedding_url = f'http://{ip}/diarizer'
    for source in (manifest, overlay):
        for host in ('backend-listen', 'pusher'):
            assert source['gke'][host]['env']['HOSTED_SPEAKER_EMBEDDING_API_URL']['value'] == embedding_url
        for host in ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration'):
            values = source['cloud_run']['services'][host]['env']
            assert values['HOSTED_SPEAKER_EMBEDDING_API_URL']['value'] == embedding_url
            assert values['HOSTED_PARAKEET_API_URL']['value'] == f'http://parakeet.{domain}'
        listen = source['gke']['backend-listen']['env']
        assert listen['HOSTED_TRANSLATION_API_URL']['value'] == f'http://{ip}/nllb'
        assert listen['HOSTED_PARAKEET_API_URL']['value'] == f'http://parakeet.{domain}'
    for chart in ('backend-listen', 'pusher', 'parakeet'):
        assert _chart(chart, env)['HOSTED_SPEAKER_EMBEDDING_API_URL'] == embedding_url
    listen_chart = _chart('backend-listen', env)
    assert listen_chart['HOSTED_TRANSLATION_API_URL'] == f'http://{ip}/nllb'
    assert listen_chart['HOSTED_VAD_API_URL'] == f'http://{ip}/vad/v1/vad'
    assert listen_chart['HOSTED_PARAKEET_API_URL'] == f'http://parakeet.{domain}'
    assert _chart('pusher', env)['HOSTED_PARAKEET_API_URL'] == f'http://parakeet.{domain}'
