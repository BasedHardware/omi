from __future__ import annotations

# pyright: reportPrivateUsage=false

from pathlib import Path
import sys
from typing import Any

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from scripts import resume_cloud_run_deploy as resume  # noqa: E402

SOURCE_SHA = 'b939eab902c88abc6cc64501747485d6aec428d3'
DIGEST = f'sha256:{"d" * 64}'
IMAGE = 'gcr.io/example/backend:b939eab'


def _candidates() -> list[resume.Candidate]:
    return [resume.Candidate(service, f'{service}-b939eab-1') for service in resume.PROMOTION_ORDER]


def _revision(service: str, *, digest: str = DIGEST, source_sha: str = SOURCE_SHA) -> dict[str, Any]:
    return {
        'metadata': {
            'name': f'{service}-b939eab-1',
            'labels': {'commit-sha': source_sha},
        },
        'spec': {'containers': [{'image': f'gcr.io/example/backend@{digest}'}]},
        'status': {'conditions': [{'type': 'Ready', 'status': 'True', 'reason': 'Retired'}]},
    }


def _service(
    service: str,
    serving: str,
    *,
    latest_created: str | None = None,
    tag: str | None = None,
    tagged_revision: str | None = None,
) -> dict[str, Any]:
    status_traffic: list[dict[str, Any]] = [{'revisionName': serving, 'percent': 100}]
    spec_traffic: list[dict[str, Any]] = [{'revisionName': serving, 'percent': 100}]
    if tag:
        tagged = {
            'revisionName': tagged_revision or f'{service}-b939eab-1',
            'tag': tag,
            'url': f'https://{tag}---{service}.example',
        }
        status_traffic.append(tagged)
        spec_traffic.append({key: value for key, value in tagged.items() if key != 'url'})
    return {
        'spec': {'traffic': spec_traffic},
        'status': {
            'url': f'https://{service}.example',
            'latestCreatedRevisionName': latest_created or f'{service}-b939eab-1',
            'traffic': status_traffic,
        },
    }


def _install_candidate_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    traffic: dict[str, str] | None = None,
    revisions: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, str], set[str], list[list[str]]]:
    traffic = traffic or {service: f'{service}-old' for service in resume.PROMOTION_ORDER}
    tagged: set[str] = set()
    commands: list[list[str]] = []
    revisions = revisions or {candidate.service: _revision(candidate.service) for candidate in _candidates()}

    def fake_describe_revision(revision: str, *, project: str, region: str) -> dict[str, Any]:
        service = next(service for service in resume.PROMOTION_ORDER if revision.startswith(f'{service}-'))
        return revisions[service]

    def fake_describe_service(service: str, *, project: str, region: str) -> dict[str, Any]:
        return _service(
            service,
            traffic[service],
            tag='resume-test' if service in tagged else None,
        )

    def fake_run(command: list[str]) -> None:
        commands.append(command)
        service = command[4]
        if any(part.startswith('--update-tags=') for part in command):
            tagged.add(service)
        if any(part.startswith('--remove-tags=') for part in command):
            tagged.discard(service)
        for part in command:
            if part.startswith('--to-revisions='):
                traffic[service] = part.removeprefix('--to-revisions=').split('=', 1)[0]

    monkeypatch.setattr(resume, '_describe_revision', fake_describe_revision)
    monkeypatch.setattr(resume, '_describe_service', fake_describe_service)
    monkeypatch.setattr(resume, '_run', fake_run)
    monkeypatch.setattr(resume, '_identity_token', lambda audience: 'opaque-token')
    return traffic, tagged, commands


