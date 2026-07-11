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
PROBE_TOKEN = 'A' * 32


def _candidates() -> list[resume.Candidate]:
    return [resume.Candidate(service, f'{service}-b939eab-1') for service in resume.PROMOTION_ORDER]


def _probe_log_entry(
    revision: str,
    *,
    probe_token: str = PROBE_TOKEN,
    status: int = 200,
    request_url: str | None = None,
) -> dict[str, Any]:
    return {
        'logName': 'projects/based-hardware/logs/run.googleapis.com%2Frequests',
        'resource': {
            'type': 'cloud_run_revision',
            'labels': {'service_name': 'backend', 'revision_name': revision},
        },
        'httpRequest': {
            'status': status,
            'requestUrl': request_url
            or f'https://api.omi.me/v1/health?{resume.BACKEND_PROBE_QUERY_PARAM}={probe_token}',
        },
    }


def _revision(
    service: str,
    *,
    digest: str = DIGEST,
    source_sha: str = SOURCE_SHA,
    active_status: str = 'True',
) -> dict[str, Any]:
    return {
        'metadata': {
            'name': f'{service}-b939eab-1',
            'labels': {'commit-sha': source_sha},
        },
        'spec': {'containers': [{'image': f'gcr.io/example/backend@{digest}'}]},
        'status': {
            'conditions': [
                {'type': 'Ready', 'status': 'True'},
                {'type': 'Active', 'status': active_status},
            ]
        },
    }


def _service(
    service: str,
    serving: str,
    *,
    latest_created: str | None = None,
    tag: str | None = None,
    tagged_revision: str | None = None,
    include_tag_url: bool = True,
    base_url: str | None = None,
    default_url_disabled: bool | None = None,
) -> dict[str, Any]:
    disabled = service == 'backend' if default_url_disabled is None else default_url_disabled
    canonical_url = '' if disabled else (base_url or f'https://{service}-abcdef-uc.a.run.app')
    status_traffic: list[dict[str, Any]] = [{'revisionName': serving, 'percent': 100}]
    spec_traffic: list[dict[str, Any]] = [{'revisionName': serving, 'percent': 100}]
    if tag:
        tagged = {
            'revisionName': tagged_revision or f'{service}-b939eab-1',
            'tag': tag,
        }
        if include_tag_url and not disabled:
            tagged['url'] = canonical_url.replace('https://', f'https://{tag}---', 1)
        status_traffic.append(tagged)
        spec_traffic.append({key: value for key, value in tagged.items() if key != 'url'})
    return {
        'metadata': {
            'annotations': {resume.DEFAULT_URL_DISABLED_ANNOTATION: 'true'} if disabled else {},
        },
        'spec': {'traffic': spec_traffic},
        'status': {
            'url': canonical_url,
            'latestCreatedRevisionName': latest_created or f'{service}-b939eab-1',
            'traffic': status_traffic,
        },
    }


def _install_candidate_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    traffic: dict[str, str] | None = None,
    revisions: dict[str, dict[str, Any]] | None = None,
    include_tag_urls: bool = True,
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
            include_tag_url=include_tag_urls,
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
    monkeypatch.setattr(resume, '_wait_for_backend_probe_attribution', lambda **kwargs: None)
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


def test_prepare_preflight_requires_aligned_serving_revisions(monkeypatch: pytest.MonkeyPatch) -> None:
    services = {service: _service(service, f'{service}-old') for service in resume.PROMOTION_ORDER}
    monkeypatch.setattr(
        resume,
        '_describe_service',
        lambda service, **_kwargs: services[service],
    )

    assert resume.verify_prepare_preflight(project='project', region='region') == {
        service: f'{service}-old' for service in resume.PROMOTION_ORDER
    }

    services['backend']['spec']['traffic'][0]['revisionName'] = 'backend-other'
    with pytest.raises(RuntimeError, match='backend spec/status traffic mismatch'):
        resume.verify_prepare_preflight(project='project', region='region')


