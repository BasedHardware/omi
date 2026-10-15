"""Dev acceptance can never send its signed-in summary to a production host."""

from pathlib import Path

import pytest
import yaml

from scripts.probe_dev_fleet_telemetry import payload, verify_dev_candidate
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
