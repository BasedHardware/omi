"""Contract for development Pusher image freshness on shared runtime imports."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
WORKFLOW = REPO / '.github/workflows/gcp_backend_pusher_auto_deploy.yml'


def test_pusher_auto_deploy_tracks_its_shared_lifecycle_and_observability_imports():
    lines = WORKFLOW.read_text(encoding='utf-8').splitlines()
    paths_start = lines.index('    paths:') + 1
    paths = set()
    for line in lines[paths_start:]:
        if not line.startswith('      - '):
            break
        paths.add(line.split("'", 2)[1])

    assert paths == {
        'backend/config/**',
        'backend/database/**',
        'backend/models/**',
        'backend/routers/**',
        'backend/services/**',
        'backend/utils/**',
        'backend/testing/parity_pack_v0/**',
        'backend/pusher/**',
        'backend/charts/pusher/**',
        '.dockerignore',
        'backend/scripts/verify_pusher_source_closure.py',
        'backend/scripts/verify_pusher_live_deployment_gate.py',
        'backend/scripts/verify_pusher_dev_observability.py',
        'backend/scripts/verify_pusher_promotion_evidence.py',
        'backend/scripts/pusher_release_receipt.py',
        'backend/scripts/pusher_semantic_probe.py',
        'backend/scripts/pusher_prod_canary.py',
        'backend/scripts/verify_pusher_live_alert_route.py',
        'backend/scripts/runtime_env_capability_contracts.py',
        'backend/scripts/runtime_env_validation/**',
        'backend/scripts/validate-backend-runtime-env.py',
        'backend/deploy/runtime_env/**',
        'backend/scripts/firebase_release_probe_token.py',
        'backend/testing/release_fixtures/transcription-release-probe.json',
        'backend/testing/release_fixtures/transcription-release-probe.wav',
        '.github/workflows/gcp_backend_pusher_auto_deploy.yml',
        '.github/workflows/gcp_backend_pusher.yml',
    }