def test_verify_prepared_candidates_derives_digest_without_mutating_traffic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    traffic, _, commands = _install_candidate_fakes(monkeypatch)

    assert (
        resume.verify_prepared_candidates(
            _candidates(),
            project='project',
            region='region',
            source_sha=SOURCE_SHA,
        )
        == DIGEST
    )
    assert traffic == {service: f'{service}-old' for service in resume.PROMOTION_ORDER}
    assert commands == []


def test_verify_prepared_candidates_rejects_mixed_child_digests(monkeypatch: pytest.MonkeyPatch) -> None:
    revisions = {candidate.service: _revision(candidate.service) for candidate in _candidates()}
    revisions['backend-sync'] = _revision('backend-sync', digest=f'sha256:{"e" * 64}')
    _install_candidate_fakes(monkeypatch, revisions=revisions)

    with pytest.raises(RuntimeError, match='backend-sync-b939eab-1 image digest'):
        resume.verify_prepared_candidates(
            _candidates(),
            project='project',
            region='region',
            source_sha=SOURCE_SHA,
        )


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
    health_urls: list[str] = []

    def healthy(url: str, *, token: str | None = None) -> int:
        health_urls.append(url)
        return 200

    monkeypatch.setattr(resume, '_http_status', healthy)
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
    assert control_plane_urls == [('https://resume-test---backend-integration-abcdef-uc.a.run.app', 'opaque-token')]
    assert not any(url.startswith('https://resume-test---backend-abcdef-uc.a.run.app') for url in health_urls)
    assert len([command for command in commands if any('--update-tags=' in part for part in command)]) == 4
    assert len([command for command in commands if any('--remove-tags=' in part for part in command)]) == 4
    assert all(command[1:3] == ['run', 'services'] for command in commands)


def test_candidate_tag_poll_accepts_exact_url_disabled_backend_without_direct_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = resume.Candidate('backend', 'backend-b939eab-1')
    calls = [0]
    sleeps: list[float] = []

    def describe_service(service: str, *, project: str, region: str) -> dict[str, Any]:
        calls[0] += 1
        return _service(
            service,
            'backend-old',
            tag='resume-test' if calls[0] >= 2 else None,
            include_tag_url=False,
        )

    monkeypatch.setattr(resume, '_describe_service', describe_service)
    monkeypatch.setattr(resume, '_describe_revision', lambda *args, **kwargs: _revision('backend'))
    monkeypatch.setattr(resume.time, 'sleep', sleeps.append)

    assert resume._wait_for_candidate_tag(
        candidate,
        project='project',
        region='region',
        candidate_tag='resume-test',
        previous_revision='backend-old',
        attempts=3,
        poll_interval_seconds=0.25,
    ) == (None, None)
    assert calls[0] == 2
    assert sleeps == [0.25]


@pytest.mark.parametrize(
    'base_url',
    (
        'http://backend-abcdef-uc.a.run.app',
        'https://backend.example',
        'https://backend-abcdef-uc.a.run.app/path',
        'https://user@backend-abcdef-uc.a.run.app',
    ),
)
def test_candidate_tag_url_fails_closed_for_malformed_canonical_url(base_url: str) -> None:
    with pytest.raises(RuntimeError, match=r'origin-only https://\*\.run\.app URL'):
        resume._validate_reported_tag_url(
            base_url,
            'https://resume-test---backend-sync-abcdef-uc.a.run.app',
            'resume-test',
        )


def test_candidate_tag_poll_fails_closed_for_wrong_revision_target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        resume,
        '_describe_service',
        lambda service, **kwargs: _service(
            service,
            'backend-old',
            tag='resume-test',
            tagged_revision='backend-wrong-revision',
        ),
    )

    with pytest.raises(RuntimeError, match='tag resume-test targets backend-wrong-revision'):
        resume._wait_for_candidate_tag(
            resume.Candidate('backend', 'backend-b939eab-1'),
            project='project',
            region='region',
            candidate_tag='resume-test',
            previous_revision='backend-old',
            attempts=2,
            poll_interval_seconds=0,
        )


