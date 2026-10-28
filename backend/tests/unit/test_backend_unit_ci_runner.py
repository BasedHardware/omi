from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from testing.shell import bash_command, bash_path

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER_SOURCE = REPO_ROOT / 'backend' / 'scripts' / 'run-unit-ci.sh'
TYPECHECK_PREDICATE_SOURCE = REPO_ROOT / 'backend' / 'scripts' / 'needs-typecheck.sh'

SORTED_PATHS = [f'tests/unit/test_{index:02d}.py' for index in range(13)]
GUARD_ENV_LINE = 'test:0.1:1.0:1:not integration and not slow:auto:auto'


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
    predicate = scripts / 'needs-typecheck.sh'
    shutil.copy2(TYPECHECK_PREDICATE_SOURCE, predicate)
    predicate.chmod(0o755)

    log_path = tmp_path / 'runner.log'
    changed_files = tmp_path / 'changed-files.txt'
    changed_files.write_text('backend/routers/example.py\n', encoding='utf-8', newline='\n')

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
echo "preflight:$PYTHON" >> "$RUNNER_SHELL_LOG"
'''.lstrip(),
    )
    _write_executable(
        scripts / 'typecheck.sh',
        '''
#!/usr/bin/env bash
set -euo pipefail
echo "typecheck:$PYTHON" >> "$RUNNER_SHELL_LOG"
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
  "$BACKEND_PYTEST_WORKERS" >> "$RUNNER_SHELL_LOG"
'''.lstrip(),
    )

    shell_python = bash_path(Path(sys.executable), cwd=REPO_ROOT)
    environment = os.environ | {
        'PYTHON': shell_python,
        'RUNNER_LOG': str(log_path),
        'RUNNER_SHELL_LOG': bash_path(log_path, cwd=REPO_ROOT),
    }
    result = subprocess.run(
        bash_command(runner, '--changed-files', changed_files, cwd=REPO_ROOT),
        cwd=backend,
        env=environment,
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert 'Selected 1 backend unit test file(s): fixture selection' in result.stdout

    all_result = subprocess.run(
        bash_command(runner, '--all', cwd=REPO_ROOT),
        cwd=backend,
        env=environment,
        check=False,
        text=True,
        capture_output=True,
    )

    assert all_result.returncode == 0, all_result.stderr
    assert log_path.read_text(encoding='utf-8').splitlines() == [
        'select',
        f'preflight:{shell_python}',
        f'typecheck:{shell_python}',
        'test:0.1:1.0:1:not integration and not slow:auto:auto',
        'select',
        f'preflight:{shell_python}',
        f'typecheck:{shell_python}',
        'test:0.1:1.0:1:not integration and not slow:auto:auto',
    ]


def _sharded_fixture(tmp_path: Path):
    backend = tmp_path / 'backend'
    scripts = backend / 'scripts'
    scripts.mkdir(parents=True)
    runner = scripts / 'run-unit-ci.sh'
    shutil.copy2(RUNNER_SOURCE, runner)
    runner.chmod(0o755)
    predicate = scripts / 'needs-typecheck.sh'
    shutil.copy2(TYPECHECK_PREDICATE_SOURCE, predicate)
    predicate.chmod(0o755)

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
    assert Path(args[args.index('--changed-files') + 1]).is_file()
else:
    assert '--all' in args
out.write_text(os.environ['FIXTURE_SELECTION'], encoding='utf-8')
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
echo "preflight:$PYTHON" >> "$RUNNER_SHELL_LOG"
'''.lstrip(),
    )
    _write_executable(
        scripts / 'typecheck.sh',
        '''
#!/usr/bin/env bash
set -euo pipefail
echo "typecheck:$PYTHON" >> "$RUNNER_SHELL_LOG"
'''.lstrip(),
    )
    _write_executable(
        backend / 'test.sh',
        '''
#!/usr/bin/env bash
set -euo pipefail
cat "$BACKEND_UNIT_TEST_FILE_LIST" > "$TESTS_OUT"
printf 'test:%s:%s:%s:%s:%s:%s\\n' \\
  "$BACKEND_FAST_UNIT_WARN_SECONDS" \\
  "$BACKEND_FAST_UNIT_FAIL_SECONDS" \\
  "$BACKEND_PYTEST_FILE_ISOLATION" \\
  "$BACKEND_PYTEST_MARK_EXPR" \\
  "$BACKEND_PYTEST_XDIST" \\
  "$BACKEND_PYTEST_WORKERS" >> "$RUNNER_SHELL_LOG"
'''.lstrip(),
    )
    return backend, runner