def test_parse_candidates_requires_exact_set_and_returns_dependency_order() -> None:
    entries = [f'{service}={service}-b939eab-1' for service in reversed(resume.PROMOTION_ORDER)]

    assert [candidate.service for candidate in resume.parse_candidates(entries)] == list(resume.PROMOTION_ORDER)

    with pytest.raises(ValueError, match='missing=backend'):
        resume.parse_candidates(entries[:-1])
    with pytest.raises(ValueError, match='unexpected=other'):
        resume.parse_candidates([*entries, 'other=other-b939eab-1'])

    existing = [f'{service}={service}-b939eab-1' for service in reversed(resume.EXISTING_CANDIDATE_ORDER)]
    assert [candidate.service for candidate in resume.parse_existing_candidates(existing)] == list(
        resume.EXISTING_CANDIDATE_ORDER
    )


def test_existing_candidate_verification_is_read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _, _, commands = _install_candidate_fakes(monkeypatch)
    existing = [resume.Candidate(service, f'{service}-b939eab-1') for service in resume.EXISTING_CANDIDATE_ORDER]

    resume._validate_candidate_set(
        existing,
        project='project',
        region='region',
        source_sha=SOURCE_SHA,
        expected_digest=DIGEST,
        expected_order=resume.EXISTING_CANDIDATE_ORDER,
    )

    assert commands == []


def test_integration_plan_creates_absent_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(resume, '_try_describe_revision', lambda *args, **kwargs: None)

    assert (
        resume.integration_plan(
            resume.Candidate('backend-integration', 'backend-integration-b939eab-1'),
            project='project',
            region='region',
            source_sha=SOURCE_SHA,
            expected_digest=DIGEST,
        )
        == 'create'
    )


def test_integration_plan_reuses_only_exact_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    candidate = resume.Candidate('backend-integration', 'backend-integration-b939eab-1')
    monkeypatch.setattr(resume, '_try_describe_revision', lambda *args, **kwargs: _revision(candidate.service))
    monkeypatch.setattr(
        resume,
        '_describe_service',
        lambda *args, **kwargs: _service(candidate.service, 'backend-integration-old'),
    )

    assert (
        resume.integration_plan(
            candidate,
            project='project',
            region='region',
            source_sha=SOURCE_SHA,
            expected_digest=DIGEST,
        )
        == 'reuse'
    )

    monkeypatch.setattr(
        resume, '_try_describe_revision', lambda *args, **kwargs: _revision(candidate.service, digest='sha256:bad')
    )
    with pytest.raises(RuntimeError, match='does not match'):
        resume.integration_plan(
            candidate,
            project='project',
            region='region',
            source_sha=SOURCE_SHA,
            expected_digest=DIGEST,
        )


def test_validate_candidates_uses_child_digest_and_smokes_control_plane_before_cutover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    traffic, tagged, commands = _install_candidate_fakes(monkeypatch)
    control_plane_urls: list[tuple[str, str | None]] = []
    monkeypatch.setattr(resume, '_http_status', lambda url, token=None: 200)
    monkeypatch.setattr(
        resume,
        'verify_control_plane',
        lambda url, token=None: control_plane_urls.append((url, token)),
    )

    resume.validate_candidates(
        _candidates(),
        project='project',
        region='region',
        source_sha=SOURCE_SHA,
        expected_digest=DIGEST,
        candidate_tag='resume-test',
    )

    assert traffic == {service: f'{service}-old' for service in resume.PROMOTION_ORDER}
    assert tagged == set()
    assert control_plane_urls == [('https://resume-test---backend.example', 'opaque-token')]
    assert len([command for command in commands if any('--update-tags=' in part for part in command)]) == 4
    assert len([command for command in commands if any('--remove-tags=' in part for part in command)]) == 4
    assert all(command[1:3] == ['run', 'services'] for command in commands)


