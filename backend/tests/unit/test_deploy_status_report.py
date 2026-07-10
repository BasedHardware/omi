from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from scripts.deploy_status_report import (
    Finding,
    load_json,
    parse_expected_traffic,
    render_cloud_run_report,
    render_gke_report,
)
from scripts.verify_k8s_secret_keys import expected_keys

FIXTURES = BACKEND_ROOT / 'tests' / 'fixtures' / 'deploy_status'


def test_gke_report_flags_incomplete_rollout_bad_pod_and_stale_replicaset() -> None:
    state = load_json(FIXTURES / 'k8s_rollout_problem.json')

    report, findings = render_gke_report(
        state,
        namespace='prod-omi-backend',
        services=['backend-listen'],
        now=datetime(2026, 7, 1, 12, 45, tzinfo=timezone.utc),
        stale_rs_threshold_minutes=15,
    )

    assert '| `prod-omi-backend-listen` | 3 | 2 | 1 | `gcr.io/example/backend:abc1234` | stale-controller |' in report
    assert '- 3x `BackOff`: Back-off restarting failed container backend' in report
    assert (
        Finding(
            'FAIL',
            'prod-omi-backend-listen',
            'rollout incomplete: desired=3 updated=2 available=1',
        )
        in findings
    )
    assert Finding('FAIL', 'prod-omi-backend-listen-abc-pod', 'container waiting reason CrashLoopBackOff') in findings
    assert (
        Finding(
            'WARN',
            'prod-omi-backend-listen-old',
            'old ReplicaSet still has 1 replica(s) after 45m',
        )
        in findings
    )
    assert Finding('FAIL', 'prod-omi-backend-listen', 'unavailable replicas remain: 2') in findings
    assert (
        Finding(
            'FAIL',
            'prod-omi-backend-listen',
            'controller has not observed latest generation: generation=43 observed=42',
        )
        in findings
    )


def test_cloud_run_report_requires_ready_revision_to_serve_expected_traffic() -> None:
    state = load_json(FIXTURES / 'cloud_run_traffic_problem.json')

    report, findings = render_cloud_run_report(
        state,
        services=['backend', 'backend-sync'],
        expected_traffic=parse_expected_traffic(
            [
                'backend=backend-abc1234-1',
                'backend-sync=backend-sync-abc1234-1',
            ]
        ),
        project='based-hardware',
        region='us-central1',
    )

    assert '`backend-old9999-1`=100%' in report
    assert (
        '`gcr.io/example/backend:abc1234@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`'
        in report
    )
    assert '`backend-sync-abc1234-1` | `backend-sync-old9999-1`' in report
    assert (
        Finding(
            'FAIL',
            'backend',
            'expected revision backend-abc1234-1 to serve 100% traffic, observed 0%',
        )
        in findings
    )
    assert (
        Finding(
            'FAIL',
            'backend-sync',
            'latest created revision backend-sync-abc1234-1 is not latest ready (backend-sync-old9999-1)',
        )
        in findings
    )


def test_cloud_run_report_fails_when_expected_service_is_missing() -> None:
    report, findings = render_cloud_run_report(
        {'services': []},
        services=['backend'],
        expected_traffic=parse_expected_traffic(['backend=backend-abc1234-1']),
    )

    assert '| `backend` | - | - | - | - | - | missing |' in report
    assert (
        Finding(
            'FAIL',
            'backend',
            'expected revision backend-abc1234-1 to serve 100% traffic, but service data is missing',
        )
        in findings
    )


def test_cloud_run_report_fails_when_describe_failed() -> None:
    report, findings = render_cloud_run_report(
        {'services': [], 'errors': [{'service': 'backend', 'exitCode': 1}]},
        services=['backend'],
        expected_traffic=parse_expected_traffic(['backend=backend-abc1234-1']),
    )

    assert '| `backend` | - | - | - | - | - | missing |' in report
    assert Finding('FAIL', 'backend', 'gcloud run services describe failed with exit code 1') in findings


def test_cloud_run_report_flags_spec_status_mismatch_and_emits_repair_command() -> None:
    state = load_json(FIXTURES / 'cloud_run_spec_status_mismatch.json')

    report, findings = render_cloud_run_report(
        state,
        services=['backend'],
        expected_traffic={},
        project='based-hardware',
        region='us-central1',
    )

    assert '`backend-failed-1`=100%' in report
    assert '`backend-good-1`=100%' in report
    assert (
        Finding(
            'FAIL',
            'backend',
            'spec.traffic (backend-failed-1) != status.traffic (backend-good-1); repair: '
            'gcloud run services update-traffic backend --project=based-hardware '
            '--region=us-central1 --to-revisions=backend-good-1=100 --quiet',
        )
        in findings
    )


def test_cloud_run_report_uses_state_project_region_when_cli_project_missing() -> None:
    state = load_json(FIXTURES / 'cloud_run_spec_status_mismatch.json')
    state = {**state, 'project': 'saved-project', 'region': 'europe-west1'}

    _, findings = render_cloud_run_report(
        state,
        services=['backend'],
        expected_traffic={},
    )

    assert (
        Finding(
            'FAIL',
            'backend',
            'spec.traffic (backend-failed-1) != status.traffic (backend-good-1); repair: '
            'gcloud run services update-traffic backend --project=saved-project '
            '--region=europe-west1 --to-revisions=backend-good-1=100 --quiet',
        )
        in findings
    )


def test_secret_key_verifier_reads_expected_keys_without_secret_values() -> None:
    assert expected_keys(FIXTURES / 'backend_secrets_values.yaml') == {'OPENAI_API_KEY', 'SENTINEL_FAKE_ONLY'}