def _run_shard(tmp_path: Path, backend: Path, runner: Path, arguments: list[str], index: str):
    log_path = tmp_path / f'runner-{index}.log'
    tests_out = tmp_path / f'tests-{index}.txt'
    environment = os.environ | {
        'PYTHON': bash_path(Path(sys.executable), cwd=REPO_ROOT),
        'RUNNER_LOG': str(log_path),
        'RUNNER_SHELL_LOG': bash_path(log_path, cwd=REPO_ROOT),
        'TESTS_OUT': bash_path(tests_out, cwd=REPO_ROOT),
        'FIXTURE_SELECTION': ''.join(f'{path}\n' for path in SORTED_PATHS),
    }
    result = subprocess.run(
        bash_command(runner, *arguments, cwd=REPO_ROOT),
        cwd=backend,
        env=environment,
        check=False,
        text=True,
        capture_output=True,
    )
    return result, log_path, tests_out


@pytest.mark.parametrize('mode', ['--all', '--changed-files'])
@pytest.mark.parametrize('total', [2, 4, 6])
def test_shards_partition_the_sorted_selection_exactly(tmp_path, mode, total):
    backend, runner = _sharded_fixture(tmp_path)
    changed_files = tmp_path / 'changed-files.txt'
    changed_files.write_text('backend/routers/example.py\n', encoding='utf-8', newline='\n')

    shard_selections = []
    for index in range(1, total + 1):
        arguments = [mode, '--shard', f'{total}/{index}']
        if mode == '--changed-files':
            arguments.insert(1, str(changed_files))
        result, log_path, tests_out = _run_shard(tmp_path, backend, runner, arguments, f'{mode[2:]}-{total}-{index}')

        assert result.returncode == 0, result.stderr
        assert f'(shard {index}/{total}:' in result.stdout
        expected_log = [
            'select',
            f'preflight:{bash_path(Path(sys.executable), cwd=REPO_ROOT)}',
        ]
        if index == 1:
            # only shard 1 pays the full-tree type check for the commit; its
            # reserved capacity also leaves it empty for this tiny uniform
            # selection, so it stops after "No backend unit tests selected"
            # without ever launching test.sh
            expected_log.append(f'typecheck:{bash_path(Path(sys.executable), cwd=REPO_ROOT)}')
            assert f'No backend unit tests selected (shard 1/{total}: 0 of 13 files)' in result.stdout
        else:
            assert (
                'Skipping backend type check on shard {}/{}: shard 1 runs it for this commit.'.format(index, total)
                in result.stdout
            )
            expected_log.append(GUARD_ENV_LINE)
        assert log_path.read_text(encoding='utf-8').splitlines() == expected_log
        shard_selections.append(tests_out.read_text(encoding='utf-8').splitlines() if tests_out.exists() else [])

    for paths in shard_selections:
        assert paths == sorted(paths)  # uniform fixture weights: deal order is alphabetical
    # the deal reserves shard 1's capacity for the type check it alone runs
    # (4 lanes x the ~90s check), so with a tiny uniform selection shard 1
    # is dealt nothing and the other shards share the files.
    assert shard_selections[0] == []
    assert all(shard_selections[index] for index in range(1, total))
    flattened = [path for paths in shard_selections for path in paths]
    assert sorted(flattened) == SORTED_PATHS
    assert len(flattened) == len(set(flattened)) == len(SORTED_PATHS)


