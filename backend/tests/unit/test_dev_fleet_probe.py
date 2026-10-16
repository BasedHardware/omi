"""Dev acceptance can never send its signed-in summary to a production host."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call
import json

import pytest
import yaml

from scripts.probe_dev_fleet_telemetry import payload, verify_dev_candidate
from scripts import probe_dev_fleet_telemetry as probe
from config.fleet_telemetry import validate_summary


def test_dev_probe_uses_the_actual_dev_candidate_and_valid_schema():
    url = 'https://candidate---backend-dev.example.run.app'
    service = {'status': {'url': 'https://backend-dev.example.run.app', 'traffic': [{'url': url}]}}
    verify_dev_candidate(url, service)
    validate_summary(payload())
    for invalid in ('https://api.omi.me', 'https://backend-prod.example.run.app', url + '/other', url + '?x=y'):
        with pytest.raises(ValueError):
            verify_dev_candidate(invalid, service)


def test_probe_is_explicitly_opted_in_by_admitted_source_deploys_only():
    root = Path(__file__).resolve().parents[3]
    probe = yaml.safe_load((root / '.github/actions/transcription-release-candidate-probe/action.yml').read_text())
    assert probe['inputs']['probe_fleet']['default'] == 'false'
    assert '"$PROBE_FLEET" == true' in probe['runs']['steps'][0]['run']
    stack = yaml.safe_load((root / '.github/actions/deploy-backend-stack/action.yml').read_text())
    step = next(step for step in stack['runs']['steps'] if step['name'] == 'Gate backend candidate on known audio')
    assert step['with']['probe_fleet'] == 'true'
    cutover = (root / '.github/workflows/sync_ledger_fence_cutover.yml').read_text()
    assert 'probe_fleet:' not in cutover


@pytest.mark.parametrize('status', [200, 429])
def test_probe_requires_accepted_summary_without_retrying(status, monkeypatch, tmp_path, capsys):
    url = 'https://candidate---backend-dev.example.run.app'
    token = tmp_path / 'token'
    token.write_text('synthetic-token')
    monkeypatch.setattr('sys.argv', ['probe', '--candidate-api-url', url, '--bearer-token-file', str(token)])
    service = {'status': {'url': url}}
    monkeypatch.setattr(probe.subprocess, 'run', Mock(return_value=SimpleNamespace(stdout=json.dumps(service))))
    post = Mock(side_effect=[(401, {}), (status, {'schema_version': 1, 'accepted': True, 'clamped': False})])
    monkeypatch.setattr(probe, 'post', post)
    if status == 429:
        with pytest.raises(SystemExit, match='acceptance incomplete.*429'):
            probe.main()
        assert 'accepted (200)' not in capsys.readouterr().out
    else:
        probe.main()
        assert 'accepted (200)' in capsys.readouterr().out
    assert post.call_args_list == [call(url), call(url, 'synthetic-token')]
