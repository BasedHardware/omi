from pathlib import Path
import subprocess
import sys

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