def test_validate_candidates_rejects_source_digest_or_latest_revision_before_tagging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad_revisions = {candidate.service: _revision(candidate.service) for candidate in _candidates()}
    bad_revisions['backend'] = _revision('backend', digest=f'sha256:{"a" * 64}')
    _, _, commands = _install_candidate_fakes(monkeypatch, revisions=bad_revisions)

    with pytest.raises(RuntimeError, match='image digest'):
        resume.validate_candidates(
            _candidates(),
            project='project',
            region='region',
            source_sha=SOURCE_SHA,
            expected_digest=DIGEST,
            candidate_tag='resume-test',
        )
    assert commands == []

    bad_revisions['backend'] = _revision('backend', source_sha='0' * 40)
    with pytest.raises(RuntimeError, match='source label'):
        resume.validate_candidates(
            _candidates(),
            project='project',
            region='region',
            source_sha=SOURCE_SHA,
            expected_digest=DIGEST,
            candidate_tag='resume-test',
        )


def test_validate_candidates_cleans_tags_and_reports_manual_recovery_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, tagged, commands = _install_candidate_fakes(monkeypatch)
    monkeypatch.setattr(resume, '_http_status', lambda url, token=None: 503)

    with pytest.raises(RuntimeError, match='health returned HTTP 503'):
        resume.validate_candidates(
            _candidates(),
            project='project',
            region='region',
            source_sha=SOURCE_SHA,
            expected_digest=DIGEST,
            candidate_tag='resume-test',
        )

    assert tagged == set()
    assert any(any('--remove-tags=resume-test' in part for part in command) for command in commands)


def test_validate_candidates_cleans_attempted_tag_when_gcloud_mutates_then_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, tagged, commands = _install_candidate_fakes(monkeypatch)
    original_run = resume._run
    injected = False

    def mutate_then_raise(command: list[str]) -> None:
        nonlocal injected
        is_candidate_tag = any(part.startswith('--update-tags=') for part in command)
        if not injected and command[4] == 'backend-integration' and is_candidate_tag:
            injected = True
            original_run(command)
            raise RuntimeError('ambiguous tag update failure')
        original_run(command)

    monkeypatch.setattr(resume, '_run', mutate_then_raise)

    with pytest.raises(RuntimeError, match='ambiguous tag update failure'):
        resume.validate_candidates(
            _candidates(),
            project='project',
            region='region',
            source_sha=SOURCE_SHA,
            expected_digest=DIGEST,
            candidate_tag='resume-test',
        )

    assert tagged == set()
    assert any(command[4] == 'backend-integration' and '--remove-tags=resume-test' in command for command in commands)


def test_promote_uses_dependency_order_and_rolls_back_verified_traffic(monkeypatch: pytest.MonkeyPatch) -> None:
    traffic, _, _ = _install_candidate_fakes(monkeypatch)
    shifts: list[tuple[str, str]] = []
    original_run = resume._run

    def recording_run(command: list[str]) -> None:
        if any(part.startswith('--to-revisions=') for part in command):
            target = next(part for part in command if part.startswith('--to-revisions='))
            shifts.append((command[4], target.removeprefix('--to-revisions=').split('=', 1)[0]))
        original_run(command)

    monkeypatch.setattr(resume, '_run', recording_run)

    def fake_status(url: str, *, token: str | None = None) -> int:
        return 503 if 'backend-sync.example' in url else 200

    monkeypatch.setattr(resume, '_http_status', fake_status)

    with pytest.raises(RuntimeError, match='traffic was rolled back'):
        resume.promote_candidates(
            _candidates(),
            project='project',
            region='region',
            source_sha=SOURCE_SHA,
            expected_digest=DIGEST,
            control_plane_url='https://api.example',
        )

    assert shifts[:3] == [
        ('backend-integration', 'backend-integration-b939eab-1'),
        ('backend-sync-backfill', 'backend-sync-backfill-b939eab-1'),
        ('backend-sync', 'backend-sync-b939eab-1'),
    ]
    assert shifts[-4:] == [
        ('backend', 'backend-old'),
        ('backend-sync', 'backend-sync-old'),
        ('backend-sync-backfill', 'backend-sync-backfill-old'),
        ('backend-integration', 'backend-integration-old'),
    ]
    assert traffic == {service: f'{service}-old' for service in resume.PROMOTION_ORDER}


