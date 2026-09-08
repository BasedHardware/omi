from __future__ import annotations

import json
from typing import Sequence
from urllib.parse import unquote

from scripts import wait_cloud_run_candidate_readiness as readiness


class FakeCloudRunner:
    def __init__(self, result: readiness.CommandResult) -> None:
        self.result = result
        self.commands: list[list[str]] = []

    def run(self, command: Sequence[str]) -> readiness.CommandResult:
        self.commands.append(list(command))
        return self.result


class SequenceCloudRunner:
    def __init__(self, results: list[readiness.CommandResult]) -> None:
        self.results = results
        self.commands: list[list[str]] = []

    def run(self, command: Sequence[str]) -> readiness.CommandResult:
        self.commands.append(list(command))
        return self.results.pop(0)


def _config() -> readiness.CandidateConfig:
    return readiness.CandidateConfig(
        project='omi-prod',
        region='us-central1',
        service='frontend',
        revision='frontend-candidate-00001',
    )


def test_ready_false_reports_reason_message_and_candidate_identity() -> None:
    runner = FakeCloudRunner(
        readiness.CommandResult(
            returncode=0,
            stdout=json.dumps(
                {
                    'status': {
                        'conditions': [
                            {
                                'type': 'Ready',
                                'status': 'False',
                                'reason': 'HealthCheckContainerError',
                                'message': 'The user-provided container failed to start and listen on PORT=8080.',
                            }
                        ]
                    }
                }
            ),
        )
    )

    observation = readiness.observe_candidate_readiness(_config(), runner=runner)
    report = readiness.format_failure(_config(), observation)

    assert observation.is_ready is False
    assert 'candidate.project=omi-prod' in report
    assert 'candidate.region=us-central1' in report
    assert 'candidate.service=frontend' in report
    assert 'candidate.revision=frontend-candidate-00001' in report
    assert 'ready.status=False' in report
    assert 'ready.reason=HealthCheckContainerError' in report
    assert 'ready.message=The user-provided container failed to start and listen on PORT=8080.' in report
    assert runner.commands == [
        [
            'gcloud',
            'run',
            'revisions',
            'describe',
            'frontend-candidate-00001',
            '--project=omi-prod',
            '--region=us-central1',
            '--format=json',
        ]
    ]


def test_describe_failure_does_not_print_raw_gcloud_stderr() -> None:
    runner = FakeCloudRunner(
        readiness.CommandResult(returncode=1, stderr='permission denied while reading token=private-token-value')
    )

    report = readiness.format_failure(_config(), readiness.observe_candidate_readiness(_config(), runner=runner))

    assert 'ready.status=unavailable' in report
    assert 'diagnostic=Cloud Run revision describe failed (exit=1).' in report
    assert 'private-token-value' not in report


def test_ready_condition_message_redacts_suspected_secret_values() -> None:
    runner = FakeCloudRunner(
        readiness.CommandResult(
            returncode=0,
            stdout=json.dumps(
                {
                    'status': {
                        'conditions': [
                            {
                                'type': 'Ready',
                                'status': 'False',
                                'message': 'Container reported OPENAI_API_KEY=raw-secret-value while starting.',
                            }
                        ]
                    }
                }
            ),
        )
    )

    report = readiness.format_failure(_config(), readiness.observe_candidate_readiness(_config(), runner=runner))

    assert 'OPENAI_API_KEY=<redacted>' in report
    assert 'raw-secret-value' not in report


def test_invalid_ready_status_fails_closed() -> None:
    runner = FakeCloudRunner(
        readiness.CommandResult(returncode=0, stdout=json.dumps({'status': {'conditions': [{'type': 'Ready'}]}}))
    )

    observation = readiness.wait_for_candidate_ready(
        _config(),
        timeout_seconds=0,
        poll_interval_seconds=1,
        runner=runner,
    )

    assert observation.is_ready is False
    assert observation.status == 'invalid'
    assert observation.diagnostic == 'Cloud Run Ready condition has an invalid status.'


def test_invalid_json_fails_closed_without_exposing_response_body() -> None:
    runner = FakeCloudRunner(readiness.CommandResult(returncode=0, stdout='{this is not JSON'))

    observation = readiness.observe_candidate_readiness(_config(), runner=runner)
    report = readiness.format_failure(_config(), observation)

    assert observation.is_ready is False
    assert observation.status == 'invalid'
    assert observation.diagnostic == 'Cloud Run revision describe returned invalid JSON.'
    assert '{this is not JSON' not in report


def test_ready_false_returns_immediately_without_waiting_for_timeout() -> None:
    runner = FakeCloudRunner(
        readiness.CommandResult(
            returncode=0,
            stdout=json.dumps(
                {
                    'status': {
                        'conditions': [{'type': 'Ready', 'status': 'False', 'reason': 'HealthCheckContainerError'}]
                    }
                }
            ),
        )
    )
    slept: list[float] = []

    observation = readiness.wait_for_candidate_ready(
        _config(),
        timeout_seconds=150,
        poll_interval_seconds=5,
        runner=runner,
        sleeper=slept.append,
    )

    assert observation.status == 'False'
    assert slept == []
    assert len(runner.commands) == 1


def test_unknown_ready_state_keeps_polling_until_candidate_is_ready() -> None:
    runner = SequenceCloudRunner(
        [
            readiness.CommandResult(
                returncode=0,
                stdout=json.dumps({'status': {'conditions': [{'type': 'Ready', 'status': 'Unknown'}]}}),
            ),
            readiness.CommandResult(
                returncode=0,
                stdout=json.dumps({'status': {'conditions': [{'type': 'Ready', 'status': 'True'}]}}),
            ),
        ]
    )
    current_time = [0.0]
    slept: list[float] = []

    def sleeper(seconds: float) -> None:
        slept.append(seconds)
        current_time[0] += seconds

    observation = readiness.wait_for_candidate_ready(
        _config(),
        timeout_seconds=150,
        poll_interval_seconds=5,
        runner=runner,
        monotonic=lambda: current_time[0],
        sleeper=sleeper,
    )

    assert observation.is_ready is True
    assert slept == [5]
    assert len(runner.commands) == 2


def test_logging_url_filters_one_revision_and_escapes_filter_values() -> None:
    config = readiness.CandidateConfig(
        project='omi-prod',
        region='us-central1',
        service='frontend" OR severity>=ERROR',
        revision='frontend-candidate-00001',
    )

    url = readiness.build_cloud_logging_url(config)
    decoded = unquote(url)

    assert url.startswith('https://console.cloud.google.com/logs/query;query=')
    assert decoded.endswith('?project=omi-prod')
    assert 'resource.type="cloud_run_revision"' in decoded
    assert 'resource.labels.service_name="frontend\\" OR severity>=ERROR"' in decoded
    assert 'resource.labels.revision_name="frontend-candidate-00001"' in decoded
    assert 'resource.labels.location="us-central1"' in decoded
