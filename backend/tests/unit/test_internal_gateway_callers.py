"""Speaker-ID route topology: in-cluster callers on ClusterIP, Cloud Run on the internal ALB.

Cloud Run cannot resolve Kubernetes DNS, so its services keep the internal-ALB routes
(per-GB inbound). GKE workloads in the same cluster as the target services use the
ClusterIP service DNS and pay nothing per GB. Prod routes in-cluster traffic off the
ALBs. The dev shared gateway VIP (172.16.48.49) was deleted 2026-11-02, so the dev
listen/pusher/Cloud Run bindings use the documented rollback Ingress endpoints
(backend/docs/internal-gateway-callers.md); prod keeps the gateway routes. The
parakeet chart is frozen against main by the audio-fleet contract
(test_audio_fleet_helm), so its dev fallback still binds the dead gateway VIP
until the audio-fleet owner lands the separately qualified switch.
"""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]

IN_CLUSTER_EMBEDDING = 'http://prod-omi-diarizer.prod-omi-backend.svc.cluster.local:8080'
IN_CLUSTER_VAD = 'http://prod-omi-vad.prod-omi-backend.svc.cluster.local:8080/v1/vad'
IN_CLUSTER_PUSHER = 'http://prod-omi-pusher.prod-omi-backend.svc.cluster.local:8080'

# Dev rollback endpoints restored after the shared internal gateway VIP was deleted.
DEV_LEGACY_EMBEDDING = 'http://diarizer.omiapi.com:80'
DEV_LEGACY_TRANSLATION = 'http://nllb.omiapi.com'
DEV_LEGACY_VAD = 'http://vad.omiapi.com:80/v1/vad'
# The parakeet chart may not drift from main (audio-fleet contract), so its dev
# fallback still binds the deleted gateway VIP; moving it is the audio-fleet
# owner's separately qualified change.
DEV_FROZEN_PARAKEET_EMBEDDING = 'http://172.16.48.49/diarizer'

PROD_GATEWAY_IP = '172.16.160.20'


def _chart(chart, env):
    path = ROOT / f'backend/charts/{chart}/{env}_omi_{chart.replace("-", "_")}_values.yaml'
    return {entry['name']: entry.get('value') for entry in yaml.load(path.read_text(), Loader=yaml.CSafeLoader)['env']}


@pytest.mark.parametrize('env', ['dev', 'prod'])
def test_gateway_caller_bindings_cover_all_speaker_id_hosts(env):
    manifest = yaml.load((ROOT / 'backend/deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)[
        'environments'
    ][env]
    overlay = yaml.load((ROOT / f'backend/deploy/runtime_env/{env}.overlay.yaml').read_text(), Loader=yaml.CSafeLoader)[
        'overlay'
    ]
    in_cluster = env == 'prod'
    gke_embedding = IN_CLUSTER_EMBEDDING if in_cluster else DEV_LEGACY_EMBEDDING
    # Prod NLLB is retired (translation runs on Luna), so prod binds no translation URL.
    gke_translation = None if in_cluster else DEV_LEGACY_TRANSLATION
    gke_vad = IN_CLUSTER_VAD if in_cluster else DEV_LEGACY_VAD
    cloud_run_embedding = f'http://{PROD_GATEWAY_IP}/diarizer' if in_cluster else DEV_LEGACY_EMBEDDING
    parakeet_embedding = f'http://{PROD_GATEWAY_IP}/diarizer' if in_cluster else DEV_FROZEN_PARAKEET_EMBEDDING
    domain = 'omi.me' if in_cluster else 'omiapi.com'
    for source in (manifest, overlay):
        for host in ('backend-listen', 'pusher'):
            assert source['gke'][host]['env']['HOSTED_SPEAKER_EMBEDDING_API_URL']['value'] == gke_embedding
        for host in ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration'):
            values = source['cloud_run']['services'][host]['env']
            # Cloud Run must stay on an internal-ALB route; it cannot resolve cluster DNS.
            assert values['HOSTED_SPEAKER_EMBEDDING_API_URL']['value'] == cloud_run_embedding
            assert values['HOSTED_PARAKEET_API_URL']['value'] == f'http://parakeet.{domain}'
        listen = source['gke']['backend-listen']['env']
        assert listen.get('HOSTED_TRANSLATION_API_URL', {}).get('value') == gke_translation
        assert listen['HOSTED_PARAKEET_API_URL']['value'] == f'http://parakeet.{domain}'
    for chart in ('backend-listen', 'pusher'):
        assert _chart(chart, env)['HOSTED_SPEAKER_EMBEDDING_API_URL'] == gke_embedding
    # Parakeet's helm contract freezes its template against main (only the two
    # dark flags and the language gate may drift), so both environments keep
    # the gateway binding; dev's points at the deleted VIP until the
    # audio-fleet owner lands the separately qualified switch.
    assert _chart('parakeet', env)['HOSTED_SPEAKER_EMBEDDING_API_URL'] == parakeet_embedding
    listen_chart = _chart('backend-listen', env)
    assert listen_chart.get('HOSTED_TRANSLATION_API_URL') == gke_translation
    assert listen_chart['HOSTED_VAD_API_URL'] == gke_vad
    assert listen_chart['HOSTED_PARAKEET_API_URL'] == f'http://parakeet.{domain}'
    assert _chart('pusher', env)['HOSTED_PARAKEET_API_URL'] == f'http://parakeet.{domain}'
    if in_cluster:
        assert listen_chart['HOSTED_PUSHER_API_URL'] == IN_CLUSTER_PUSHER


def test_prod_in_cluster_callers_stay_off_internal_alb_routes():
    """Prod listen and pusher route same-cluster dependencies by ClusterIP DNS.

    Parakeet stays on the shared gateway: its helm contract forbids this
    template change until a separate qualification. The diarizer-batch cohort
    stage is the other exception and still binds the gateway route.
    """
    listen_chart = _chart('backend-listen', 'prod')
    assert listen_chart['HOSTED_PUSHER_API_URL'] == IN_CLUSTER_PUSHER
    assert listen_chart['HOSTED_VAD_API_URL'] == IN_CLUSTER_VAD
    assert listen_chart['HOSTED_SPEAKER_EMBEDDING_API_URL'] == IN_CLUSTER_EMBEDDING
    assert 'HOSTED_TRANSLATION_API_URL' not in listen_chart
    assert _chart('pusher', 'prod')['HOSTED_SPEAKER_EMBEDDING_API_URL'] == IN_CLUSTER_EMBEDDING
    assert _chart('parakeet', 'prod')['HOSTED_SPEAKER_EMBEDDING_API_URL'] == 'http://172.16.160.20/diarizer'
    # The reviewed diarizer-batch cohort stage still binds pusher and Cloud Run to the
    # shared gateway route (config/diarization-cohort-stages.json pins the URL).
    assert _chart('pusher', 'prod')['HOSTED_DIARIZATION_API_URL'] == 'http://172.16.160.20/diarizer-batch'
