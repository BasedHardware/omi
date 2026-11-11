import json
from pathlib import Path
from types import SimpleNamespace

from scripts import run_dev_candidate_acceptance as acceptance


def _fake_completed_process(returncode: int, stdout: str = '', stderr: str = '') -> SimpleNamespace:
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def _write_single_service_manifest(tmp_path: Path, command: list[str]) -> Path:
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(
        json.dumps(
            {
                'schema_version': 1,
                'services': {'backend': {'contract': 'what_matters_now', 'command': command}},
            }
        ),
        encoding='utf-8',
    )
    return manifest


def _run_acceptance_main(tmp_path: Path, monkeypatch, command: list[str]) -> tuple[int, dict, Path]:
    evidence_path = tmp_path / 'candidate.json'
    manifest = _write_single_service_manifest(tmp_path, command)
    code = acceptance.main(
        [
            '--manifest',
            str(manifest),
            '--candidate',
            'backend=https://candidate.example',
            '--audience',
            'backend=https://backend-service.example',
            '--evidence-path',
            str(evidence_path),
        ]
    )
    return code, json.loads(evidence_path.read_text(encoding='utf-8')), evidence_path


def test_mint_failure_classes_auth_no_credentials_without_leaking_stderr(monkeypatch):
    secret = 'SUPERSECRETYA29.federated-token-material'
    monkeypatch.setattr(
        acceptance.subprocess,
        'run',
        lambda *args, **kwargs: _fake_completed_process(
            1, stderr=f'ERROR: (gcloud.login) no authorized account\n{secret}'
        ),
    )

    error = None
    try:
        acceptance.mint_cloud_run_identity_token(audience='https://backend-service.example')
    except RuntimeError as caught:
        error = caught
    if error is None:
        raise AssertionError('expected mint failure to raise')

    diagnostics = error.args[1]
    assert diagnostics == {'stage': 'mint', 'rc': 1, 'class': 'auth_no_credentials'}
    assert secret not in str(error)
    assert secret not in json.dumps(diagnostics)
    assert 'gcloud' not in json.dumps(diagnostics)


def test_mint_failure_classes_federated_token_error_and_timeout(monkeypatch):
    cases = [
        ('invalid_grant: token endpoint returned an error', 'federated_token_error', 1),
        ('your refresh token has expired', 'federated_token_error', 1),
        ('gcloud operation timed out after 30s', 'timeout', 1),
    ]
    for stderr, expected_class, expected_rc in cases:
        monkeypatch.setattr(
            acceptance.subprocess,
            'run',
            lambda *args, **kwargs: _fake_completed_process(expected_rc, stderr=stderr),
        )
        try:
            acceptance.mint_cloud_run_identity_token(audience='https://backend-service.example')
        except RuntimeError as error:
            assert error.args[1] == {'stage': 'mint', 'rc': expected_rc, 'class': expected_class}
        else:
            raise AssertionError(f'expected mint failure for stderr {stderr!r}')
        monkeypatch.undo()

    monkeypatch.setattr(acceptance.subprocess, 'run', lambda *args, **kwargs: _fake_completed_process(1, stderr=''))
    try:
        acceptance.mint_cloud_run_identity_token(audience='https://backend-service.example')
    except RuntimeError as error:
        assert error.args[1] == {'stage': 'mint', 'rc': 1, 'class': 'unknown'}
    else:
        raise AssertionError('expected mint failure for empty token')


def test_oversized_token_counts_as_failure_and_reports_token_oversized(monkeypatch):
    oversized = 'x' * 8193
    monkeypatch.setattr(
        acceptance.subprocess, 'run', lambda *args, **kwargs: _fake_completed_process(0, stdout=oversized + '\n')
    )

    try:
        acceptance.mint_cloud_run_identity_token(audience='https://backend-service.example')
    except RuntimeError as error:
        assert error.args[1] == {'stage': 'mint', 'rc': 0, 'class': 'token_oversized'}
        assert oversized not in str(error)
    else:
        raise AssertionError('expected oversized token to fail the mint stage')


def test_probe_failure_captures_http_status_for_non_2xx(monkeypatch):
    check = acceptance.CandidateCheck(
        service='backend',
        contract='what_matters_now',
        command=('echo', '{base_url}'),
    )
    monkeypatch.setattr(acceptance, 'mint_cloud_run_identity_token', lambda *, audience, impersonate=None: 'token')
    monkeypatch.setattr(
        acceptance.subprocess,
        'run',
        lambda *args, **kwargs: _fake_completed_process(1, stderr='ERROR: What Matters Now smoke received HTTP 503\n'),
    )

    outcome = acceptance.run_check(
        check,
        base_url='https://candidate.example',
        audience='https://backend-service.example',
    )

    assert outcome.status == 'FAIL'
    assert outcome.diagnostics == {
        'stage': 'probe',
        'service': 'backend',
        'http_status': 503,
        'class': 'http_failure',
    }