def test_promote_reconciles_all_services_when_gcloud_mutates_then_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    traffic, _, commands = _install_candidate_fakes(monkeypatch)
    original_run = resume._run
    injected = False

    def mutate_then_raise(command: list[str]) -> None:
        nonlocal injected
        target = next((part for part in command if part.startswith('--to-revisions=')), '')
        if not injected and target.startswith('--to-revisions=backend-integration-b939eab-1='):
            injected = True
            original_run(command)
            raise RuntimeError('ambiguous traffic update failure')
        original_run(command)

    monkeypatch.setattr(resume, '_run', mutate_then_raise)

    with pytest.raises(RuntimeError, match='traffic was rolled back: ambiguous traffic update failure'):
        resume.promote_candidates(
            _candidates(),
            project='project',
            region='region',
            source_sha=SOURCE_SHA,
            expected_digest=DIGEST,
            control_plane_url='https://api.example',
        )

    rollback_commands = [
        command
        for command in commands
        if any(part.endswith('-old=100') for part in command if part.startswith('--to-revisions='))
    ]
    assert [command[4] for command in rollback_commands] == list(reversed(resume.PROMOTION_ORDER))
    assert traffic == {service: f'{service}-old' for service in resume.PROMOTION_ORDER}


def test_post_cutover_control_plane_failure_rolls_back_all_services(monkeypatch: pytest.MonkeyPatch) -> None:
    traffic, _, _ = _install_candidate_fakes(monkeypatch)
    monkeypatch.setattr(resume, '_http_status', lambda url, token=None: 200)
    monkeypatch.setattr(
        resume, 'verify_control_plane', lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('missing route'))
    )

    with pytest.raises(RuntimeError, match='traffic was rolled back'):
        resume.promote_candidates(
            _candidates(),
            project='project',
            region='region',
            source_sha=SOURCE_SHA,
            expected_digest=DIGEST,
            control_plane_url='https://api.example',
        )

    assert traffic == {service: f'{service}-old' for service in resume.PROMOTION_ORDER}


def test_rollback_failure_reports_exact_manual_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_candidate_fakes(monkeypatch)
    original_run = resume._run

    def fail_one_rollback(command: list[str]) -> None:
        target = next((part for part in command if part.startswith('--to-revisions=')), '')
        if command[4] == 'backend-sync' and target.startswith('--to-revisions=backend-sync-old='):
            raise RuntimeError('simulated rollback failure')
        original_run(command)

    monkeypatch.setattr(resume, '_run', fail_one_rollback)
    monkeypatch.setattr(
        resume,
        '_http_status',
        lambda url, token=None: 503 if 'backend-sync.example' in url else 200,
    )

    with pytest.raises(
        RuntimeError, match=r'rollback also failed: .*manual recovery: gcloud run services update-traffic'
    ):
        resume.promote_candidates(
            _candidates(),
            project='project',
            region='region',
            source_sha=SOURCE_SHA,
            expected_digest=DIGEST,
            control_plane_url='https://api.example',
        )


def test_verify_control_plane_requires_post_routes_and_safe_method_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        resume,
        '_http_json',
        lambda url, token=None: {'paths': {path: {'post': {}} for path in resume.CONTROL_PLANE_PATHS}},
    )
    seen: list[tuple[str, str | None]] = []

    def fake_status(url: str, *, token: str | None = None) -> int:
        seen.append((url, token))
        return 405

    monkeypatch.setattr(resume, '_http_status', fake_status)

    resume.verify_control_plane('https://candidate.example/', token='opaque-token')

    assert seen == [(f'https://candidate.example{path}', 'opaque-token') for path in resume.CONTROL_PLANE_PATHS]


