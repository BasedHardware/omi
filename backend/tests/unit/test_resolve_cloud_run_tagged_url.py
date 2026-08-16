from __future__ import annotations

import json
from typing import Sequence

import pytest

from scripts import resolve_cloud_run_tagged_url as resolver


class FakeCloudRunner:
    def __init__(self, service_document: dict) -> None:
        self.service_document = service_document
        self.commands: list[list[str]] = []

    def run(self, command: Sequence[str], *, check: bool = True) -> resolver.CommandResult:
        command = list(command)
        self.commands.append(command)
        assert command[:4] == ['gcloud', 'run', 'services', 'describe']
        return resolver.CommandResult(returncode=0, stdout=json.dumps(self.service_document))


def _config() -> resolver.TaggedUrlConfig:
    return resolver.TaggedUrlConfig(
        project='omi-prod',
        region='us-central1',
        service='backend',
        revision='backend-candidate',
        tag='ledger-candidate',
    )


def _service_document(*, traffic: list[dict]) -> dict:
    return {
        'status': {
            # The tagged binding, not the newest revision, is the authority.
            'latestCreatedRevisionName': 'backend-newest-unrelated',
            'traffic': traffic,
        }
    }


def test_resolves_exact_https_url_for_requested_tag_and_revision() -> None:
    runner = FakeCloudRunner(
        _service_document(
            traffic=[
                {'revisionName': 'backend-serving', 'percent': 100},
                {
                    'revisionName': 'backend-candidate',
                    'percent': 0,
                    'tag': 'ledger-candidate',
                    'url': 'https://ledger-candidate---backend.example.test',
                },
            ]
        )
    )

    url = resolver.resolve_live_tagged_url(_config(), runner=runner)

    assert url == 'https://ledger-candidate---backend.example.test'
    assert runner.commands == [
        [
            'gcloud',
            'run',
            'services',
            'describe',
            'backend',
            '--project=omi-prod',
            '--region=us-central1',
            '--format=json',
        ]
    ]


def test_rejects_tag_bound_to_stale_revision_even_when_latest_created_differs() -> None:
    runner = FakeCloudRunner(
        _service_document(
            traffic=[
                {
                    'revisionName': 'backend-stale',
                    'percent': 0,
                    'tag': 'ledger-candidate',
                    'url': 'https://ledger-candidate---backend.example.test',
                }
            ]
        )
    )

    with pytest.raises(
        resolver.TaggedUrlResolutionError, match="targets revision 'backend-stale', not requested 'backend-candidate'"
    ):
        resolver.resolve_live_tagged_url(_config(), runner=runner)


def test_rejects_missing_tag() -> None:
    runner = FakeCloudRunner(
        _service_document(
            traffic=[
                {
                    'revisionName': 'backend-candidate',
                    'percent': 0,
                    'tag': 'different-tag',
                    'url': 'https://different-tag---backend.example.test',
                }
            ]
        )
    )

    with pytest.raises(resolver.TaggedUrlResolutionError, match='is absent'):
        resolver.resolve_live_tagged_url(_config(), runner=runner)


def test_rejects_duplicate_tag_targets() -> None:
    runner = FakeCloudRunner(
        _service_document(
            traffic=[
                {
                    'revisionName': 'backend-candidate',
                    'percent': 0,
                    'tag': 'ledger-candidate',
                    'url': 'https://ledger-candidate---backend.example.test',
                },
                {
                    'revisionName': 'backend-other',
                    'percent': 0,
                    'tag': 'ledger-candidate',
                    'url': 'https://ledger-candidate---backend-other.example.test',
                },
            ]
        )
    )

    with pytest.raises(resolver.TaggedUrlResolutionError, match='appears more than once'):
        resolver.resolve_live_tagged_url(_config(), runner=runner)