def test_candidate_tag_url_rejects_reported_host_that_does_not_match_tag() -> None:
    with pytest.raises(RuntimeError, match='does not match tag'):
        resume._validate_reported_tag_url(
            'https://backend-abcdef-uc.a.run.app',
            'https://wrong-tag---backend-abcdef-uc.a.run.app',
            'resume-test',
        )


def test_candidate_tag_poll_rejects_default_url_disabled_non_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        resume,
        '_describe_service',
        lambda service, **kwargs: _service(
            service,
            'backend-sync-old',
            tag='resume-test',
            default_url_disabled=True,
        ),
    )
    monkeypatch.setattr(resume, '_describe_revision', lambda *args, **kwargs: _revision('backend-sync'))

    with pytest.raises(RuntimeError, match='only backend may set'):
        resume._wait_for_candidate_tag(
            resume.Candidate('backend-sync', 'backend-sync-b939eab-1'),
            project='project',
            region='region',
            candidate_tag='resume-test',
            previous_revision='backend-sync-old',
            attempts=1,
            poll_interval_seconds=0,
        )


def test_candidate_tag_poll_rejects_missing_url_for_enabled_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        resume,
        '_describe_service',
        lambda service, **kwargs: _service(
            service,
            'backend-sync-old',
            tag='resume-test',
            include_tag_url=False,
        ),
    )
    monkeypatch.setattr(resume, '_describe_revision', lambda *args, **kwargs: _revision('backend-sync'))

    with pytest.raises(RuntimeError, match=r'origin-only https://\*\.run\.app URL'):
        resume._wait_for_candidate_tag(
            resume.Candidate('backend-sync', 'backend-sync-b939eab-1'),
            project='project',
            region='region',
            candidate_tag='resume-test',
            previous_revision='backend-sync-old',
            attempts=1,
            poll_interval_seconds=0,
        )