def _gke_documents(desired: int = 3) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    deployment = {
        'metadata': {'generation': 7},
        'spec': {
            'replicas': desired,
            'template': {
                'spec': {
                    'containers': [
                        {
                            'image': IMAGE,
                            'env': [{'name': 'GOOGLE_CLOUD_PROJECT', 'value': 'based-hardware'}],
                        }
                    ]
                }
            },
        },
        'status': {
            'observedGeneration': 7,
            'replicas': desired,
            'updatedReplicas': desired,
            'readyReplicas': desired,
            'availableReplicas': desired,
            'unavailableReplicas': 0,
            'conditions': [{'type': 'Available', 'status': 'True'}],
        },
    }
    hpa = {
        'status': {
            'currentReplicas': desired,
            'desiredReplicas': desired,
            'conditions': [
                {'type': 'AbleToScale', 'status': 'True'},
                {'type': 'ScalingActive', 'status': 'True'},
            ],
        }
    }
    current_rs = {
        'metadata': {'name': 'current'},
        'spec': {
            'replicas': desired,
            'template': {'spec': {'containers': [{'image': IMAGE}]}},
        },
        'status': {'replicas': desired, 'readyReplicas': desired},
    }
    old_rs = {
        'metadata': {'name': 'old'},
        'spec': {
            'replicas': 0,
            'template': {'spec': {'containers': [{'image': 'gcr.io/example/backend:old'}]}},
        },
        'status': {'replicas': 0},
    }
    pods = {
        'items': [
            {
                'metadata': {'name': f'pod-{index}'},
                'status': {
                    'phase': 'Running',
                    'conditions': [{'type': 'Ready', 'status': 'True'}],
                    'containerStatuses': [
                        {'ready': True, 'restartCount': 0, 'state': {'running': {'startedAt': 'now'}}}
                    ],
                },
            }
            for index in range(desired)
        ]
    }
    return deployment, hpa, {'items': [old_rs, current_rs]}, pods


def test_gke_gate_validation_requires_full_rollout_and_no_old_or_pending_capacity() -> None:
    documents = _gke_documents()
    assert (
        resume.validate_gke_documents(
            *documents,
            expected_image=IMAGE,
            expected_runtime_project='based-hardware',
        )
        == []
    )

    deployment, hpa, replica_sets, pods = _gke_documents()
    deployment['status']['unavailableReplicas'] = 1
    hpa['status']['desiredReplicas'] = 4
    hpa['status']['conditions'][1]['status'] = 'False'
    replica_sets['items'][0]['spec']['replicas'] = 1
    replica_sets['items'][0]['status']['replicas'] = 1
    pods['items'][0]['status']['phase'] = 'Pending'
    errors = resume.validate_gke_documents(
        deployment,
        hpa,
        replica_sets,
        pods,
        expected_image='wrong-image',
        expected_runtime_project='wrong-project',
    )

    assert any('unavailableReplicas=1' in item for item in errors)
    assert any('HPA desiredReplicas=4' in item for item in errors)
    assert any('HPA ScalingActive condition is not True' in item for item in errors)
    assert any('old ReplicaSet old' in item for item in errors)
    assert any('pod pod-0 is not Running' in item for item in errors)
    assert any('deployment image' in item for item in errors)
    assert any('GOOGLE_CLOUD_PROJECT=based-hardware expected=wrong-project' in item for item in errors)


