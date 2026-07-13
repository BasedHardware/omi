from __future__ import annotations

import json
from typing import Sequence

import pytest

from scripts import verify_sync_ledger_fence_transition as verifier


class FakeCloudRunner:
    """Read-only fake for Cloud Run service/revision describe commands."""

    def __init__(self, *, service_documents: dict[str, dict], revision_documents: dict[str, dict]) -> None:
        self.service_documents = service_documents
        self.revision_documents = revision_documents
        self.commands: list[list[str]] = []

    def run(self, command: Sequence[str], *, check: bool = True) -> verifier.CommandResult:
        command = list(command)
        self.commands.append(command)
        if command[:4] == ['gcloud', 'run', 'services', 'describe']:
            return verifier.CommandResult(returncode=0, stdout=json.dumps(self.service_documents[command[4]]))
        if command[:4] == ['gcloud', 'run', 'revisions', 'describe']:
            return verifier.CommandResult(returncode=0, stdout=json.dumps(self.revision_documents[command[4]]))
        raise AssertionError(f'unexpected command: {command}')


def _service_document(
    *, serving_revision: str, latest_created_revision: str, traffic: list[dict] | None = None
) -> dict:
    return {
        # This deliberately conflicting service template must never influence
        # the serving revision used by the verifier.
        'spec': {
            'template': {'spec': {'containers': [{'env': [{'name': verifier.FENCE_MODE_ENV, 'value': 'legacy'}]}]}}
        },
        'status': {
            'latestCreatedRevisionName': latest_created_revision,
            'traffic': traffic if traffic is not None else [{'revisionName': serving_revision, 'percent': 100}],
        },
    }


def _revision_document(mode: str | None, *, duplicate: bool = False) -> dict:
    environment = [] if mode is None else [{'name': verifier.FENCE_MODE_ENV, 'value': mode}]
    if duplicate and mode is not None:
        environment.append({'name': verifier.FENCE_MODE_ENV, 'value': mode})
    return {'spec': {'containers': [{'name': 'backend', 'env': environment}]}}


def _runner(*, modes: dict[str, str | None]) -> FakeCloudRunner:
    service_documents: dict[str, dict] = {}
    revision_documents: dict[str, dict] = {}
    for service in verifier.SERVICES:
        serving_revision = f'{service}-serving'
        service_documents[service] = _service_document(
            serving_revision=serving_revision,
            latest_created_revision=f'{service}-newest-unserved',
        )
        revision_documents[serving_revision] = _revision_document(modes[service])
    return FakeCloudRunner(service_documents=service_documents, revision_documents=revision_documents)


def _config(desired_mode: str) -> verifier.TransitionVerificationConfig:
    return verifier.TransitionVerificationConfig(
        project='omi-prod',
        region='us-central1',
        desired_mode=desired_mode,
    )


def test_uses_positive_status_traffic_not_latest_created_or_service_template() -> None:
    runner = _runner(modes={service: 'active' for service in verifier.SERVICES})

    result = verifier.verify_transition(_config('active'), runner=runner)

    assert result.bootstrap_legacy is False
    assert [item.revision for item in result.serving_revisions] == [
        f'{service}-serving' for service in verifier.SERVICES
    ]
    described_revisions = [
        command[4] for command in runner.commands if command[:4] == ['gcloud', 'run', 'revisions', 'describe']
    ]
    assert described_revisions == [f'{service}-serving' for service in verifier.SERVICES]
    assert not any('newest-unserved' in ' '.join(command) for command in runner.commands)


def test_rejects_split_positive_traffic_before_describing_a_revision() -> None:
    runner = _runner(modes={service: 'active' for service in verifier.SERVICES})
    runner.service_documents['backend']['status']['traffic'] = [
        {'revisionName': 'backend-a', 'percent': 50},
        {'revisionName': 'backend-b', 'percent': 50},
    ]

    with pytest.raises(verifier.FenceTransitionVerificationError, match='splits positive traffic'):
        verifier.verify_transition(_config('active'), runner=runner)

    assert not any(command[:4] == ['gcloud', 'run', 'revisions', 'describe'] for command in runner.commands)


def test_accepts_all_missing_serving_modes_only_as_legacy_bootstrap() -> None:
    runner = _runner(modes={service: None for service in verifier.SERVICES})

    result = verifier.verify_transition(_config('legacy'), runner=runner)

    assert result.bootstrap_legacy is True
    assert all(item.mode is None for item in result.serving_revisions)


def test_rejects_completed_mode_transition_until_serving_revisions_match_requested_mode() -> None:
    runner = _runner(modes={service: 'standby' for service in verifier.SERVICES})

    with pytest.raises(verifier.FenceTransitionVerificationError, match="remain in 'standby', not requested 'active'"):
        verifier.verify_transition(_config('active'), runner=runner)


def test_rejects_a_partial_missing_mode_and_duplicate_declaration() -> None:
    modes = {service: 'active' for service in verifier.SERVICES}
    modes['backend-sync'] = None
    runner = _runner(modes=modes)

    with pytest.raises(verifier.FenceTransitionVerificationError, match='is missing from serving revision'):
        verifier.verify_transition(_config('active'), runner=runner)

    duplicate_runner = _runner(modes={service: 'active' for service in verifier.SERVICES})
    duplicate_runner.revision_documents['backend-serving'] = _revision_document('active', duplicate=True)
    with pytest.raises(
        verifier.FenceTransitionVerificationError, match='declares SYNC_LEDGER_FENCE_MODE more than once'
    ):
        verifier.verify_transition(_config('active'), runner=duplicate_runner)