def test_candidate_tag_poll_waits_for_spec_status_convergence(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = [0]
    sleeps: list[float] = []

    def describe_service(service: str, **kwargs: Any) -> dict[str, Any]:
        calls[0] += 1
        document = _service(service, 'backend-sync-old', tag='resume-test')
        if calls[0] == 1:
            document['status']['traffic'] = document['status']['traffic'][:1]
        return document

    monkeypatch.setattr(resume, '_describe_service', describe_service)
    monkeypatch.setattr(resume, '_describe_revision', lambda *args, **kwargs: _revision('backend-sync'))
    monkeypatch.setattr(resume.time, 'sleep', sleeps.append)

    assert resume._wait_for_candidate_tag(
        resume.Candidate('backend-sync', 'backend-sync-b939eab-1'),
        project='project',
        region='region',
        candidate_tag='resume-test',
        previous_revision='backend-sync-old',
        attempts=2,
        poll_interval_seconds=0.25,
    ) == (
        'https://backend-sync-abcdef-uc.a.run.app',
        'https://resume-test---backend-sync-abcdef-uc.a.run.app',
    )
    assert sleeps == [0.25]


def test_candidate_tag_poll_waits_for_active_revision_after_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    revision_calls = [0]
    sleeps: list[float] = []
    monkeypatch.setattr(
        resume,
        '_describe_service',
        lambda service, **kwargs: _service(service, 'backend-old', tag='resume-test'),
    )

    def describe_revision(*args: Any, **kwargs: Any) -> dict[str, Any]:
        revision_calls[0] += 1
        return _revision('backend', active_status='False' if revision_calls[0] == 1 else 'True')

    monkeypatch.setattr(resume, '_describe_revision', describe_revision)
    monkeypatch.setattr(resume.time, 'sleep', sleeps.append)

    assert resume._wait_for_candidate_tag(
        resume.Candidate('backend', 'backend-b939eab-1'),
        project='project',
        region='region',
        candidate_tag='resume-test',
        previous_revision='backend-old',
        attempts=2,
        poll_interval_seconds=0.25,
    ) == (None, None)
    assert revision_calls[0] == 2
    assert sleeps == [0.25]


def test_candidate_tag_cleanup_polls_until_absent_from_spec_and_status(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = [0]
    sleeps: list[float] = []

    def describe_service(service: str, **kwargs: Any) -> dict[str, Any]:
        calls[0] += 1
        document = _service(service, 'backend-sync-old', tag='resume-test' if calls[0] < 3 else None)
        if calls[0] == 2:
            document['status']['traffic'] = document['status']['traffic'][:1]
        return document

    monkeypatch.setattr(resume, '_describe_service', describe_service)
    monkeypatch.setattr(resume.time, 'sleep', sleeps.append)

    resume._wait_for_tag_cleanup(
        resume.Candidate('backend-sync', 'backend-sync-b939eab-1'),
        project='project',
        region='region',
        candidate_tag='resume-test',
        previous_revision='backend-sync-old',
        attempts=3,
        poll_interval_seconds=0.25,
    )

    assert calls[0] == 3
    assert sleeps == [0.25, 0.25]


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


def test_backend_probe_attribution_accepts_exact_200_revision_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []

    def read_entries(command: list[str]) -> list[dict[str, Any]]:
        commands.append(command)
        return [_probe_log_entry('backend-b939eab-1')]

    monkeypatch.setattr(resume, '_read_logging_entries', read_entries)
    monkeypatch.setattr(resume, '_http_status', lambda url, attempts=1: 200)

    resume._wait_for_backend_probe_attribution(
        project='based-hardware',
        revision='backend-b939eab-1',
        probe_token=PROBE_TOKEN,
        control_plane_url='https://api.omi.me',
        attempts=1,
        poll_interval_seconds=0,
    )

    log_filter = commands[0][3]
    assert 'logName="projects/based-hardware/logs/run.googleapis.com%2Frequests"' in log_filter
    assert 'resource.labels.revision_name="backend-b939eab-1"' in log_filter
    assert f'httpRequest.requestUrl:"{resume.BACKEND_PROBE_QUERY_PARAM}={PROBE_TOKEN}"' in log_filter


def test_backend_probe_attribution_polls_for_delayed_log_ingestion(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [[], [], [_probe_log_entry('backend-b939eab-1')]]
    sleeps: list[float] = []
    probes: list[str] = []
    monkeypatch.setattr(resume, '_read_logging_entries', lambda command: responses.pop(0))

    def probe(url: str, *, attempts: int = 1) -> int:
        probes.append(url)
        return 200

    monkeypatch.setattr(resume, '_http_status', probe)
    monkeypatch.setattr(resume.time, 'sleep', sleeps.append)

    resume._wait_for_backend_probe_attribution(
        project='based-hardware',
        revision='backend-b939eab-1',
        probe_token=PROBE_TOKEN,
        control_plane_url='https://api.omi.me',
        attempts=3,
        poll_interval_seconds=0.25,
    )

    assert sleeps == [0.25, 0.25]
    assert len(probes) == 3
    assert len(set(probes)) == 1


def test_backend_probe_reissues_same_token_after_old_revision_log(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        [_probe_log_entry('backend-old')],
        [_probe_log_entry('backend-b939eab-1')],
    ]
    probes: list[str] = []
    monkeypatch.setattr(resume, '_read_logging_entries', lambda command: responses.pop(0))
    monkeypatch.setattr(resume, '_http_status', lambda url, attempts=1: (probes.append(url) or 200))
    monkeypatch.setattr(resume.time, 'sleep', lambda seconds: None)

    resume._wait_for_backend_probe_attribution(
        project='based-hardware',
        revision='backend-b939eab-1',
        probe_token=PROBE_TOKEN,
        control_plane_url='https://api.omi.me',
        attempts=2,
        poll_interval_seconds=0,
    )

    assert len(probes) == 2
    assert probes[0] == probes[1]


@pytest.mark.parametrize('evidence_kind', ('wrong-revision', 'missing-revision', 'wrong-log', 'none'))
def test_backend_probe_attribution_rejects_wrong_or_missing_revision_evidence(
    monkeypatch: pytest.MonkeyPatch,
    evidence_kind: str,
) -> None:
    if evidence_kind == 'wrong-revision':
        entries = [_probe_log_entry('backend-old')]
    elif evidence_kind == 'missing-revision':
        entry = _probe_log_entry('backend-b939eab-1')
        del entry['resource']['labels']['revision_name']
        entries = [entry]
    elif evidence_kind == 'wrong-log':
        entry = _probe_log_entry('backend-b939eab-1')
        entry['logName'] = 'projects/based-hardware/logs/not-requests'
        entries = [entry]
    else:
        entries = []
    monkeypatch.setattr(resume, '_read_logging_entries', lambda command: entries)
    monkeypatch.setattr(resume, '_http_status', lambda url, attempts=1: 200)

    with pytest.raises(RuntimeError, match='no 200 Cloud Run request-log evidence'):
        resume._wait_for_backend_probe_attribution(
            project='based-hardware',
            revision='backend-b939eab-1',
            probe_token=PROBE_TOKEN,
            control_plane_url='https://api.omi.me',
            attempts=1,
            poll_interval_seconds=0,
        )


def test_backend_probe_inputs_fail_closed_before_logging_filter_construction() -> None:
    with pytest.raises(ValueError, match='invalid GCP project ID'):
        resume._wait_for_backend_probe_attribution(
            project='bad" OR true',
            revision='backend-b939eab-1',
            probe_token=PROBE_TOKEN,
            control_plane_url='https://api.omi.me',
            attempts=1,
        )
    with pytest.raises(ValueError, match='invalid Cloud Run revision name'):
        resume._wait_for_backend_probe_attribution(
            project='based-hardware',
            revision='backend-bad" OR true',
            probe_token=PROBE_TOKEN,
            control_plane_url='https://api.omi.me',
            attempts=1,
        )
    with pytest.raises(ValueError, match='32 URL-safe characters'):
        resume._backend_probe_url('https://api.omi.me', 'unsafe token"')


def test_backend_probe_uses_exact_control_plane_and_attribution_before_openapi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_candidate_fakes(monkeypatch)
    events: list[str] = []
    urls: list[str] = []
    monkeypatch.setattr(resume.secrets, 'token_urlsafe', lambda size: PROBE_TOKEN)

    def status(url: str, *, token: str | None = None) -> int:
        urls.append(url)
        return 200

    monkeypatch.setattr(resume, '_http_status', status)
    monkeypatch.setattr(
        resume,
        '_wait_for_backend_probe_attribution',
        lambda **kwargs: events.append(
            f'attribution:{kwargs["control_plane_url"]}:{kwargs["revision"]}:{kwargs["probe_token"]}'
        ),
    )
    monkeypatch.setattr(resume, 'verify_control_plane', lambda *args, **kwargs: events.append('openapi'))

    resume.promote_candidates(
        _candidates(),
        project='project',
        region='region',
        source_sha=SOURCE_SHA,
        expected_digest=DIGEST,
        control_plane_url='https://api.omi.me',
    )

    assert events == [f'attribution:https://api.omi.me:backend-b939eab-1:{PROBE_TOKEN}', 'openapi']


def test_backend_attribution_failure_rolls_back_all_services_before_openapi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    traffic, _, _ = _install_candidate_fakes(monkeypatch)
    openapi_calls: list[str] = []
    monkeypatch.setattr(resume, '_http_status', lambda url, token=None: 200)
    monkeypatch.setattr(
        resume,
        '_wait_for_backend_probe_attribution',
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError('no exact revision evidence')),
    )
    monkeypatch.setattr(resume, 'verify_control_plane', lambda url, token=None: openapi_calls.append(url))

    with pytest.raises(RuntimeError, match='traffic was rolled back: no exact revision evidence'):
        resume.promote_candidates(
            _candidates(),
            project='project',
            region='region',
            source_sha=SOURCE_SHA,
            expected_digest=DIGEST,
            control_plane_url='https://api.omi.me',
        )

    assert openapi_calls == []
    assert traffic == {service: f'{service}-old' for service in resume.PROMOTION_ORDER}


def test_wait_for_serving_revision_polls_transient_describe_and_spec_status_convergence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses: list[dict[str, Any] | RuntimeError] = [
        RuntimeError('transient describe failure'),
        {
            'spec': {'traffic': [{'revisionName': 'backend-old', 'percent': 100}]},
            'status': {'traffic': [{'revisionName': 'backend-b939eab-1', 'percent': 100}]},
        },
        _service('backend', 'backend-b939eab-1'),
    ]
    sleeps: list[float] = []

    def describe_service(*args: Any, **kwargs: Any) -> dict[str, Any]:
        response = responses.pop(0)
        if isinstance(response, RuntimeError):
            raise response
        return response

    monkeypatch.setattr(resume, '_describe_service', describe_service)
    monkeypatch.setattr(resume.time, 'sleep', sleeps.append)

    resume._wait_for_serving_revision(
        'backend',
        'backend-b939eab-1',
        project='project',
        region='region',
        attempts=3,
        poll_interval_seconds=0.25,
    )

    assert sleeps == [0.25, 0.25]


def test_rollback_ambiguous_command_is_success_when_snapshot_converges(monkeypatch: pytest.MonkeyPatch) -> None:
    traffic = {candidate.service: candidate.revision for candidate in _candidates()}
    traffic, _, _ = _install_candidate_fakes(monkeypatch, traffic=traffic)
    original_run = resume._run
    injected = False

    def mutate_then_raise(command: list[str]) -> None:
        nonlocal injected
        target = next((part for part in command if part.startswith('--to-revisions=')), '')
        if not injected and command[4] == 'backend-sync' and target.startswith('--to-revisions=backend-sync-old='):
            injected = True
            original_run(command)
            raise RuntimeError('ambiguous rollback result')
        original_run(command)

    monkeypatch.setattr(resume, '_run', mutate_then_raise)

    errors = resume._rollback_candidates(
        _candidates(),
        previous={service: f'{service}-old' for service in resume.PROMOTION_ORDER},
        project='project',
        region='region',
    )

    assert errors == []
    assert traffic == {service: f'{service}-old' for service in resume.PROMOTION_ORDER}


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
        return 503 if 'backend-sync-abcdef-uc.a.run.app' in url else 200

    monkeypatch.setattr(resume, '_http_status', fake_status)

    with pytest.raises(RuntimeError, match='traffic was rolled back'):
        resume.promote_candidates(
            _candidates(),
            project='project',
            region='region',
            source_sha=SOURCE_SHA,
            expected_digest=DIGEST,
            control_plane_url='https://api.omi.me',
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
            control_plane_url='https://api.omi.me',
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
            control_plane_url='https://api.omi.me',
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
        lambda url, token=None: 503 if 'backend-sync-abcdef-uc.a.run.app' in url else 200,
    )
    monkeypatch.setattr(resume.time, 'sleep', lambda seconds: None)

    with pytest.raises(
        RuntimeError, match=r'rollback also failed: .*manual recovery: gcloud run services update-traffic'
    ):
        resume.promote_candidates(
            _candidates(),
            project='project',
            region='region',
            source_sha=SOURCE_SHA,
            expected_digest=DIGEST,
            control_plane_url='https://api.omi.me',
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


def test_http_helpers_retry_builtin_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        status = 200

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self, *_: object) -> bytes:
            return b'{"ok": true}'

    outcomes: list[object] = [TimeoutError('read timed out'), FakeResponse()]
    sleeps: list[float] = []

    def urlopen(*_: object, **__: object) -> FakeResponse:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        assert isinstance(outcome, FakeResponse)
        return outcome

    monkeypatch.setattr(resume.request, 'urlopen', urlopen)
    monkeypatch.setattr(resume.time, 'sleep', sleeps.append)

    assert resume._http_status('https://candidate.example/v1/health', attempts=2) == 200
    assert sleeps == [5]

    outcomes[:] = [TimeoutError('read timed out'), FakeResponse()]
    sleeps.clear()

    assert resume._http_json('https://candidate.example/openapi.json', attempts=2) == {'ok': True}
    assert sleeps == [5]


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


def test_gke_gate_requires_continuous_healthy_dwell(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_gke_gate_healthy_hpa_scale_down_does_not_reset_dwell(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [0.0]
    samples = [0]
    desired_by_sample = (5, 4, 3)

    def load_documents(**_: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        index = samples[0]
        samples[0] += 1
        return _gke_documents(desired_by_sample[min(index, len(desired_by_sample) - 1)])

    monkeypatch.setattr(resume, '_load_gke_documents', load_documents)
    monkeypatch.setattr(resume.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(resume.time, 'sleep', lambda seconds: clock.__setitem__(0, clock[0] + seconds))

    resume.gate_gke_rollout(
        namespace='namespace',
        deployment='deployment',
        hpa='hpa',
        selector='selector',
        expected_image=IMAGE,
        expected_runtime_project='based-hardware',
        dwell_seconds=120,
        poll_interval_seconds=60,
        timeout_seconds=180,
    )

    assert samples[0] == 3


def test_gke_gate_restart_count_increase_resets_dwell(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [0.0]
    samples = [0]

    def load_documents(**_: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        index = samples[0]
        samples[0] += 1
        documents = _gke_documents()
        if index >= 1:
            documents[3]['items'][0]['status']['containerStatuses'][0]['restartCount'] = 1
        return documents

    monkeypatch.setattr(resume, '_load_gke_documents', load_documents)
    monkeypatch.setattr(resume.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(resume.time, 'sleep', lambda seconds: clock.__setitem__(0, clock[0] + seconds))

    resume.gate_gke_rollout(
        namespace='namespace',
        deployment='deployment',
        hpa='hpa',
        selector='selector',
        expected_image=IMAGE,
        expected_runtime_project='based-hardware',
        dwell_seconds=100,
        poll_interval_seconds=50,
        timeout_seconds=200,
    )

    assert samples[0] == 4


def test_gke_gate_unhealthy_sample_resets_dwell(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = [0.0]
    samples = [0]

    def load_documents(**_: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        index = samples[0]
        samples[0] += 1
        documents = _gke_documents()
        if index == 1:
            documents[3]['items'][0]['status']['phase'] = 'Pending'
        return documents

    monkeypatch.setattr(resume, '_load_gke_documents', load_documents)
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
        timeout_seconds=50,
    )

    assert samples[0] == 5


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
    deploy_block = workflow.split('\n  deploy:', 1)[1]
    for topology_block in (deploy_block, helm_workflow):
        assert 'GCP_PROJECT_ID: ${{ vars.GCP_PROJECT_ID }}' in topology_block
        assert 'ENV: ${{ vars.ENV }}' in topology_block
        assert 'GKE_CLUSTER: ${{ vars.GKE_CLUSTER }}' in topology_block
        assert 'RUNTIME_GCP_PROJECT_ID: ${{ vars.RUNTIME_GCP_PROJECT_ID }}' in topology_block
        assert 'EXPECTED_GCP_PROJECT_ID="based-hardware-dev"' in topology_block
        assert 'EXPECTED_GCP_PROJECT_ID="based-hardware"' in topology_block
        assert 'EXPECTED_ENV="dev"' in topology_block
        assert 'EXPECTED_ENV="prod"' in topology_block
        assert 'EXPECTED_GKE_CLUSTER="dev-omi-gke"' in topology_block
        assert 'EXPECTED_GKE_CLUSTER="prod-omi-gke"' in topology_block
        assert '[[ "$RUNTIME_GCP_PROJECT_ID" != "based-hardware" ]]' in topology_block
    assert 'ref: ${{ github.sha }}' in helm_workflow
    assert helm_workflow.index('Validate deployment topology') < helm_workflow.index('Install Helm')
    assert deploy_block.index('deployment topology does not match') < deploy_block.index('Build and Push Docker image')
    current_revision_block = deploy_block.split('      - name: Verify validated revisions are still current', 1)[
        1
    ].split('      - name: Verify zero-traffic candidates and emit immutable resume handoff', 1)[0]
    assert current_revision_block.count('--project=${{ vars.GCP_PROJECT_ID }}') == 4


def test_workflow_prepare_lane_keeps_cloud_run_traffic_unchanged_and_emits_resume_handoff() -> None:
    workflow = (REPO_ROOT / '.github/workflows/gcp_backend.yml').read_text(encoding='utf-8')
    auto_dev = (REPO_ROOT / '.github/workflows/gcp_backend_auto_dev.yml').read_text(encoding='utf-8')
    backfill_action = (REPO_ROOT / '.github/actions/sync-backfill-lifecycle/action.yml').read_text(encoding='utf-8')
    deploy_block = workflow.split('\n  deploy:', 1)[1]
    preflight_block = deploy_block.split('      - name: Preflight Cloud Run deploy', 1)[1].split(
        '      - name: Snapshot exact serving revisions', 1
    )[0]
    shift_header = deploy_block.split('      - name: Shift Cloud Run traffic to validated revisions', 1)[1].split(
        '        run:', 1
    )[0]

    assert '- prepare-cloud-run' in workflow
    assert "github.event.inputs.mode == 'deploy' || github.event.inputs.mode == 'prepare-cloud-run'" in workflow
    assert 'confirm must be prepare-cloud-run-prod' in deploy_block
    assert 'prepare-cloud-run requires deploy_targets=all' in deploy_block
    assert 'resume_cloud_run_deploy.py prepare-preflight' in deploy_block
    assert 'resume_cloud_run_deploy.py verify-prepared' in deploy_block
    assert 'diff -u /tmp/cloud-run-serving-before-prepare.txt' in deploy_block
    assert 'expected_revision_digest=$EXPECTED_DIGEST' in deploy_block
    assert "if [[ \"$INPUT_MODE\" != \"prepare-cloud-run\" ]]" in preflight_block
    assert 'PREFLIGHT_ARGS+=(--repair-traffic)' in preflight_block
    assert "github.event.inputs.mode == 'deploy'" in shift_header
    assert 'Roll back GKE if candidate preparation fails after mutation' in deploy_block
    assert '--atomic' in deploy_block
    assert (
        "github.event.inputs.mode != 'prepare-cloud-run'"
        in deploy_block.split('      - name: Provision sync-backfill platform', 1)[1].split('        uses:', 1)[0]
    )
    assert 'labels: release-source-sha=${{ github.sha }}' in deploy_block
    assert 'labels: ${{ inputs.revision_labels }}' in backfill_action
    assert 'revision_labels: release-source-sha=${{ github.sha }}' in workflow
    assert 'revision_labels: release-source-sha=${{ github.sha }}' in auto_dev


def test_resume_helper_never_resolves_mutable_container_tag() -> None:
    source = (BACKEND_ROOT / 'scripts/resume_cloud_run_deploy.py').read_text(encoding='utf-8')

    assert 'container images describe' not in source
    assert 'expected-digest' in source