def test_gke_gate_requires_continuous_stable_dwell(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [0.0]
    samples = [0]
    monkeypatch.setattr(
        resume, '_load_gke_documents', lambda **kwargs: (samples.__setitem__(0, samples[0] + 1) or _gke_documents())
    )
    monkeypatch.setattr(resume.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(resume.time, 'sleep', lambda seconds: clock.__setitem__(0, clock[0] + seconds))

    resume.gate_gke_rollout(
        namespace='namespace',
        deployment='deployment',
        hpa='hpa',
        selector='selector',
        expected_image=IMAGE,
        expected_runtime_project='based-hardware',
        dwell_seconds=20,
        poll_interval_seconds=10,
        timeout_seconds=30,
    )

    assert samples[0] == 3


def test_workflow_resume_lane_is_pinned_isolated_and_serialized() -> None:
    workflow = (REPO_ROOT / '.github/workflows/gcp_backend.yml').read_text(encoding='utf-8')
    helm_workflow = (REPO_ROOT / '.github/workflows/gcp_backend_listen_helm.yml').read_text(encoding='utf-8')
    resume_block = workflow.split('  resume-cloud-run:', 1)[1].split('\n  deploy:', 1)[0]

    assert '- resume-cloud-run' in workflow
    assert 'ref: ${{ github.sha }}' in resume_block
    assert 'integration-plan' in resume_block
    assert 'verify-existing' in resume_block
    assert 'gke-gate' in resume_block
    assert 'backend/scripts/resume_cloud_run_deploy.py validate' in resume_block
    assert 'backend/scripts/resume_cloud_run_deploy.py promote' in resume_block
    assert '--check-secrets' in resume_block
    assert '--check-traffic' in resume_block
    assert '--repair-traffic' not in resume_block
    assert 'GCP_PROJECT_ID: ${{ vars.GCP_PROJECT_ID }}' in resume_block
    assert 'ENV: ${{ vars.ENV }}' in resume_block
    assert 'GKE_CLUSTER: ${{ vars.GKE_CLUSTER }}' in resume_block
    assert 'RUNTIME_GCP_PROJECT_ID: ${{ vars.RUNTIME_GCP_PROJECT_ID }}' in resume_block
    assert '[[ "$GCP_PROJECT_ID" != "based-hardware" ]]' in resume_block
    assert '[[ "$ENV" != "prod" ]]' in resume_block
    assert '[[ "$GKE_CLUSTER" != "prod-omi-gke" ]]' in resume_block
    assert '[[ "$RUNTIME_GCP_PROJECT_ID" != "based-hardware" ]]' in resume_block
    assert '${{ vars.CONTROL_PLANE_URL }}' in resume_block
    assert '${{ vars.API_URL }}' not in resume_block
    assert 'CONTROL_PLANE_URL must be exactly https://api.omi.me for production resume' in resume_block
    assert (
        'gcr.io/${{ vars.GCP_PROJECT_ID }}/${{ env.SERVICE }}@${{ github.event.inputs.expected_revision_digest }}'
        in resume_block
    )
    assert 'if: steps.integration-plan.outputs.action == \'create\'' in resume_block
    assert 'Build and Push Docker image' not in resume_block
    assert 'helm ' not in resume_block.lower()
    assert 'deploy-backend-secrets' not in resume_block
    assert 'sync-backfill-lifecycle' not in resume_block
    assert '${GITHUB_RUN_ID}' in workflow
    assert workflow.count('ref: ${{ github.sha }}') == 3
    assert 'ref: ${{ github.event.inputs.branch }}' not in workflow
    assert 'branch input must match the dispatched ref' in workflow
    assert 'group: backend-deploy-${{ github.event.inputs.environment || \'development\' }}' in helm_workflow
    assert 'RUNTIME_GCP_PROJECT_ID must be set before backend-listen Helm deployment' in workflow
    assert 'RUNTIME_GCP_PROJECT_ID must be set before backend-listen Helm deployment' in helm_workflow
    assert 'ref: ${{ github.sha }}' in helm_workflow
    assert helm_workflow.index('Validate runtime GCP project') < helm_workflow.index('Install Helm')
    deploy_block = workflow.split('\n  deploy:', 1)[1]
    assert deploy_block.index('RUNTIME_GCP_PROJECT_ID must be set') < deploy_block.index('Build and Push Docker image')
    current_revision_block = deploy_block.split('      - name: Verify validated revisions are still current', 1)[
        1
    ].split('      - name: Shift Cloud Run traffic to validated revisions', 1)[0]
    assert current_revision_block.count('--project=${{ vars.GCP_PROJECT_ID }}') == 4


def test_resume_helper_never_resolves_mutable_container_tag() -> None:
    source = (BACKEND_ROOT / 'scripts/resume_cloud_run_deploy.py').read_text(encoding='utf-8')

    assert 'container images describe' not in source
    assert 'expected-digest' in source