def test_shards_deal_measured_heavy_files_first_to_the_least_loaded_shard(tmp_path):
    # PR #23767: round-robin slices left shard walls 433-754s; dealing by
    # measured weight keeps heavy files from stacking on one shard. The slice
    # keeps deal order (heaviest first) so test.sh's worker slots run a
    # longest-processing-time schedule; shard 1's reserved type-check capacity
    # (see the partition test) keeps it out of this tiny fixture's deal.
    backend, runner = _sharded_fixture(tmp_path)
    heavy = {SORTED_PATHS[0]: 30.0, SORTED_PATHS[3]: 30.0, SORTED_PATHS[6]: 12.5}  # round-robin: all in shard 1 of 3
    (backend / 'scripts/backend_unit_shard_weights.tsv').write_text(
        '# comment\n' + ''.join(f'{path}\t{seconds}\n' for path, seconds in heavy.items()), encoding='utf-8'
    )

    shard_selections = []
    for index in range(1, 4):
        result, _, tests_out = _run_shard(tmp_path, backend, runner, ['--all', '--shard', f'3/{index}'], f'w-{index}')
        assert result.returncode == 0, result.stderr
        shard_selections.append(tests_out.read_text(encoding='utf-8').splitlines() if tests_out.exists() else [])

    flattened = [path for paths in shard_selections for path in paths]
    assert sorted(flattened) == SORTED_PATHS and len(flattened) == len(set(flattened))
    # the two 30s files are dealt to different shards, and each shard's slice
    # is its files in deal order: heaviest first, so the scheduler lanes fill
    # longest-processing-time
    thirty_second_files = {SORTED_PATHS[0], SORTED_PATHS[3]}
    carriers = [index for index, paths in enumerate(shard_selections) if set(paths) & thirty_second_files]
    assert len(carriers) == 2
    for paths in shard_selections:
        weights = [heavy.get(path, 0.0) for path in paths]
        assert weights == sorted(weights, reverse=True)


@pytest.mark.parametrize('spec', ['0/1', '6/0', '6/7', 'six/1', '6'])
def test_malformed_shard_specs_fail_usage_before_any_work(tmp_path, spec):
    backend, runner = _sharded_fixture(tmp_path)
    result, log_path, tests_out = _run_shard(tmp_path, backend, runner, ['--all', '--shard', spec], 'bad')

    assert result.returncode == 2
    assert 'usage:' in result.stderr
    assert not log_path.exists()
    assert not tests_out.exists()


def test_empty_shard_selection_runs_preflight_but_only_shard_one_typechecks(tmp_path):
    backend, runner = _sharded_fixture(tmp_path)
    changed_files = tmp_path / 'changed-files.txt'
    changed_files.write_text('backend/routers/example.py\n', encoding='utf-8', newline='\n')

    for tag, arguments, typecheck_runs in (
        ('all-shard1', ['--all', '--shard', '6/1'], True),
        ('all-shard2', ['--all', '--shard', '6/2'], False),
        ('changed-shard1', ['--changed-files', str(changed_files), '--shard', '6/1'], True),
        ('changed-shard2', ['--changed-files', str(changed_files), '--shard', '6/2'], False),
    ):
        log_path = tmp_path / f'runner-empty-{tag}.log'
        environment = os.environ | {
            'PYTHON': bash_path(Path(sys.executable), cwd=REPO_ROOT),
            'RUNNER_LOG': str(log_path),
            'RUNNER_SHELL_LOG': bash_path(log_path, cwd=REPO_ROOT),
            'FIXTURE_SELECTION': '',
        }
        result = subprocess.run(
            bash_command(runner, *arguments, cwd=REPO_ROOT),
            cwd=backend,
            env=environment,
            check=False,
            text=True,
            capture_output=True,
        )

        assert result.returncode == 0, result.stderr
        assert 'No backend unit tests selected' in result.stdout
        expected_log = [
            'select',
            f'preflight:{bash_path(Path(sys.executable), cwd=REPO_ROOT)}',
        ]
        if typecheck_runs:
            expected_log.append(f'typecheck:{bash_path(Path(sys.executable), cwd=REPO_ROOT)}')
        else:
            assert 'Skipping backend type check on shard' in result.stdout
        assert log_path.read_text(encoding='utf-8').splitlines() == expected_log
