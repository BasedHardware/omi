"""Private cohorts cannot widen through empty payloads or the legacy bulk sync path."""

import base64
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import verify_k8s_secret_keys as k8s
from scripts.private_cohort_secrets import PRIVATE_COHORT_ENV_NAMES, valid_private_cohort_payload

ROOT = Path(__file__).resolve().parents[3]
KEY = 'SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST'


@pytest.mark.parametrize('payload', ['', '  \n', ', ,\t,'])
def test_empty_parsed_lineage_cohort_is_rejected(payload):
    assert not valid_private_cohort_payload(KEY, payload)


@pytest.mark.parametrize('payload', ['synthetic-owner', ' , synthetic-owner,other-owner, '])
def test_nonempty_lineage_payload_is_accepted(payload):
    assert valid_private_cohort_payload(KEY, payload)


def _preflight():
    spec = importlib.util.spec_from_file_location(
        'private_cohort_preflight', ROOT / 'backend/scripts/preflight-cloud-run-deploy.py'
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    'payload,code,expected',
    [('', 0, 1), ('  , , ', 0, 1), ('private-value-do-not-log', 1, 1), ('synthetic-owner', 0, 0), (b'\xff', 0, 1)],
)
def test_cloud_run_preflight_blocks_empty_or_inaccessible_payload_without_logging(
    monkeypatch, capsys, payload, code, expected
):
    preflight = _preflight()
    monkeypatch.setattr(
        preflight,
        '_cloud_run_service_configs',
        lambda **kwargs: {'backend-sync': {'secrets': {KEY: {'secret': KEY, 'version': 'latest'}}}},
    )
    monkeypatch.setattr(preflight, 'check_rendered_secrets', lambda **kwargs: [])
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, code, payload, 'private-error-do-not-log')

    monkeypatch.setattr(preflight.subprocess, 'run', fake_run)
    monkeypatch.setattr(
        sys,
        'argv',
        ['preflight', '--env', 'prod', '--project', 'synthetic', '--service', 'backend-sync', '--check-secrets'],
    )
    assert preflight.main() == expected
    assert calls == [['gcloud', 'secrets', 'versions', 'access', 'latest', f'--secret={KEY}', '--project=synthetic']]
    output = capsys.readouterr()
    if expected:
        assert 'private cohort payload validation failed' in output.err
        assert KEY not in output.err
    assert 'synthetic-owner' not in output.err + output.out
    assert 'private-value-do-not-log' not in output.err + output.out
    assert 'private-error-do-not-log' not in output.err + output.out


@pytest.mark.parametrize('payload,expected', [('', 1), ('  , , ', 1), ('synthetic-owner', 0)])
def test_k8s_gate_checks_payload_not_just_presence(tmp_path, monkeypatch, capsys, payload, expected):
    values = tmp_path / 'values.yaml'
    values.write_text(f'externalSecret:\n  secretKeys:\n    - secretKey: {KEY}\n      remoteKey: {KEY}\n')
    data = {KEY: base64.b64encode(payload.encode()).decode()}
    monkeypatch.setattr(sys, 'argv', ['verify', str(values)])
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps({'data': data})))
    assert k8s.main() == expected
    output = capsys.readouterr()
    assert 'synthetic-owner' not in output.err + output.out


def test_bulk_sync_excludes_all_private_cohorts_for_every_target(tmp_path):
    fake = tmp_path / 'gcloud'
    log = tmp_path / 'calls'
    fake.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALLS"\n')
    fake.chmod(0o755)
    env = {**os.environ, 'PATH': str(tmp_path) + os.pathsep + os.environ['PATH'], 'CALLS': str(log)}
    subprocess.run(
        ['bash', 'backend/scripts/sync_cloudrun_secrets_from_chart.sh', 'prod', '--project', 'synthetic'],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    calls = log.read_text()
    assert '--update-secrets=' in calls and 'OPENAI_API_KEY=OPENAI_API_KEY:latest' in calls
    assert all(name + '=' not in calls for name in PRIVATE_COHORT_ENV_NAMES)


def test_reviewed_stages_and_guard_constants_contain_no_membership():
    stages = json.loads((ROOT / 'config/diarization-cohort-stages.json').read_text())
    assert all(not any(key.endswith('UID_ALLOWLIST') for key in stage) for stage in stages.values())
    spec = importlib.util.spec_from_file_location(
        'private_cohort_cohost', ROOT / 'backend/scripts/verify_pusher_cohost_env_diff.py'
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    assert not any(
        key.endswith('UID_ALLOWLIST') for key in {**module.PROD_SHADOW_VALUES, **module.PROD_FINAL_PASS_SHADOW_VALUES}
    )


@pytest.mark.parametrize(
    'payload,expected', [('{}', False), ('[]', False), ('not-json', False), ('{"imessage":{"enabled":true}}', True)]
)
def test_private_policy_requires_a_nonempty_json_object(payload, expected):
    assert valid_private_cohort_payload('OMI_MESSAGING_CHANNEL_POLICY', payload) is expected
