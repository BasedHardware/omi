from pathlib import Path
import subprocess
import sys

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
SELECTOR = BACKEND_DIR / 'scripts' / 'select_backend_unit_tests.py'
SELECTED_TEST = 'tests/unit/test_workflow_contracts.py'


def test_selector_artifacts_use_lf_on_every_platform(tmp_path: Path) -> None:
    input_list = tmp_path / 'input.txt'
    selected_list = tmp_path / 'selected.txt'
    reason_file = tmp_path / 'reason.txt'
    input_list.write_bytes(f'{SELECTED_TEST}\r\n'.encode('utf-8'))

    subprocess.run(
        [
            sys.executable,
            str(SELECTOR),
            '--from-test-list',
            str(input_list),
            '--output',
            str(selected_list),
            '--reason-output',
            str(reason_file),
        ],
        cwd=BACKEND_DIR,
        check=True,
    )

    assert selected_list.read_bytes() == f'{SELECTED_TEST}\n'.encode('utf-8')
    assert reason_file.read_bytes() == b'using provided backend unit test list\n'


@pytest.mark.parametrize(
    'source',
    [
        'backend/charts/backend-listen/templates/deployment.yaml',
        'backend/charts/pusher/templates/deployment.yaml',
        'backend/charts/monitoring/kube-prometheus-stack/prod_omi_monitoring_values.yaml',
    ],
)
def test_monitoring_changes_select_firestore_attribution_charts(tmp_path, source):
    changed = tmp_path / 'changed.txt'
    changed.write_text(source + '\n')
    result = subprocess.run(
        [sys.executable, str(SELECTOR), '--changed-files', str(changed)],
        cwd=BACKEND_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    assert 'tests/unit/test_firestore_attribution_charts.py' in result.stdout.splitlines()
