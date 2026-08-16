from __future__ import annotations

import json
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from scripts.repair_cloud_run_traffic import (
    analyze_service_traffic,
    repair_command,
    repair_from_state,
)

FIXTURES = BACKEND_ROOT / 'tests' / 'fixtures' / 'deploy_status'


def test_analyze_service_traffic_detects_spec_status_mismatch() -> None:
    state = json.loads((FIXTURES / 'cloud_run_spec_status_mismatch.json').read_text(encoding='utf-8'))
    service_doc = state['services'][0]

    analysis = analyze_service_traffic(service_doc, service='backend')

    assert analysis.serving_revision == 'backend-good-1'
    assert analysis.spec_revision == 'backend-failed-1'
    assert analysis.mismatched is True


def test_repair_from_state_reports_mismatch_without_repair_flag() -> None:
    state = json.loads((FIXTURES / 'cloud_run_spec_status_mismatch.json').read_text(encoding='utf-8'))

    results = repair_from_state(state, services=('backend',), repair=False, project='based-hardware')

    assert len(results) == 1
    assert results[0].action == 'failed'
    assert results[0].serving_revision == 'backend-good-1'


def test_analyze_service_traffic_resolves_latest_revision_target() -> None:
    state = json.loads((FIXTURES / 'cloud_run_latest_revision_traffic.json').read_text(encoding='utf-8'))
    service_doc = state['services'][0]

    analysis = analyze_service_traffic(service_doc, service='backend')

    assert analysis.serving_revision == 'backend-good-1'
    assert analysis.spec_revision == 'backend-failed-1'
    assert analysis.mismatched is True


def test_repair_command_format() -> None:
    command = repair_command(
        project='based-hardware',
        region='us-central1',
        service='backend',
        revision='backend-good-1',
    )

    assert command == (
        'gcloud run services update-traffic backend '
        '--project=based-hardware --region=us-central1 --to-revisions=backend-good-1=100 --quiet'
    )


def test_repair_from_state_accepts_top_level_service_list(tmp_path: Path) -> None:
    state = json.loads((FIXTURES / 'cloud_run_spec_status_mismatch.json').read_text(encoding='utf-8'))
    state_path = tmp_path / 'services.json'
    state_path.write_text(json.dumps(state['services']), encoding='utf-8')

    from scripts.repair_cloud_run_traffic import _load_state

    loaded = _load_state(str(state_path))
    results = repair_from_state(
        loaded,
        services=('backend',),
        repair=False,
        project='based-hardware',
        region='us-central1',
    )

    assert len(results) == 1
    assert results[0].action == 'failed'
