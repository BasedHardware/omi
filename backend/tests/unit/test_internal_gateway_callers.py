"""Speaker-ID route topology: in-cluster callers on ClusterIP, Cloud Run on the internal ALB.

Cloud Run cannot resolve Kubernetes DNS, so its services keep the internal-ALB routes
(per-GB inbound). GKE workloads in the same cluster as the target services use the
ClusterIP service DNS and pay nothing per GB. Dev keeps the shared dev gateway on both
sides; prod routes in-cluster traffic off the ALBs.
"""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]

IN_CLUSTER_EMBEDDING = 'http://prod-omi-diarizer.prod-omi-backend.svc.cluster.local:8080'
IN_CLUSTER_NLLB = 'http://prod-omi-nllb-translation.prod-omi-backend.svc.cluster.local:8080'
IN_CLUSTER_VAD = 'http://prod-omi-vad.prod-omi-backend.svc.cluster.local:8080/v1/vad'
IN_CLUSTER_PUSHER = 'http://prod-omi-pusher.prod-omi-backend.svc.cluster.local:8080'


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
    in_cluster = env == 'prod'
    gke_embedding = IN_CLUSTER_EMBEDDING if in_cluster else f'http://{ip}/diarizer'
    gke_translation = IN_CLUSTER_NLLB if in_cluster else f'http://{ip}/nllb'
    gke_vad = IN_CLUSTER_VAD if in_cluster else f'http://{ip}/vad/v1/vad'
    for source in (manifest, overlay):
        for host in ('backend-listen', 'pusher'):
            assert source['gke'][host]['env']['HOSTED_SPEAKER_EMBEDDING_API_URL']['value'] == gke_embedding
        for host in ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration'):
            values = source['cloud_run']['services'][host]['env']
            # Cloud Run must stay on the internal-ALB route; it cannot resolve cluster DNS.
            assert values['HOSTED_SPEAKER_EMBEDDING_API_URL']['value'] == f'http://{ip}/diarizer'
            assert values['HOSTED_PARAKEET_API_URL']['value'] == f'http://parakeet.{domain}'
        listen = source['gke']['backend-listen']['env']
        assert listen['HOSTED_TRANSLATION_API_URL']['value'] == gke_translation
        assert listen['HOSTED_PARAKEET_API_URL']['value'] == f'http://parakeet.{domain}'
    for chart in ('backend-listen', 'pusher', 'parakeet'):
        assert _chart(chart, env)['HOSTED_SPEAKER_EMBEDDING_API_URL'] == gke_embedding
    listen_chart = _chart('backend-listen', env)
    assert listen_chart['HOSTED_TRANSLATION_API_URL'] == gke_translation
    assert listen_chart['HOSTED_VAD_API_URL'] == gke_vad
    assert listen_chart['HOSTED_PARAKEET_API_URL'] == f'http://parakeet.{domain}'
    assert _chart('pusher', env)['HOSTED_PARAKEET_API_URL'] == f'http://parakeet.{domain}'
    if in_cluster:
        assert listen_chart['HOSTED_PUSHER_API_URL'] == IN_CLUSTER_PUSHER


def test_prod_in_cluster_callers_stay_off_internal_alb_routes():
    """Prod GKE charts route every same-cluster dependency by ClusterIP DNS."""
    listen_chart = _chart('backend-listen', 'prod')
    assert listen_chart['HOSTED_PUSHER_API_URL'] == IN_CLUSTER_PUSHER
    assert listen_chart['HOSTED_VAD_API_URL'] == IN_CLUSTER_VAD
    assert listen_chart['HOSTED_SPEAKER_EMBEDDING_API_URL'] == IN_CLUSTER_EMBEDDING
    assert listen_chart['HOSTED_TRANSLATION_API_URL'] == IN_CLUSTER_NLLB
    assert _chart('pusher', 'prod')['HOSTED_SPEAKER_EMBEDDING_API_URL'] == IN_CLUSTER_EMBEDDING
    assert _chart('parakeet', 'prod')['HOSTED_SPEAKER_EMBEDDING_API_URL'] == IN_CLUSTER_EMBEDDING
    # The reviewed diarizer-batch cohort stage still binds pusher and Cloud Run to the
    # shared gateway route (config/diarization-cohort-stages.json pins the URL).
    assert _chart('pusher', 'prod')['HOSTED_DIARIZATION_API_URL'] == 'http://172.16.160.20/diarizer-batch'
