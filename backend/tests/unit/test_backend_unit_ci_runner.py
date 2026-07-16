from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER_SOURCE = REPO_ROOT / 'backend' / 'scripts' / 'run-unit-ci.sh'


def _write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    path.chmod(0o755)


def test_runner_executes_the_same_selected_contract_as_ci(tmp_path):
    backend = tmp_path / 'backend'
    scripts = backend / 'scripts'
    scripts.mkdir(parents=True)
    runner = scripts / 'run-unit-ci.sh'
    shutil.copy2(RUNNER_SOURCE, runner)
    runner.chmod(0o755)

    log_path = tmp_path / 'runner.log'
    changed_files = tmp_path / 'changed-files.txt'
    changed_files.write_text('backend/routers/example.py\n', encoding='utf-8')

    _write_executable(
        scripts / 'select_backend_unit_tests.py',
        '''
from pathlib import Path
import os
import sys

args = sys.argv[1:]
out = Path(args[args.index('--output') + 1])
reason = Path(args[args.index('--reason-output') + 1])
if '--changed-files' in args:
    assert Path(args[args.index('--changed-files') + 1]).read_text(encoding='utf-8') == 'backend/routers/example.py\\n'
else:
    assert '--all' in args
out.write_text('tests/unit/test_example.py\\n', encoding='utf-8')
reason.write_text('fixture selection\\n', encoding='utf-8')
with open(os.environ['RUNNER_LOG'], 'a', encoding='utf-8') as log:
    log.write('select\\n')
'''.lstrip(),
    )
    _write_executable(
        backend / 'test-preflight.sh',
        '''
#!/usr/bin/env bash
set -euo pipefail
echo "preflight:$PYTHON" >> "$RUNNER_LOG"
'''.lstrip(),
    )
    _write_executable(
        scripts / 'typecheck.sh',
        '''
#!/usr/bin/env bash
set -euo pipefail
echo "typecheck:$PYTHON" >> "$RUNNER_LOG"
'''.lstrip(),
    )
    _write_executable(
        backend / 'test.sh',
        '''
#!/usr/bin/env bash
set -euo pipefail
test "$(cat "$BACKEND_UNIT_TEST_FILE_LIST")" = 'tests/unit/test_example.py'
printf 'test:%s:%s:%s:%s:%s:%s\\n' \\
  "$BACKEND_FAST_UNIT_WARN_SECONDS" \\
  "$BACKEND_FAST_UNIT_FAIL_SECONDS" \\
  "$BACKEND_PYTEST_FILE_ISOLATION" \\
  "$BACKEND_PYTEST_MARK_EXPR" \\
  "$BACKEND_PYTEST_XDIST" \\
  "$BACKEND_PYTEST_WORKERS" >> "$RUNNER_LOG"
'''.lstrip(),
    )

    environment = os.environ | {'PYTHON': sys.executable, 'RUNNER_LOG': str(log_path)}
    result = subprocess.run(
        ['bash', str(runner), '--changed-files', str(changed_files)],
        cwd=backend,
        env=environment,
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert 'Selected 1 backend unit test file(s): fixture selection' in result.stdout

    all_result = subprocess.run(
        ['bash', str(runner), '--all'],
        cwd=backend,
        env=environment,
        check=False,
        text=True,
        capture_output=True,
    )

    assert all_result.returncode == 0, all_result.stderr
    assert log_path.read_text(encoding='utf-8').splitlines() == [
        'select',
        f'preflight:{sys.executable}',
        f'typecheck:{sys.executable}',
        'test:0.1:1.0:1:not integration and not slow:auto:auto',
        'select',
        f'preflight:{sys.executable}',
        f'typecheck:{sys.executable}',
        'test:0.1:1.0:1:not integration and not slow:auto:auto',
    ]