def test_probe_failure_records_conn_error_for_connection_exception(monkeypatch):
    check = acceptance.CandidateCheck(
        service='backend-sync',
        contract='health',
        command=('echo', '{base_url}'),
    )

    def failing_mint(*, audience: str, impersonate: str | None = None) -> str:
        raise OSError('network unreachable')

    monkeypatch.setattr(acceptance, 'mint_cloud_run_identity_token', failing_mint)

    outcome = acceptance.run_check(
        check,
        base_url='https://candidate.example',
        audience='https://backend-service.example',
    )

    assert outcome.status == 'FAIL'
    assert outcome.diagnostics == {
        'stage': 'probe',
        'service': 'backend-sync',
        'http_status': None,
        'class': 'conn_error',
    }


def test_probe_diagnostics_never_leak_stderr_urls_or_tokens(monkeypatch):
    check = acceptance.CandidateCheck(
        service='backend',
        contract='what_matters_now',
        command=('echo', '{base_url}'),
    )
    monkeypatch.setattr(
        acceptance, 'mint_cloud_run_identity_token', lambda *, audience, impersonate=None: 'raw-token-material'
    )
    monkeypatch.setattr(
        acceptance.subprocess,
        'run',
        lambda *args, **kwargs: _fake_completed_process(
            1,
            stderr=(
                'ERROR: What Matters Now smoke received HTTP 401\n'
                'Authorization: Bearer raw-token-material https://candidate.example/v1/what-matters-now\n'
            ),
        ),
    )

    outcome = acceptance.run_check(
        check,
        base_url='https://candidate.example',
        audience='https://backend-service.example',
    )

    serialized = json.dumps(acceptance.evidence_document([outcome]))
    assert 'raw-token-material' not in serialized
    assert 'candidate.example' not in serialized
    assert outcome.diagnostics is not None
    assert outcome.diagnostics['http_status'] == 401


def test_evidence_schema_stays_backward_compatible():
    passing = acceptance.CheckOutcome(service='backend', contract='what_matters_now', status='PASS')
    failed = acceptance.CheckOutcome(
        service='backend',
        contract='what_matters_now',
        status='FAIL',
        diagnostics={'stage': 'probe', 'service': 'backend', 'http_status': 503, 'class': 'http_failure'},
    )
    not_run = acceptance.CheckOutcome(service='backend-sync', contract='health', status='NOT_RUN')

    passing_document = acceptance.evidence_document([passing])
    assert passing_document == {
        'schema_version': 1,
        'status': 'PASS',
        'checks': [{'service': 'backend', 'contract': 'what_matters_now', 'status': 'PASS'}],
    }

    failed_document = acceptance.evidence_document([failed, not_run])
    assert failed_document['schema_version'] == 1
    assert failed_document['status'] == 'FAIL'
    assert failed_document['checks'][0] == {
        'service': 'backend',
        'contract': 'what_matters_now',
        'status': 'FAIL',
        'diagnostics': {'stage': 'probe', 'service': 'backend', 'http_status': 503, 'class': 'http_failure'},
    }
    assert failed_document['checks'][1] == {'service': 'backend-sync', 'contract': 'health', 'status': 'NOT_RUN'}


def test_passing_run_emits_no_diagnostics_key(monkeypatch, tmp_path):
    monkeypatch.setattr(acceptance, 'mint_cloud_run_identity_token', lambda *, audience, impersonate=None: 'token')
    monkeypatch.setattr(
        acceptance.subprocess, 'run', lambda *args, **kwargs: _fake_completed_process(0, stdout='ok', stderr='')
    )
    code, evidence, _ = _run_acceptance_main(
        tmp_path,
        monkeypatch,
        ['echo', '{base_url}'],
    )

    assert code == 0
    assert evidence['status'] == 'PASS'
    assert evidence['checks'] == [{'service': 'backend', 'contract': 'what_matters_now', 'status': 'PASS'}]


def test_failed_run_adds_diagnostics_to_the_artifact(monkeypatch, tmp_path):
    monkeypatch.setattr(acceptance, 'mint_cloud_run_identity_token', lambda *, audience, impersonate=None: 'token')
    monkeypatch.setattr(
        acceptance.subprocess,
        'run',
        lambda *args, **kwargs: _fake_completed_process(1, stderr='ERROR: Cloud Run health smoke received HTTP 403\n'),
    )
    code, evidence, _ = _run_acceptance_main(
        tmp_path,
        monkeypatch,
        ['echo', '{base_url}'],
    )

    assert code == 1
    assert evidence['status'] == 'FAIL'
    assert evidence['checks'] == [
        {
            'service': 'backend',
            'contract': 'what_matters_now',
            'status': 'FAIL',
            'diagnostics': {
                'stage': 'probe',
                'service': 'backend',
                'http_status': 403,
                'class': 'http_failure',
            },
        }
    ]
